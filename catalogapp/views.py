# catalogapp/views.py
import duckdb
import requests
from urllib.parse import urlparse, urljoin
import urllib.parse
from django.shortcuts      import render, redirect, get_object_or_404
from django.conf           import settings
from django.contrib        import messages
from django.views.decorators.http import require_http_methods
from requests_toolbelt.utils import dump
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import json
from functools import wraps
import numpy as np
from math import log

from .queries              import catalog
from .models               import Endpoint
from .forms                import QueryForm, EndpointForm
from .forms import QUESTION_CHOICES
import base64
import io
import pandas as pd
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from sklearn.tree import DecisionTreeRegressor, plot_tree
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_squared_error, r2_score
import uuid
import matplotlib.pyplot as plt

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
    eps = []
    for ep in Endpoint.objects.all():
        parsed = urlparse(ep.url)

        # 1) take scheme + netloc
        base_netloc = f"{parsed.scheme}://{parsed.netloc}"

        # 2) take whatever “path” was in the original URL (e.g. "/api3"),
        #    but strip any trailing slash so we don’t get "//sparql‐protected"
        prefix = parsed.path.rstrip("/")

        # 3) build the "sparql‐protected" URL under that path:
        #    e.g. "http://tdn.dei.unipd.it" + "/api3" + "/sparql‐protected/"
        protected_path = prefix + "/sparql-protected/"

        # urljoin will handle a missing leading slash in protected_path,
        # but since we constructed protected_path with a leading slash
        # (because parsed.path always starts with "/"), urljoin is straightforward:
        base = urljoin(base_netloc, protected_path)

        try:
            resp = requests.get(base, timeout=2)
            # if the SPARQL‐protected URL exists but only accepts POST/PUT/etc,
            # you’ll often get 405 Method Not Allowed, which we treat as “online”
            ep.online = (resp.status_code == 405)
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
    for idx, e in enumerate(entries):
        e["id"] = idx

    return render(request, "catalogapp/catalog.html", {
        "catalog": entries,
        "QUESTION_CHOICES": QUESTION_CHOICES,
        # add this line:
        "QUESTION_CHOICES_JSON": json.dumps(QUESTION_CHOICES),
    })


@login_required
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


            q = prefixes + q

            # Mask out the original template markers so they don’t get sent along
            entry['template'] = entry['template'].replace('<{', '**<').replace('}>', '>**')
            results = []

            for ep in Endpoint.objects.all():
                url = ep.url.rstrip('/') + '/sparql-protected/'

                try:
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
                    # Raise an exception if status is 4xx/5xx
                    resp.raise_for_status()

                    data = resp.json()

                    # Handle ASK, SELECT, or empty/unauthorized cases
                    if 'boolean' in data:
                        results.append({
                            'endpoint': ep.name,
                            'logo_url': ep.logo.url,
                            'boolean':  data['boolean']
                        })

                    elif 'head' in data and 'results' in data:
                        head = data['head']['vars']
                        for bd in data['results']['bindings']:
                            row = {}
                            for v in head:
                                # only pull bd[v]['value'] if it exists
                                if v in bd:
                                    row[v] = bd[v]['value']
                                else:
                                    row[v] = None
                            row['endpoint'] = ep.name
                            row['logo_url']  = ep.logo.url
                            results.append(row)

                    elif 'results' in data:
                        # Known template but no results (or unauthorized)
                        results.append({
                            'endpoint': ep.name,
                            'logo_url': ep.logo.url,
                            'rows':     []
                        })

                    else:
                        # Unexpected JSON shape
                        results.append({
                            'endpoint': ep.name,
                            'logo_url': ep.logo.url,
                            'error':    'Invalid response'
                        })

                except requests.RequestException:
                    # If anything goes wrong (timeout, HTTP error, connection error),
                    # just skip this endpoint.
                    continue
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
        'form':        form,
        'id':          raw_id,
    })
    

        
