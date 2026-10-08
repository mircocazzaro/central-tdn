"""Central side of the HDN network protocols.

- identity of this Central (Ed25519 key in the state directory);
- /hdn/key/: public key, fetched by endpoints on first contact;
- /hdn/enroll/: signed applications from endpoints;
- approval: Central notifies the endpoint and adds it once the endpoint has
  answered with a signature by the key it applied with.
"""
import datetime
import hashlib
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


# ---------------------------------------------------------------------------
# Query catalog distribution
# ---------------------------------------------------------------------------

def _digest(doc):
    body = {k: v for k, v in doc.items() if k != 'version'}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode('utf-8')).hexdigest()


def current_catalog_release():
    """Release matching the current catalog (queries.py), created if it changed.

    Returns ``(release, skipped)``.
    """
    from .models import CatalogRelease
    from .queries import federated_templates
    from .views import prefixes

    published, skipped = federated_templates()
    doc = {'prologue': prefixes, 'templates': published}
    digest = _digest(doc)
    with transaction.atomic():
        last = CatalogRelease.objects.select_for_update().order_by('-version').first()
        if last and last.digest == digest:
            return last, skipped
        version = (last.version + 1) if last else 1
        doc['version'] = version
        return CatalogRelease.objects.create(version=version, document=doc, digest=digest), skipped


def push_catalog(release, endpoints=None):
    """Send ``release`` to the enrolled endpoints; records the installed version."""
    results = push_all('catalog', {'catalog': release.document}, '/hdn/catalog/', endpoints)
    for ep, ok, status, data in results:
        if ok and isinstance(data, dict) and data.get('version') == release.version:
            Endpoint.objects.filter(pk=ep.pk).update(catalog_version=release.version)
        elif isinstance(data, dict) and status == 409 and isinstance(data.get('installed'), int):
            Endpoint.objects.filter(pk=ep.pk).update(catalog_version=data['installed'])
    return results


def describe(results):
    """Human-readable per-endpoint outcome lines."""
    out = []
    for ep, ok, status, data in results:
        if ok:
            out.append((ep.name, True, str((data or {}).get('status', 'ok'))))
        else:
            detail = data if isinstance(data, str) else (
                (data or {}).get('error', '') if isinstance(data, dict) else '')
            out.append((ep.name, False, f"{'HTTP %s ' % status if status else ''}{detail}".strip()))
    return out


# ---------------------------------------------------------------------------
# Ontology distribution
# ---------------------------------------------------------------------------

MAX_ONTOLOGY_BYTES = 8 * 1024 * 1024


class InvalidUpload(ValueError):
    pass


def _text(what, data):
    if not data:
        raise InvalidUpload(f'the {what} is empty')
    if len(data) > MAX_ONTOLOGY_BYTES:
        raise InvalidUpload(f'the {what} exceeds {MAX_ONTOLOGY_BYTES // (1024 * 1024)} MB')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise InvalidUpload(f'the {what} is not UTF-8 text')


def new_ontology_release(filename, data, template_filename, template_data):
    """Store an ontology and its mapping template as the next version.

    Both are required. Central only checks size and encoding; each endpoint
    parses them and refuses the pair (reported per endpoint) if the ontology
    is not valid or the template uses terms the ontology does not declare.
    """
    from .models import OntologyRelease
    text = _text('ontology file', data)
    if '[MappingDeclaration]' not in (template_text := _text('mapping template', template_data)):
        raise InvalidUpload('the mapping template is not an Ontop .obda file')
    digest = hashlib.sha256(data).hexdigest()
    tdigest = hashlib.sha256(template_data).hexdigest()
    with transaction.atomic():
        last = OntologyRelease.objects.select_for_update().order_by('-version').first()
        if last and last.sha256 == digest and last.template_sha256 == tdigest:
            return last
        return OntologyRelease.objects.create(
            version=(last.version + 1) if last else 1, filename=filename[:200],
            ttl=text, sha256=digest, template_filename=template_filename[:200],
            mapping_template=template_text, template_sha256=tdigest)


def push_ontology(release, endpoints=None):
    payload = {'version': release.version, 'ttl': release.ttl, 'sha256': release.sha256,
               'mapping_template': release.mapping_template,
               'template_sha256': release.template_sha256}
    results = push_all('ontology', payload, '/hdn/ontology/', endpoints)
    for ep, ok, status, data in results:
        if ok and isinstance(data, dict) and data.get('version') == release.version:
            Endpoint.objects.filter(pk=ep.pk).update(ontology_version=release.version)
        elif isinstance(data, dict) and status == 409 and isinstance(data.get('installed'), int):
            Endpoint.objects.filter(pk=ep.pk).update(ontology_version=data['installed'])
    return results


def describe_ontology(results):
    """Like describe(), with the mapping outcome reported by each endpoint."""
    out = []
    for (name, ok, detail), (_, _, _, data) in zip(describe(results), results):
        if ok and isinstance(data, dict) and data.get('status') == 'installed':
            m = data.get('mapping')
            if m in ('reduced', 'emptied'):
                detail = f"installed, {data.get('dropped')} mappings removed, {data.get('kept')} kept"
            elif m == 'unchanged':
                detail = 'installed, all mappings still valid'
            else:
                detail = 'installed (no mapping yet)'
        out.append((name, ok, detail))
    return out
