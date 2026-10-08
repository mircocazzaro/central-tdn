"""Compose a query: visual builder and SPARQL editor answered by rewriting.

The user's query never reaches the endpoints. Central rewrites it into
catalog templates (see catalogapp/rewriting), runs those and computes the
rest itself.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from rdflib import URIRef, Variable
from rdflib.namespace import RDF

from .forms import DISEASE_CHOICES, QUESTION_CHOICES
from .queries import PREFIXES_FOR_BUILDER
from .rewriting import ir, mediator, minicon, service

MAX_QUERY_CHARS = 20000


@login_required
def compose_page(request):
    release, templates = service.published_templates()
    return render(request, "catalogapp/compose.html", {
        "release": release,
        "n_templates": len(templates),
        "n_derived": sum(t.derived for t in templates),
        "prologue": PREFIXES_FOR_BUILDER,
    })


def vocabulary(templates):
    """Classes, and per class the properties seen in catalog patterns.

    A property target is another class, a value (literal or IRI), or a
    parameter (a constant the user must choose, with its grammar).
    """
    classes = {}

    def cls_of(var, triples):
        for s, p, o in triples:
            if s == var and p == RDF.type and isinstance(o, URIRef):
                return o
        return None

    for t in templates:
        for s, p, o in t.triples:
            if not isinstance(s, Variable) or isinstance(p, Variable) or p == RDF.type:
                continue
            c = cls_of(s, t.triples)
            if c is None:
                continue
            props = classes.setdefault(str(c), {})
            entry = props.setdefault(str(p), {"iri": str(p), "label": ir.render_iri(p),
                                              "classes": set(), "value": False, "params": set(),
                                              "constants": set()})
            if isinstance(o, Variable) and str(o).startswith(ir.PARAM_PREFIX):
                slot = t.slots.get(str(o)[len(ir.PARAM_PREFIX):])
                if slot:
                    entry["params"].add((slot.kind, slot.wire, slot.prefix, slot.suffix))
            elif isinstance(o, Variable):
                oc = cls_of(o, t.triples)
                if oc is not None:
                    entry["classes"].add(str(oc))
                else:
                    entry["value"] = True
            else:
                entry["constants"].add(ir.render_term(o))
    for t in templates:
        for s, p, o in t.triples:
            if p == RDF.type and isinstance(o, URIRef):
                classes.setdefault(str(o), {})
    out = []
    for c, props in sorted(classes.items()):
        out.append({"iri": c, "label": ir.render_iri(URIRef(c)), "properties": [
            {**{k: v for k, v in e.items() if k not in ("classes", "params", "constants")},
             "classes": sorted(e["classes"]),
             "params": [{"kind": k, "wire": w, "prefix": pr, "suffix": su}
                        for k, w, pr, su in sorted(e["params"], key=str)],
             "constants": sorted(e["constants"])}
            for _, e in sorted(props.items())]})
    return out


@login_required
@require_GET
def compose_vocabulary(request):
    _, templates = service.published_templates()
    return JsonResponse({
        "classes": vocabulary(templates),
        "choices": {"disease": DISEASE_CHOICES, "alsfrs_question": QUESTION_CHOICES},
    })


def _sparql(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
        sparql = str(body.get("sparql", ""))
    except (UnicodeDecodeError, ValueError, AttributeError):
        sparql = ""
    return sparql[:MAX_QUERY_CHARS + 1]


def _planned(request):
    release, templates = service.published_templates()
    if release is None:
        return None, JsonResponse({"error": "No catalog has been published yet: publish it from "
                                            "the Endpoints page first."}, status=409)
    sparql = _sparql(request)
    if not sparql.strip() or len(sparql) > MAX_QUERY_CHARS:
        return None, JsonResponse({"error": "Write a query first."}, status=400)
    try:
        p, _ = service.plan(sparql, templates)
    except ir.Unsupported as exc:
        return None, JsonResponse({"error": f"Not supported: {exc}.", "reasons": []}, status=400)
    except minicon.NoRewriting as exc:
        return None, JsonResponse({"error": "The catalog cannot answer this query.",
                                   "reasons": exc.reasons}, status=422)
    return p, None


@login_required
@require_POST
def compose_plan(request):
    p, err = _planned(request)
    if err:
        return err
    return JsonResponse({"plan": service.describe(p)})


@login_required
@require_POST
def compose_run(request):
    p, err = _planned(request)
    if err:
        return err
    res = mediator.execute(p)
    return JsonResponse({
        "plan": service.describe(p),
        "columns": res.columns,
        "rows": res.rows,
        "boolean": res.boolean,
        "calls": res.calls,
        "responders": res.responders,
        "failed": res.failed,
    })