def run_analytics(request):
    """
    Run the same fan-out SPARQL logic as in query_view, but return
    either:
      • { results: [ {bucket,n}, … ], responders: […], failed: […] }
        for ageDist
      • { distribution_true: […], distribution_false: […],
          kl_divergence: float, responders: […], failed: […] }
        for klDiv
    """
    key = request.POST.get('query_key')
    entries = catalog()
    entry = next((e for e in entries if e.get('analytics_key') == key), None)
    if not entry:
        return JsonResponse({"results": [], "responders": [], "failed": []})

    # 1) Build SPARQL string
    q = prefixes + entry['template']
    for param in entry['params']:
        v = request.POST.get(param) or ''
        q = q.replace(f'{{{param}}}', v)

    entry['template'] = entry['template'].replace('<{', '**<').replace('}>', '>**')

    # 2) Fan-out to endpoints, collect raw bindings
    raw_bindings = []
    responders = []
    failed = []

    for ep in Endpoint.objects.all():
        url = ep.url.rstrip('/') + '/sparql-protected/'
        try:
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
            resp.raise_for_status()
            data = resp.json()

            # Extract SPARQL bindings
            if isinstance(data.get('results'), list):
                bds = data['results']
            elif data.get('results', {}).get('bindings'):
                bds = data['results']['bindings']
            else:
                bds = []

            # Normalize and collect
            for bd in bds:
                def norm(k):
                    v = bd.get(k)
                    return (isinstance(v, dict) and v.get('value')) or v
                raw_bindings.append({
                    'b':        norm('b'),
                    'ageOn':    norm('ageOn'),
                    'bracket':  norm('bracket'),
                    'n':        norm('n'),
                    'endpoint': ep.name,
                    'logo_url': ep.logo.url,
                })

            responders.append({
                'name':     ep.name,
                'logo_url': ep.logo.url
            })


        except Exception:
            failed.append(ep.name)
            continue

    # 3) Branch on analytics key
    if key == 'klDiv':
        # Split ages by bulbar flag
        #ages_true  = [int(r['ageOn']) for r in raw_bindings if str(r['b']).lower() == 'true']
        #ages_false = [int(r['ageOn']) for r in raw_bindings if str(r['b']).lower() == 'false']
        
        # Split ages by bulbar flag, parsing as float
        if key == 'klDiv':
            ages_true, ages_false = [], []
            for r in raw_bindings:
                try:
                    age = float(r['ageOn'])
                except (TypeError, ValueError):
                    continue
                if str(r['b']).lower() == 'true':
                    ages_true.append(age)
                else:
                    ages_false.append(age)


        all_ages = ages_true + ages_false
        if not all_ages:
            return JsonResponse({
                "distribution_true": [],
                "distribution_false": [],
                "kl_divergence":     None,
                "responders":        responders,
                "failed":            failed
            })

        # Shared bin edges
        bins = np.linspace(min(all_ages), max(all_ages), num=11)
        p_counts, _     = np.histogram(ages_true,  bins=bins)
        q_counts, edges = np.histogram(ages_false, bins=bins)

        # Convert to PMFs with smoothing
        eps = 1e-9
        total = (p_counts + q_counts + 2*eps).sum()
        p = (p_counts + eps) / total
        q = (q_counts + eps) / total

        # Compute KL divergence D(P‖Q)
        kl = float((p * np.log(p / q)).sum())

        # Build JSON-safe distributions
        dist_true = [
            {"range": f"{edges[i]:.0f}–{edges[i+1]:.0f}", "p": float(p[i])}
            for i in range(len(p))
        ]
        dist_false = [
            {"range": f"{edges[i]:.0f}–{edges[i+1]:.0f}", "p": float(q[i])}
            for i in range(len(q))
        ]

        return JsonResponse({
            "distribution_true":  dist_true,
            "distribution_false": dist_false,
            "kl_divergence":      kl,
            "responders":         responders,
            "failed":             failed
        })

    # Fallback: ageDist (merge brackets → counts)
    agg = {}
    for r in raw_bindings:
        b = r.get('bracket')
        c = int(r.get('n') or 0)
        agg[b] = agg.get(b, 0) + c

    # **Return bracket & n** so the existing JS still works
    results = [
        {"bracket": label, "n": agg[label]}
        for label in sorted(
            agg.keys(),
            key=lambda s: int(''.join(filter(str.isdigit, s)) or 0)
        )
    ]

    return JsonResponse({
        "results":    results,
        "responders": responders,
        "failed":     failed
    })
    
@require_POST
@login_required
def train_model(request):
    # 1) Re-run the underlying query to get {evType, sex, endpoint, ageOn}
    disease = request.POST.get("disease")
    if not disease:
        return JsonResponse({"error": "Missing disease parameter"}, status=400)

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
    entries = catalog()
    entry   = entries[int(query_id)]

    # 1) Grab the raw template
    raw_template = entry['template']

    # 2) Build the full SPARQL string
    #    (we only know {disease} is needed for this query)
    sparql = prefixes + raw_template.replace("{disease}", disease)
    # (for debugging—log this)
    print("TRAIN_MODEL SPARQL:\n", sparql)

    # 3) Mask the template markers *locally* for the POST body
    masked_template = raw_template.replace("<{", "**<").replace("}>", ">**")

    rows = []
    for ep in Endpoint.objects.all():
        url = ep.url.rstrip("/") + "/sparql-protected/"
        try:
            resp = requests.post(
                url,
                data=urllib.parse.urlencode({
                    "template": masked_template,
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