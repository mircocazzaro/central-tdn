# catalogapp/views.py
import requests
import urllib.parse
from django.shortcuts      import render, redirect, get_object_or_404
from django.conf           import settings
from django.contrib        import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from functools import wraps

from .queries              import catalog, get_entry
from .models               import Endpoint, EnrollmentRequest
from .                     import network
from .dispatch             import dispatch, probe_all
from .forms                import QueryForm, EndpointForm
from .forms import QUESTION_CHOICES, DISEASE_CHOICES
import base64
import io
import pandas as pd
from django.views.decorators.http import require_POST
from sklearn.tree import DecisionTreeRegressor, plot_tree
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import uuid
import matplotlib
matplotlib.use('Agg')  # headless, no GUI backend in a threaded server
import matplotlib.pyplot as plt  # noqa: E402

# simple in‐memory store for trained models
_models = {}

TREE_PARAMS = [
    'criterion',
    'splitter',
    'max_depth',
    'min_samples_split',
    'min_samples_leaf',
    'max_features',
    'random_state',
]


prefixes = '''PREFIX bto:   <https://w3id.org/brainteaser/ontology/schema/>
PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
PREFIX NCIT:  <http://purl.obolibrary.org/obo/NCIT_>
'''

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
    eps = list(Endpoint.objects.all())
    for ep, online in zip(eps, probe_all(eps)):
        ep.online = online

    return render(request, 'catalogapp/endpoint_manager.html', {
        'endpoints': eps,
        'applications': EnrollmentRequest.objects.filter(status=EnrollmentRequest.PENDING),
        'central_fingerprint': network.identity().fingerprint,
    })


@require_manager_password
@require_POST
def enrollment_decide(request, pk):
    """Approve or reject an endpoint's application."""
    req = get_object_or_404(EnrollmentRequest, pk=pk, status=EnrollmentRequest.PENDING)
    approve = request.POST.get('decision') == 'approve'
    try:
        ep = network.decide(req, approve)
    except network.DecisionFailed as exc:
        messages.error(request, f'"{req.name}" was not added: {exc}. '
                                'The application stays pending.')
    else:
        if approve:
            messages.success(request, f'"{ep.name}" joined the network.')
        else:
            messages.info(request, f'Application of "{req.name}" rejected.')
    return redirect('endpoint_manager')


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
        # remove the file from storage first
        if ep.logo:
            ep.logo.delete(save=False)
        # then delete the DB record
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


@login_required
def central_catalog(request):
    entries = catalog()
    for e in entries:
        e["id"] = e["key"]

    return render(request, "catalogapp/catalog.html", {
        "catalog": entries,
        # Single source for the dropdowns: the same lists the form validates against
        "QUESTION_CHOICES": QUESTION_CHOICES,
        "DISEASE_CHOICES": DISEASE_CHOICES,
    })


