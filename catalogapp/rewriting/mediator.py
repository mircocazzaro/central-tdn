"""Execution of a plan: catalog templates on the endpoints, the rest on Central.

Every template of the plan is sent, instantiated with its parameters, to all
endpoints in parallel (``dispatch``). Central then computes, in an in-memory
DuckDB database:

- per endpoint, the join of the template results on the shared query
  variables (results of different endpoints are never joined: patient IRIs
  are local to each endpoint), the selections on constants and the query
  FILTERs;
- the projection, or the aggregates per endpoint and over all endpoints
  together ("All endpoints"), which is exact because Central has the rows.

An endpoint that does not answer one of the templates is left out of the
result and reported. A whole-match plan runs one template, aggregates
included, and returns the endpoint answers as they are.
"""
from concurrent.futures import ThreadPoolExecutor

import duckdb
from rdflib import Literal, URIRef, Variable
from rdflib.namespace import XSD

from ..dispatch import dispatch as default_dispatch
from ..queries import PROLOGUE

ALL = "All endpoints"
NUMERIC_TYPES = {str(x) for x in (XSD.integer, XSD.decimal, XSD.double, XSD.float, XSD.int,
                                  XSD.long, XSD.short, XSD.nonNegativeInteger, XSD.positiveInteger)}
MAX_ROWS = 50000


def instantiate(call):
    text = call.template.text
    for name, value in call.bindings.items():
        text = text.replace("{%s}" % name, value)
    return PROLOGUE + text


def _q(name):
    return '"' + str(name).replace('"', '""') + '"'


class Result:
    def __init__(self):
        self.columns = []
        self.rows = []          # dicts; key 'endpoint'
        self.boolean = None     # ASK: {endpoint: bool}
        self.calls = []         # per call: {"key", "sparql", "rows": {endpoint: n}}
        self.responders = []
        self.failed = []


def _bindings(data):
    if not isinstance(data, dict):
        return None
    if "boolean" in data:
        return data["boolean"]
    res = data.get("results")
    if not isinstance(res, dict):
        return None
    return res.get("bindings", [])


def run_calls(plan, dispatch=default_dispatch):
    """``{call_index: {endpoint_name: bindings | bool}}`` and the set of all endpoint names."""
    def one(call):
        answered, failed = dispatch({"query": instantiate(call)})
        out = {}
        for ep, data in answered:
            b = _bindings(data)
            if b is not None:
                out[ep.name] = b
        names = {ep.name for ep, _ in answered} | {ep.name for ep in failed}
        return out, names

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(plan.calls)))) as pool:
        results = list(pool.map(one, plan.calls))
    names = set().union(*(n for _, n in results)) if results else set()
    return {i: r for i, (r, _) in enumerate(results)}, names


def execute(plan, dispatch=default_dispatch):
    per_call, names = run_calls(plan, dispatch)
    res = Result()
    complete = sorted(n for n in names if all(n in per_call[i] for i in per_call))
    res.responders = complete
    res.failed = sorted(names - set(complete))
    for i, call in enumerate(plan.calls):
        res.calls.append({"key": call.template.key, "level": call.template.level,
                          "sparql": instantiate(call),
                          "rows": {ep: (len(v) if isinstance(v, list) else v)
                                   for ep, v in sorted(per_call[i].items())}})
    if plan.kind == "whole":
        _whole(plan, per_call[0], complete, res)
    else:
        _rewrite(plan, per_call, complete, res)
    return res


# --- whole match ------------------------------------------------------------

def _whole(plan, answers, complete, res):
    q = plan.query
    if q.form == "ASK":
        res.boolean = {ep: bool(answers[ep]) for ep in complete}
        res.boolean[ALL] = any(res.boolean.values())
        return
    inv = {str(k): str(v) for k, v in plan.aliases.items()}
    res.columns = [str(v) for v in q.projection]
    for ep in complete:
        for b in answers[ep]:
            row = {"endpoint": ep}
            for k, cell in b.items():
                row[inv.get(k, k)] = cell.get("value")
            res.rows.append(row)


# --- rewriting --------------------------------------------------------------

def _sql_value(term):
    if isinstance(term, Literal):
        if str(term.datatype) in NUMERIC_TYPES:
            return float(term), True
        return str(term), False
    return str(term), False


def _expr_sql(e, numeric, params):
    if isinstance(e, Variable):
        return _q(e), numeric.get(str(e), False)
    if isinstance(e, (Literal, URIRef)):
        v, isnum = _sql_value(e)
        params.append(v)
        return "?", isnum
    op = e[0]
    if op in ("and", "or"):
        return f"({_expr_sql(e[1], numeric, params)[0]} {op.upper()} {_expr_sql(e[2], numeric, params)[0]})", False
    if op == "not":
        return f"(NOT {_expr_sql(e[1], numeric, params)[0]})", False
    _, cmp, left, right = e
    lp, rp = [], []
    ls, ln = _expr_sql(left, numeric, lp)
    rs, rn = _expr_sql(right, numeric, rp)
    if ln or rn:   # numeric comparison
        ls = ls if not isinstance(left, Variable) else f"TRY_CAST({ls} AS DOUBLE)"
        rs = rs if not isinstance(right, Variable) else f"TRY_CAST({rs} AS DOUBLE)"
    params += lp + rp
    return f"({ls} {'<>' if cmp == '!=' else cmp} {rs})", False


