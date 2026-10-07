"""Fan-out of a query to every registered endpoint, in parallel."""
import logging
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

from .models import Endpoint

log = logging.getLogger(__name__)

# The endpoint gives its own backend (Ontop) 10 s, so Central must wait longer
# than that or it would drop answers the endpoint is still producing.
ENDPOINT_TIMEOUT = 15
MAX_WORKERS = 16


def _post(ep, fields, accept):
    url = ep.url.rstrip('/') + '/sparql-protected/'
    resp = requests.post(
        url,
        data=urllib.parse.urlencode(fields, quote_via=urllib.parse.quote, safe=''),
        headers={
            'Accept': accept,
            'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        },
        timeout=ENDPOINT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def dispatch(fields, accept='application/sparql-results+json'):
    """POST ``fields`` to all endpoints concurrently.

    Returns a list of ``(endpoint, data)`` for the endpoints that answered with
    JSON, and the list of endpoints that did not (timeout, connection or HTTP
    error, non-JSON body). Order follows the endpoint table.
    """
    endpoints = list(Endpoint.objects.all())
    if not endpoints:
        return [], []
    answered, failed = [], []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(endpoints))) as pool:
        futures = [(ep, pool.submit(_post, ep, fields, accept)) for ep in endpoints]
        for ep, fut in futures:
            try:
                answered.append((ep, fut.result()))
            except (requests.RequestException, ValueError) as exc:
                log.warning("endpoint %s (%s) failed: %s", ep.name, ep.url, type(exc).__name__)
                failed.append(ep)
    return answered, failed