@login_required
def query_view(request):
    """
    Render the parameter‐form for a chosen query template (GET),
    or fan‐out the fully‐instantiated SPARQL to all endpoints (POST).
    """

    # 1) Grab the id param (must be present on both GET and POST)
    raw_id = request.GET.get('id') if request.method == 'GET' else request.POST.get('id')
    entry = get_entry(raw_id)
    if entry is None:
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


            q = prefixes + q

            # Endpoints derive the template from the query itself.
            results = []
            responders = []
            answered, failed = dispatch({'query': q})

            for ep, data in answered:
                if not isinstance(data, dict):
                    failed.append(ep)
                    continue
                if 'boolean' in data:
                    results.append({
                        'endpoint': ep.name,
                        'logo_url': ep.logo_url,
                        'boolean':  data['boolean']
                    })
                    n_rows = 1
                elif isinstance(data.get('results'), dict):
                    # An endpoint that declines to contribute answers with an
                    # empty result: it still counts as a responder.
                    head = data.get('head', {}).get('vars', [])
                    bindings = data['results'].get('bindings', [])
                    for bd in bindings:
                        row = {v: bd[v]['value'] if v in bd else None for v in head}
                        row['endpoint'] = ep.name
                        row['logo_url'] = ep.logo_url
                        results.append(row)
                    n_rows = len(bindings)
                else:
                    failed.append(ep)
                    continue
                responders.append({'name': ep.name, 'logo_url': ep.logo_url, 'rows': n_rows})

            # Columns are the union over all rows, in first-seen order, so rows
            # from endpoints with different projections stay aligned.
            columns = []
            for row in results:
                for k in row:
                    if k not in ('endpoint', 'logo_url') and k not in columns:
                        columns.append(k)
            for row in results:
                row['cells'] = [row.get(k) for k in columns]

            return render(request, 'catalogapp/results.html', {
                'query':      q,
                'results':    results,
                'columns':    columns,
                'is_ask':     any('boolean' in row for row in results),
                'responders': responders,
                'failed':     [ep.name for ep in failed],
                'total':      len(responders) + len(failed),
            })
        # Invalid parameters: nothing is dispatched, the user sees why.
        return render(request, 'catalogapp/results.html',
                      {'errors': form.errors}, status=400)

    # 3) Otherwise (GET) just show the form
    else:
        # <-- only pass params here as well
        form = QueryForm(params=entry['params'])

    # 4) Always include `id` in the context so your hidden <input> gets populated
    return render(request, 'catalogapp/query.html', {
        'description': entry['description'],
        'template':    entry['template'],
        'form':        form,
        'id':          raw_id,
    })
    

        
@login_required
def run_analytics(request):
    key = request.POST.get('query_key')
    entries = catalog()
    entry = next((e for e in entries if e.get('analytics_key') == key), None)
    if not entry:
        return JsonResponse({'results': [], 'responders': [], 'failed': []})

    # 1) Validate parameters, then build the SPARQL string
    form = QueryForm(request.POST, params=entry['params'])
    if not form.is_valid():
        return JsonResponse({'error': 'Invalid parameters', 'errors': form.errors}, status=400)
    q = prefixes + entry['template']
    for param, v in form.cleaned_data.items():
        q = q.replace(f'{{{param}}}', v)

    # 2) If KL-divergence, delegate to each endpoint
    if key == 'klDiv':
        results = []
        responders = []
        answered, down = dispatch({
            'query':        q,
            'analytics_key': key,
        }, accept='application/json')
        failed = [ep.name for ep in down]
        for ep, data in answered:
            if not isinstance(data, dict):
                failed.append(ep.name)
                continue
            results.append({'endpoint': ep.name, 'kl_divergence': data.get('kl_divergence')})
            responders.append({'name': ep.name, 'logo_url': ep.logo_url})
        return JsonResponse({'results': results, 'responders': responders, 'failed': failed})

    # 3) Fallback: ageDist local aggregation
    raw_bindings = []
    responders = []
    answered, down = dispatch({'query': q})
    failed = [ep.name for ep in down]
    for ep, data in answered:
        try:
            bds = data.get('results', {}).get('bindings', []) or data.get('results') if isinstance(data.get('results'), list) else []
            for bd in bds:
                def norm(k):
                    v = bd.get(k)
                    return (isinstance(v, dict) and v.get('value')) or v
                raw_bindings.append({
                    'bracket':  norm('bracket'),
                    'n':        norm('n')
                })
            responders.append({'name': ep.name, 'logo_url': ep.logo_url})
        except Exception:
            failed.append(ep.name)
    agg = {}
    for r in raw_bindings:
        b = r.get('bracket')
        c = int(r.get('n') or 0)
        agg[b] = agg.get(b, 0) + c
    results = [{'bracket': label, 'n': agg[label]} for label in sorted(agg.keys(), key=lambda s: int(''.join(filter(str.isdigit, s)) or 0))]
    return JsonResponse({'results': results, 'responders': responders, 'failed': failed})


