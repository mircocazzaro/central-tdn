# catalogapp/views.py
import duckdb
import requests
from urllib.parse import urlparse
import urllib.parse
from django.shortcuts      import render, redirect, get_object_or_404
from django.conf           import settings
from django.contrib        import messages
from django.views.decorators.http import require_http_methods
from requests_toolbelt.utils import dump

from functools import wraps

from .queries              import catalog
from .models               import Endpoint
from .forms                import QueryForm, EndpointForm


def require_manager_password(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # Already authenticated?
        if request.session.get('manager_authenticated'):
            return view_func(request, *args, **kwargs)

        # Handle login POST
        if request.method == 'POST' and 'manager_password' in request.POST:
            if request.POST['manager_password'] == settings.ENDPOINT_MANAGER_PASSWORD:
                request.session['manager_authenticated'] = True
                return redirect(request.path)
            else:
                return render(request, 'catalogapp/manager_login.html', {
                    'error': 'Incorrect password'
                })

        # Otherwise show the login form
        return render(request, 'catalogapp/manager_login.html')
    return _wrapped


@require_manager_password
def endpoint_manager(request):
    """
    List all endpoints with Add / Edit / Delete links,
    and check whether each one is up.
    """
    eps = []
    for ep in Endpoint.objects.all():
        # normalize the base URL (so we don't accidentally hit `/sparql-protected/`)
        parsed = urlparse(ep.url)
        base = f"{parsed.scheme}://{parsed.netloc}/sparql-protected/"
        try:
            # you can also do a HEAD if you prefer
            resp = requests.get(base, timeout=2)
            ep.online = False
            if (resp.status_code == 405):
                ep.online = True
        except requests.RequestException:
            ep.online = False
        eps.append(ep)

    return render(request, 'catalogapp/endpoint_manager.html', {
        'endpoints': eps
    })


@require_manager_password
@require_http_methods(["GET", "POST"])
def endpoint_add(request):
    form = EndpointForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Endpoint added!")
        return redirect('endpoint_manager')

    return render(request, 'catalogapp/endpoint_form.html', {
        'form':  form,
        'title': 'Add Endpoint'
    })


@require_manager_password
@require_http_methods(["GET", "POST"])
def endpoint_edit(request, pk):
    ep   = get_object_or_404(Endpoint, pk=pk)
    form = EndpointForm(request.POST or None, request.FILES or None, instance=ep)
    if form.is_valid():
        form.save()
        messages.success(request, "Endpoint updated!")
        return redirect('endpoint_manager')

    return render(request, 'catalogapp/endpoint_form.html', {
        'form':  form,
        'title': f'Edit "{ep.name}"'
    })


@require_manager_password
@require_http_methods(["GET", "POST"])
def endpoint_delete(request, pk):
    ep = get_object_or_404(Endpoint, pk=pk)
    if request.method == 'POST':
        ep.delete()
        messages.success(request, "Endpoint deleted!")
        return redirect('endpoint_manager')

    return render(request, 'catalogapp/endpoint_confirm_delete.html', {
        'endpoint': ep
    })


def home(request):
    """
    Redirect root URL to the catalog.
    """
    return redirect('central_catalog')


def central_catalog(request):
    entries = catalog()
    # give each one a simple integer id
    for idx, e in enumerate(entries):
        e['id'] = idx
    return render(request, 'catalogapp/catalog.html', {
        'catalog': entries
    })



def query_view(request):
    """
    Render the parameter‐form for a chosen query template (GET),
    or fan‐out the fully‐instantiated SPARQL to all endpoints (POST).
    """

    # 1) Grab the id param (must be present on both GET and POST)
    raw_id = request.GET.get('id') if request.method == 'GET' else request.POST.get('id')
    try:
        idx     = int(raw_id)
        entries = catalog()
        entry   = entries[idx]
    except Exception:
        messages.error(request, "Unknown query template.")
        return redirect('central_catalog')

    # 2) If POST, instantiate + dispatch
    if request.method == 'POST':
        # <-- only pass params now, not template
        form = QueryForm(request.POST, params=entry['params'])
        if form.is_valid():
            # build the concrete SPARQL
            q = entry['template']
            for k, v in form.cleaned_data.items():
                q = q.replace(f'{{{k}}}', v)
            prefixes = '''PREFIX bto:   <https://w3id.org/brainteaser/ontology/schema/>
PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
PREFIX NCIT:  <http://purl.obolibrary.org/obo/NCIT_>
'''

            q = prefixes + q
            
            
            entry['template'] = entry['template'].replace('<{', '**<').replace('}>', '>**')
            results = []
            for ep in Endpoint.objects.all():
                url = ep.url.rstrip('/') + '/sparql-protected/'
                resp = requests.post(
                    url,
                    data=urllib.parse.urlencode({
                        'template': entry['template'],
                        'query':    q,
                    }, quote_via=urllib.parse.quote, safe=''),
                    headers={
                        'Accept': 'application/sparql-results+json',
                        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'
                    },
                    timeout=5
                )
                # dump both request and response:
                dump_data = dump.dump_all(resp)
                # you can log it, print it, or write to a file:
                #print(dump_data.decode('utf-8')) HERE IS PRINT REQUEST
              

                resp.raise_for_status()
                data = resp.json()

                # Handle ASK, SELECT, or empty/unauthorized cases
                if 'boolean' in data:
                    results.append({'endpoint': ep.name, 'logo_url': ep.logo.url, 'boolean': data['boolean']})
            
                elif 'head' in data and 'results' in data:
                    head = data['head']['vars']
                    for bd in data['results']['bindings']:
                        row = {v: bd[v]['value'] for v in head}
                        row['endpoint'] = ep.name
                        row['logo_url'] = ep.logo.url
                        results.append(row)
            
                elif 'results' in data:
                    # known template but no results (or unauthorized)
                    results.append({'endpoint': ep.name, 'logo_url': ep.logo.url, 'rows': []})
            
                else:
                    results.append({'endpoint': ep.name, 'logo_url': ep.logo.url, 'error': 'Invalid response'})

            return render(request, 'catalogapp/results.html', {
                'query':   q,
                'results': results
            })

    # 3) Otherwise (GET) just show the form
    else:
        # <-- only pass params here as well
        form = QueryForm(params=entry['params'])

    # 4) Always include `id` in the context so your hidden <input> gets populated
    return render(request, 'catalogapp/query.html', {
        'description': entry['description'],
        'template':    entry['template'],
        'form':         form,
        'id':           raw_id,
    })



