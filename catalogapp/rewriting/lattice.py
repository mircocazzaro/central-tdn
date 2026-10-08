"""Derived templates: the lattice of sub-patterns of the hand-written ones.

Hand-written templates are whole queries and seldom compose. Their basic
graph patterns are therefore factorized into smaller views, which a
rewriting can join: every subset of a template's triple patterns that

- has at least two triples,
- is connected through shared variables (parameters do not connect: they
  stand for constants),
- contains an anchor, a typing triple ``?x a <Class>``, so that no view is a
  free-floating property scan,

becomes a derived template ``SELECT <all its variables> WHERE { subset }``.
The same sub-pattern found in several templates is published once; it
inherits the most restrictive (highest) level among its parents, so adding a
template never lowers the level of an existing derived query.

Derived templates are published in the catalog like any other, so endpoints
accept them, but the legacy catalog UI does not list them: only the
rewriting uses them. The lattice is recomputed from the hand-written
templates at every catalog publication.

Keys are ``d_`` plus a hash of the canonical text, independent of the order
in which templates are processed: unchanged sub-patterns keep their key.
"""
import hashlib
from collections import defaultdict

from rdflib import URIRef, Variable
from rdflib.namespace import RDF

from .ir import PARAM_PREFIX, parse_template, render_term

MIN_TRIPLES = 2
MAX_TRIPLES = 14     # bound on the template size the lattice expands (2^n subsets)


def _is_param(t):
    return isinstance(t, Variable) and str(t).startswith(PARAM_PREFIX)


def _plain_vars(triple):
    return {x for x in (triple[0], triple[2]) if isinstance(x, Variable) and not _is_param(x)}


def _connected(triples):
    if len(triples) <= 1:
        return True
    seen, frontier = {0}, [0]
    while frontier:
        i = frontier.pop()
        vi = _plain_vars(triples[i])
        for j, t in enumerate(triples):
            if j not in seen and vi & _plain_vars(t):
                seen.add(j)
                frontier.append(j)
    return len(seen) == len(triples)


def _anchored(triples):
    return any(t[1] == RDF.type and isinstance(t[0], Variable) and isinstance(t[2], URIRef)
               for t in triples)


def subpatterns(triples):
    """Connected, anchored subsets with at least MIN_TRIPLES triples."""
    triples = [t for t in triples if not isinstance(t[1], Variable)][:MAX_TRIPLES]
    n = len(triples)
    out = []
    for mask in range(1, 1 << n):
        if bin(mask).count("1") < MIN_TRIPLES:
            continue
        sub = [triples[i] for i in range(n) if mask >> i & 1]
        if _anchored(sub) and _connected(sub):
            out.append(sub)
    return out


# --- canonical naming --------------------------------------------------------

def _local(iri):
    s = str(iri)
    s = s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    return s or "x"


def _hint(var, triples):
    for s, p, o in triples:
        if s == var and p == RDF.type and isinstance(o, URIRef):
            name = _local(o)
            return name[0].lower() + name[1:]
    for s, p, o in triples:
        if o == var:
            return "type" if p == RDF.type else _local(p)
    return "x"


def canonicalize(triples):
    """``(renamed_triples, mapping)``: variables renamed after their role."""
    plain = sorted({x for t in triples for x in (t[0], t[2])
                    if isinstance(x, Variable) and not _is_param(x)}, key=str)
    hints = {v: _hint(v, triples) for v in plain}
    by_hint = defaultdict(list)
    for v in plain:
        by_hint[hints[v]].append(v)
    mapping = {}
    for h, vs in by_hint.items():
        if len(vs) == 1:
            mapping[vs[0]] = Variable(h)
            continue

        def sig(v):
            parts = []
            for t in triples:
                if v in (t[0], t[2]):
                    parts.append(" ".join("*" if x == v else (hints.get(x, "") if isinstance(x, Variable)
                                                            else str(x)) for x in t))
            return sorted(parts)
        for i, v in enumerate(sorted(vs, key=lambda v: (sig(v), str(v)))):
            mapping[v] = Variable(h if i == 0 else f"{h}{i + 1}")
    ren = [tuple(mapping.get(x, x) for x in t) for t in triples]
    return ren, mapping


def render(triples, slots):
    """Canonical template text of a derived pattern."""
    by_var = {s.var: s for s in slots.values()}
    lines = sorted("  " + " ".join(render_term(x, by_var) for x in t) + " ." for t in triples)
    head = sorted({str(x) for t in triples for x in (t[0], t[2])
                   if isinstance(x, Variable) and not _is_param(x)})
    return "SELECT " + " ".join("?" + v for v in head) + " WHERE {\n" + "\n".join(lines) + "\n}"


def _summary(triples):
    parts = []
    for s, p, o in sorted(triples, key=str):
        if p == RDF.type:
            continue
        parts.append(_local(p))
    classes = sorted({_local(o) for s, p, o in triples if p == RDF.type and isinstance(o, URIRef)})
    return f"{'/'.join(classes)}: {', '.join(parts) or 'typing'}"


def derive(entries):
    """Derived catalog entries for the hand-written ``entries`` (published dicts)."""
    found = {}   # text -> {"level", "parents", "slots", "triples"}
    for e in entries:
        if e.get("derived"):
            continue
        t = parse_template(e)
        for sub in subpatterns(t.triples):
            ren, _ = canonicalize(sub)
            used = {str(x)[len(PARAM_PREFIX):] for tr in ren for x in tr if _is_param(x)}
            slots = {n: s for n, s in t.slots.items() if n in used}
            text = render(ren, slots)
            d = found.setdefault(text, {"level": e["level"], "parents": set(), "slots": slots,
                                        "triples": ren})
            d["level"] = max(d["level"], e["level"])
            d["parents"].add(e["key"])
    out = []
    for text, d in sorted(found.items()):
        parents = sorted(d["parents"])
        out.append({
            "key": "d_" + hashlib.sha256(text.encode()).hexdigest()[:16],
            "level": d["level"],
            "description": f"Derived ({_summary(d['triples'])}) from {', '.join(parents)}",
            "params": {n: s.wire for n, s in sorted(d["slots"].items())},
            "sha512": hashlib.sha512(text.encode()).hexdigest(),
            "sparql": text,
            "derived": True,
            "parents": parents,
        })
    return out