@require_POST
@login_required
def train_model(request):
    # 1) Re-run the underlying query to get {evType, sex, endpoint, ageOn}
    form = QueryForm(request.POST, params=['disease'])
    if not form.is_valid():
        return JsonResponse({"error": "Invalid parameters", "errors": form.errors}, status=400)
    disease = form.cleaned_data['disease']
    if get_entry(request.POST.get('id')) is None:
        return JsonResponse({"error": "Unknown query template"}, status=400)

    df = _fetch_query_dataframe(request.POST['id'], disease)
    # catalogapp/views.py, in train_model, after you have your df:
    if 'aOns' in df.columns and 'ageOn' not in df.columns:
        df = df.rename(columns={'aOns':'ageOn'})
        
    print(df.head())

    # 2) one-hot encode categorical cols
    X = pd.get_dummies(df[['evType','sex','endpoint']], drop_first=True)
    y = df['ageOn'].astype(float)

    # 3) collect params
    params = {}
    for p in TREE_PARAMS:
        v = request.POST.get(p)
        # only include non‐empty values
        if v not in (None, ''):
            # numeric params come in as strings of digits
            params[p] = int(v) if v.isdigit() else v

    # 4) train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=params.get('random_state',42)
    )

    model = DecisionTreeRegressor(**params)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # 5) metrics
    metrics = {
        'MSE': mean_squared_error(y_test, y_pred),
        'R^2': r2_score(y_test, y_pred),
        # you can add cross-val etc.
    }

    # 6) render tree to PNG
    buf = io.BytesIO()
    fig, ax = plt.subplots(figsize=(10,6))
    plot_tree(model, feature_names=X.columns, filled=True, ax=ax)
    fig.tight_layout()
    fig.savefig(buf, format='png')
    buf.seek(0)
    tree_png = base64.b64encode(buf.read()).decode('ascii')
    plt.close(fig)

    # 7) stash model and return JSON
    model_id = str(uuid.uuid4())
    _models[model_id] = (model, X.columns)  # save feature order

    return JsonResponse({
        'metrics': metrics,
        'tree_png': tree_png,
        'model_id': model_id
    })

@require_POST
@login_required
def predict_model(request):
    model_id = request.POST['model_id']
    model, cols = _models[model_id]

    # build a one‐row DataFrame
    sample = {
      'evType': request.POST['evType'],
      'sex':     request.POST['sex'],
      'endpoint':request.POST['endpoint'],
    }
    df = pd.get_dummies(pd.DataFrame([sample]))
    # ensure all columns
    for c in cols:
        if c not in df: df[c] = 0
    df = df[cols]

    pred = model.predict(df)[0]
    return JsonResponse({'predicted': float(pred)}) 


def _fetch_query_dataframe(query_id, disease):
    """
    Run the catalog query with id=query_id (expects only {disease}),
    fan it out to all endpoints, collect the SELECT bindings,
    and return a pandas.DataFrame of the results.
    """
    entry = get_entry(query_id)
    if entry is None:
        raise ValueError(f"unknown template key {query_id!r}")

    # 1) Grab the raw template
    raw_template = entry['template']

    # 2) Build the full SPARQL string
    #    (we only know {disease} is needed for this query)
    sparql = prefixes + raw_template.replace("{disease}", disease)
    # (for debugging—log this)
    print("TRAIN_MODEL SPARQL:\n", sparql)

    rows = []
    for ep in Endpoint.objects.all():
        url = ep.url.rstrip("/") + "/sparql-protected/"
        try:
            resp = requests.post(
                url,
                data=urllib.parse.urlencode({
                    "query":    sparql
                }, quote_via=urllib.parse.quote),
                headers={
                    "Accept": "application/sparql-results+json",
                    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"
                },
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            # (for debugging—log the first endpoint’s JSON)
            print(f"TRAIN_MODEL raw response from {ep.name}:", data)

            # Only handle SELECT-style bindings
            head = data.get("head", {}).get("vars", [])
            for bd in data.get("results", {}).get("bindings", []):
                # Extract each bound variable
                row = {v: bd[v]["value"] for v in head if v in bd}
                row["endpoint"] = ep.name
                rows.append(row)

        except Exception as ex:
            # log failures
            print(f"TRAIN_MODEL: endpoint {ep.name} failed with {ex}")
            continue

    df = pd.DataFrame(rows)
    print("TRAIN_MODEL: built DataFrame with columns:", df.columns.tolist(),
          "and", len(df), "rows")
    return df