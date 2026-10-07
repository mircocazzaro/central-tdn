"""Central side of the HDN network protocols.

- identity of this Central (Ed25519 key in the state directory);
- /hdn/key/: public key, fetched by endpoints on first contact;
- /hdn/enroll/: signed applications from endpoints;
- approval: Central notifies the endpoint and adds it once the endpoint has
  answered with a signature by the key it applied with.
"""
import datetime
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from . import hdnsig
from .models import Endpoint, EnrollmentRequest, SeenNonce

log = logging.getLogger(__name__)

ENDPOINT_TIMEOUT = 30
MAX_PENDING = 200
MAX_WORKERS = 16


@lru_cache(maxsize=None)
def _identity_at(path):
    return hdnsig.load_or_create_identity(path)


def identity():
    return _identity_at(str(Path(settings.STATE_DIR) / 'hdn' / 'identity.pem'))


def remember_nonce(sender, nonce):
    cutoff = timezone.now() - datetime.timedelta(seconds=2 * hdnsig.MAX_SKEW)
    SeenNonce.objects.filter(seen__lt=cutoff).delete()
    try:
        with transaction.atomic():
            SeenNonce.objects.create(sender=sender, nonce=nonce)
    except IntegrityError:
        return False
    return True


class _Headers:
    def __init__(self, request):
        self._r = request

    def get(self, name):
        return self._r.headers.get(name)


def _signed_json(action, nonce, status, payload):
    body = hdnsig.encode_body(payload)
    resp = HttpResponse(body, status=status, content_type='application/json')
    for k, v in hdnsig.sign_response(identity(), action, nonce, status, body).items():
        resp[k] = v
    return resp


@require_GET
def hdn_key(request):
    """Public key of this Central. Trusted by endpoints on first use."""
    me = identity()
    return JsonResponse({'name': settings.HDN_CENTRAL_NAME, 'public_key': me.public_b64,
                         'fingerprint': me.fingerprint})


@csrf_exempt
def hdn_enroll(request):
    """Signed application of an endpoint. Queued for the manager."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    body = request.body
    if len(body) > 64 * 1024:
        return HttpResponse(status=413)
    try:
        sender = hdnsig.verify_request(_Headers(request), 'enroll', identity().fingerprint,
                                       body, remember_nonce)
    except hdnsig.SignatureError as exc:
        log.warning('enroll rejected: %s from %s', exc.reason, request.META.get('REMOTE_ADDR'))
        return HttpResponse(status=401)
    nonce = request.headers.get(hdnsig.H_NONCE)
    try:
        payload = json.loads(body.decode('utf-8'))
        name = str(payload['name']).strip()[:100]
        url = str(payload['url']).strip()
        URLValidator(schemes=['http', 'https'])(url)
        if payload.get('public_key') != sender or not name:
            raise ValueError
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, ValidationError):
        return _signed_json('enroll', nonce, 400, {
            'error': 'name, url (http/https) and public_key (the signing key) are required'})

    if Endpoint.objects.filter(public_key=sender).exists():
        return _signed_json('enroll', nonce, 200, {'status': 'approved'})
    existing = EnrollmentRequest.objects.filter(public_key=sender).first()
    if existing is None and EnrollmentRequest.objects.filter(
            status=EnrollmentRequest.PENDING).count() >= MAX_PENDING:
        return _signed_json('enroll', nonce, 503, {'error': 'too many pending applications'})
    EnrollmentRequest.objects.update_or_create(
        public_key=sender,
        defaults={'name': name, 'url': url, 'status': EnrollmentRequest.PENDING,
                  'remote_addr': request.META.get('REMOTE_ADDR')},
    )
    return _signed_json('enroll', nonce, 202, {'status': 'pending'})


class DecisionFailed(Exception):
    pass


def decide(req, approve):
    """Communicate the manager's decision to the endpoint.

    On approval the endpoint must answer, signed with the key it applied with,
    at the URL it declared: only then is it added to the federation.
    Rejections are recorded even if the endpoint cannot be reached.
    """
    payload = {'decision': 'approved' if approve else 'rejected',
               'central_name': settings.HDN_CENTRAL_NAME}
    url = req.url.rstrip('/') + '/hdn/enrollment/'
    try:
        status, data = hdnsig.post_signed(identity(), url, 'enrollment', req.public_key,
                                          payload, timeout=ENDPOINT_TIMEOUT)
        ok = status == 200
        detail = '' if ok else f'HTTP {status}'
    except hdnsig.SignatureError as exc:
        ok, detail = False, f'answer not signed by the applicant key ({exc.reason})'
    except requests.RequestException as exc:
        ok, detail = False, f'endpoint not reachable ({type(exc).__name__})'

    if not approve:
        req.status = EnrollmentRequest.REJECTED
        req.save()
        return None
    if not ok:
        raise DecisionFailed(detail)
    with transaction.atomic():
        ep = Endpoint.objects.create(name=req.name, url=req.url.rstrip('/'),
                                     public_key=req.public_key)
        req.delete()
    return ep


def push_all(action, payload, path, endpoints=None):
    """Signed POST of ``payload`` to every enrolled endpoint, in parallel.

    Returns ``[(endpoint, ok, status, data_or_error)]``; responses must be
    signed by the endpoint's own key.
    """
    eps = list(endpoints if endpoints is not None
               else Endpoint.objects.exclude(public_key=''))

    def one(ep):
        try:
            status, data = hdnsig.post_signed(identity(), ep.url.rstrip('/') + path, action,
                                              ep.public_key, payload, timeout=ENDPOINT_TIMEOUT)
            return ep, status == 200, status, data
        except hdnsig.SignatureError as exc:
            return ep, False, None, f'invalid signature ({exc.reason})'
        except requests.RequestException as exc:
            return ep, False, None, f'not reachable ({type(exc).__name__})'

    if not eps:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(eps))) as pool:
        return list(pool.map(one, eps))
