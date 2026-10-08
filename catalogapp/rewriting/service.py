"""Entry points used by the views: templates of the published catalog, planning."""
import threading

from ..models import CatalogRelease
from . import admission, ir, minicon

_cache = {"version": None, "templates": []}
_lock = threading.Lock()


def templates_of(document):
    out = []
    for e in document.get("templates", []):
        try:
            out.append(ir.parse_template(e))
        except ir.Unsupported:
            continue   # not even parseable: cannot take part in a rewriting
    return out


def published_templates():
    """Parsed templates of the latest catalog release (what endpoints accept)."""
    release = CatalogRelease.objects.order_by("-version").first()
    if release is None:
        return None, []
    with _lock:
        if _cache["version"] != release.version:
            _cache.update(version=release.version, templates=templates_of(release.document))
        return release, _cache["templates"]


def plan(sparql, templates):
    """``(plan, query_ir)``; raises ir.Unsupported or minicon.NoRewriting."""
    q = ir.parse_query(sparql)
    p = minicon.rewrite(q, templates)
    ok, reason = admission.admissible(p)
    if not ok:
        raise minicon.NoRewriting([reason])
    return p, q


def describe(p):
    """Plan graph for the UI: nodes and edges, as in the rewriting demo."""
    from .mediator import instantiate
    nodes, edges = [], []
    q = p.query
    for i, c in enumerate(p.calls):
        nodes.append({"id": f"v{i}", "type": "VIEW", "label": c.template.key,
                      "level": c.template.level, "derived": c.template.derived,
                      "description": c.template.description,
                      "bindings": c.bindings,
                      "columns": {str(k): str(v) for k, v in c.columns.items()},
                      "selections": [(str(k), ir.render_term(v)) for k, v in c.selections],
                      "sparql": instantiate(c)})
    last = [f"v{i}" for i in range(len(p.calls))]
    if p.kind == "whole":
        nodes.append({"id": "out", "type": "RESULT",
                      "label": "Template answers as they are (aggregates computed by each endpoint)"})
        edges += [{"from": x, "to": "out"} for x in last]
        return {"kind": p.kind, "level": admission.plan_level(p), "nodes": nodes, "edges": edges}
    steps = []
    if len(p.calls) > 1:
        shared = sorted({str(v) for c in p.calls for v in c.columns.values()
                         if sum(v in d.columns.values() for d in p.calls) > 1})
        steps.append(("JOIN", "Join per endpoint on " + (", ".join("?" + s for s in shared) or "(cross product)")))
    if q.filters:
        steps.append(("FILTER", "FILTER " + " && ".join(_expr_text(f) for f in q.filters)))
    if q.aggregates or q.group_by:
        aggs = ", ".join(f"{a.fn}({'DISTINCT ' if a.distinct else ''}{'?' + str(a.var) if a.var else '*'})"
                         f" AS ?{a.alias}" for a in q.aggregates)
        g = " ".join("?" + str(v) for v in q.group_by)
        steps.append(("AGGREGATE", f"{aggs}" + (f" GROUP BY {g}" if g else "")
                      + " — per endpoint and over all endpoints"))
    if q.form == "ASK":
        steps.append(("ASK", "Non-empty?"))
    else:
        steps.append(("PROJECT", "SELECT " + " ".join("?" + str(v) for v in q.projection)
                      + (" ORDER BY …" if q.order_by else "") + (f" LIMIT {q.limit}" if q.limit else "")))
    for j, (t, label) in enumerate(steps):
        nid = f"s{j}"
        nodes.append({"id": nid, "type": t, "label": label})
        edges += [{"from": x, "to": nid} for x in last]
        last = [nid]
    return {"kind": p.kind, "level": admission.plan_level(p), "nodes": nodes, "edges": edges}


def _expr_text(e):
    if isinstance(e, tuple):
        if e[0] in ("and", "or"):
            return f"({_expr_text(e[1])} {'&&' if e[0] == 'and' else '||'} {_expr_text(e[2])})"
        if e[0] == "not":
            return f"!{_expr_text(e[1])}"
        return f"{_expr_text(e[2])} {e[1]} {_expr_text(e[3])}"
    return ir.render_term(e)