def _rewrite(plan, per_call, complete, res):
    q = plan.query
    con = duckdb.connect()
    try:
        numeric = {}
        iri = {}       # columns holding IRIs: local to each endpoint
        tables = []
        for i, call in enumerate(plan.calls):
            cols = sorted({str(v) for v in call.columns.values()})
            sel = [(str(v), c) for v, c in call.selections]
            eqs = [(str(v), str(qv)) for v, qv in call.equalities]
            helper = [f"__s{j}" for j in range(len(sel))] + [f"__e{j}" for j in range(len(eqs))]
            con.execute(f"CREATE TABLE c{i} (__ep VARCHAR"
                        + "".join(f", {_q(c)} VARCHAR" for c in cols + helper) + ")")
            src = {str(qv): str(v) for v, qv in call.columns.items()}
            rows = []
            for ep in complete:
                for b in per_call[i][ep][:MAX_ROWS]:
                    row = [ep]
                    for c in cols:
                        cell = b.get(src[c]) or {}
                        row.append(cell.get("value"))
                        dt = cell.get("datatype")
                        if cell:
                            numeric[c] = numeric.get(c, True) and dt in NUMERIC_TYPES
                            iri[c] = iri.get(c, False) or cell.get("type") == "uri"
                    for v, _ in sel:
                        row.append((b.get(v) or {}).get("value"))
                    for v, _ in eqs:
                        row.append((b.get(v) or {}).get("value"))
                    rows.append(row)
            if rows:
                con.executemany(f"INSERT INTO c{i} VALUES ({', '.join('?' * len(rows[0]))})", rows)
            where, params = [], []
            for j, (_, const) in enumerate(sel):
                v, isnum = _sql_value(const)
                where.append(f"TRY_CAST(__s{j} AS DOUBLE) = ?" if isnum else f"__s{j} = ?")
                params.append(v)
            for j, (_, qv) in enumerate(eqs):
                where.append(f"__e{j} = {_q(qv)}")
            tables.append((f"(SELECT __ep{''.join(', ' + _q(c) for c in cols)} FROM c{i}"
                           + (f" WHERE {' AND '.join(where)}" if where else "") + f") t{i}",
                           set(cols), params))
        # join on __ep and shared variables
        sql_from, params, have = tables[0][0], list(tables[0][2]), set(tables[0][1])
        for frag, cols, p in tables[1:]:
            using = ["__ep"] + sorted(have & cols)
            sql_from += f" JOIN {frag} USING ({', '.join(_q(c) if c != '__ep' else c for c in using)})"
            params += p
            have |= cols
        conds = []
        for f in q.filters:
            s, _ = _expr_sql(f, numeric, params)
            conds.append(s)
        base = f"SELECT * FROM {sql_from}" + (f" WHERE {' AND '.join(conds)}" if conds else "")
        con.execute(f"CREATE TABLE r AS {base}", params)

        if q.form == "ASK":
            hits = {ep for (ep,) in con.execute("SELECT DISTINCT __ep FROM r").fetchall()}
            res.boolean = {ep: ep in hits for ep in complete}
            res.boolean[ALL] = bool(hits)
            return
        res.columns = [str(v) for v in q.projection]
        order = ""
        if q.order_by:
            order = " ORDER BY " + ", ".join(_q(v) + (" DESC" if d else "") for v, d in q.order_by)
        limit = (f" LIMIT {int(q.limit)}" if q.limit is not None else "") + \
                (f" OFFSET {int(q.offset)}" if q.offset else "")
        if q.aggregates or q.group_by:
            def agg_exprs(total):
                exprs = []
                for v in q.projection:
                    a = next((a for a in q.aggregates if a.alias == v), None)
                    if a is None:
                        exprs.append(f"{_q(v)} AS {_q(v)}")
                        continue
                    if a.var is None:
                        inner = "*"
                    elif a.fn in ("SUM", "AVG") or (a.fn in ("MIN", "MAX") and numeric.get(str(a.var))):
                        inner = f"TRY_CAST({_q(a.var)} AS DOUBLE)"
                    elif total and a.distinct and iri.get(str(a.var)):
                        # the same IRI on two endpoints names two different entities
                        inner = f"(__ep, {_q(a.var)})"
                    else:
                        inner = _q(a.var)
                    d = "DISTINCT " if a.distinct and a.var is not None else ""
                    exprs.append(f"{a.fn.lower()}({d}{inner}) AS {_q(v)}")
                return exprs
            exprs = agg_exprs(False)
            g = [_q(v) for v in q.group_by]
            per_ep = (f"SELECT __ep AS endpoint, {', '.join(exprs)} FROM r "
                      f"GROUP BY {', '.join(['__ep'] + g)}")
            total = (f"SELECT '{ALL}' AS endpoint, {', '.join(agg_exprs(True))} FROM r"
                     + (f" GROUP BY {', '.join(g)}" if g else ""))
            if not g:
                # no grouping: one row per endpoint that answered, even if empty
                per_ep = (f"SELECT e.ep AS endpoint, {', '.join(exprs)} "
                          f"FROM (SELECT unnest(?::VARCHAR[]) AS ep) e LEFT JOIN r ON r.__ep = e.ep "
                          f"GROUP BY e.ep")
                cur = con.execute(f"SELECT * FROM ({per_ep}) UNION ALL SELECT * FROM ({total})",
                                  [complete])
            else:
                cur = con.execute(f"SELECT * FROM ({per_ep}{order}{limit}) UNION ALL "
                                  f"SELECT * FROM ({total}{order}{limit})")
        else:
            cols = ", ".join(_q(v) for v in q.projection)
            cur = con.execute(f"SELECT {'DISTINCT ' if q.distinct else ''}__ep AS endpoint, {cols} "
                              f"FROM r{order}{limit}")
        names = [d[0] for d in cur.description]
        for r in cur.fetchall():
            row = dict(zip(names, r))
            for k, v in row.items():
                if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
                    row[k] = int(v)
            res.rows.append(row)
    finally:
        con.close()
