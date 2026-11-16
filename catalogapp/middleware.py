import re

_REPEATED_SLASHES = re.compile(r'/{2,}')


class CollapseSlashesMiddleware:
    """Collapse repeated slashes in the path before URL routing.

    The public site reaches Central through an Apache ProxyPass whose target
    ends with '/' while the source does not (``ProxyPass /api0 http://...:8070/``).
    Apache then forwards ``/api0/catalog/`` as ``//catalog/``, which no URL
    pattern matches. This keeps the routing correct without changing the proxy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '//' in request.path_info:
            request.path_info = _REPEATED_SLASHES.sub('/', request.path_info)
        return self.get_response(request)
