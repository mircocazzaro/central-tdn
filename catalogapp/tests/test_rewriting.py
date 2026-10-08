"""Query rewriting using catalog views.

Equivalence is tested end to end: fake endpoints evaluate the instantiated
templates over synthetic RDF graphs (one per endpoint), and the result of
rewriting + mediation must equal the direct evaluation of the user query on
each graph and, for aggregates over all endpoints, on their union.
"""
import random

from django.test import SimpleTestCase
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from catalogapp.queries import PROLOGUE, RAW_TEMPLATES, federated_templates
from catalogapp.rewriting import ir, lattice, mediator, minicon, service

BTO = Namespace("https://w3id.org/brainteaser/ontology/schema/")
NCIT = Namespace("http://purl.obolibrary.org/obo/NCIT_")


def make_graph(seed, n, base=None):
    """Synthetic endpoint; ``base`` sets the IRI namespace (distinct per endpoint by default)."""
    rnd = random.Random(seed)
    base = base or f"https://endpoint{seed}.example/"
    g = Graph()
    for i in range(n):
        p = URIRef(f"{base}Patient{i}")
        g.add((p, RDF.type, BTO.Patient))
        g.add((p, BTO.hasDisease, rnd.choice([NCIT.C34373, NCIT.C34373, NCIT.C3243])))
        g.add((p, BTO.sex, Literal(rnd.choice(["male", "female"]))))
        for k in range(rnd.choice([1, 1, 2])):   # some patients have two onset events
            ev = URIRef(f"{base}eventOnset{i}_{k}")
            g.add((p, BTO.undergo, ev))
            g.add((ev, RDF.type, BTO.Onset))
            g.add((ev, BTO.ageOnset, Literal(rnd.randint(25, 80), datatype=XSD.float)))
            g.add((ev, BTO.bulbarOnset, Literal(rnd.random() < 0.3)))
            g.add((ev, BTO.eventStart, Literal(f"20{rnd.randint(10, 22)}-01-01", datatype=XSD.date)))
    return g


class Ep:
    def __init__(self, name, graph):
        self.name = name
        self.graph = graph


def to_json(result):
    if result.type == "ASK":
        return {"head": {}, "boolean": bool(result.askAnswer)}
    rows = []
    for r in result:
        b = {}
        for v in result.vars:
            x = r[v]
            if x is None:
                continue
            cell = {"type": "uri" if isinstance(x, URIRef) else "literal", "value": str(x)}
            if isinstance(x, Literal) and x.datatype:
                cell["datatype"] = str(x.datatype)
            b[str(v)] = cell
        rows.append(b)
    return {"head": {"vars": [str(v) for v in result.vars]}, "results": {"bindings": rows}}


class FakeNetwork:
    def __init__(self, endpoints, down=()):
        self.endpoints = endpoints
        self.down = set(down)
        self.queries = []

    def dispatch(self, fields):
        self.queries.append(fields["query"])
        ok, failed = [], []
        for ep in self.endpoints:
            if ep.name in self.down:
                failed.append(ep)
            else:
                ok.append((ep, to_json(ep.graph.query(fields["query"]))))
        return ok, failed


def catalog_templates():
    pub, _ = federated_templates()
    return service.templates_of({"templates": pub + lattice.derive(pub)})


TEMPLATES = catalog_templates()
EPS = [Ep("A", make_graph(1, 60)), Ep("B", make_graph(2, 45))]


def direct(sparql, graph):
    return graph.query(PROLOGUE + sparql)


def norm(v):
    if v is None:
        return None
    try:
        f = float(v)
        return round(f, 6)
    except (TypeError, ValueError):
        return str(v)


class EquivalenceTests(SimpleTestCase):
    def run_query(self, sparql, down=()):
        p, q = service.plan(sparql, TEMPLATES)
        net = FakeNetwork(EPS, down)
        return p, q, mediator.execute(p, dispatch=net.dispatch), net

    def assert_same_rows(self, sparql, res, eps=EPS, total=True):
        for ep in eps:
            exp = sorted(tuple(norm(r[v]) for v in r.labels) for r in direct(sparql, ep.graph))
            got = sorted(tuple(norm(row[c]) for c in res.columns) for row in res.rows
                         if row["endpoint"] == ep.name)
            self.assertEqual(got, exp, ep.name)
        if total:
            union = Graph()
            for ep in eps:
                union += ep.graph
            exp = sorted(tuple(norm(r[v]) for v in r.labels) for r in direct(sparql, union))
            got = sorted(tuple(norm(row[c]) for c in res.columns) for row in res.rows
                         if row["endpoint"] == mediator.ALL)
            self.assertEqual(got, exp, "all endpoints")

    def test_count_by_sex_with_filter_is_a_rewriting_and_exact(self):
        q = """SELECT ?sex (COUNT(DISTINCT ?p) AS ?n) (AVG(?age) AS ?avgAge) WHERE {
                 ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; bto:sex ?sex ; bto:undergo ?e .
                 ?e a bto:Onset ; bto:ageOnset ?age .
                 FILTER(?age < 60) } GROUP BY ?sex"""
        p, _, res, net = self.run_query(q)
        self.assertEqual(p.kind, "rewrite")
        self.assertTrue(all(c.template.key.startswith(("d_", "q")) for c in p.calls))
        self.assertTrue(all(c.bindings.get("disease") in (None, "NCIT:C34373") for c in p.calls))
        self.assert_same_rows(q, res)
        # gli endpoint hanno ricevuto solo istanze di template del catalogo
        self.assertTrue(all("NCIT:C34373" in s or "{" not in s for s in net.queries))

    def test_multiplicity_preserved_for_count_without_distinct(self):
        q = """SELECT (COUNT(*) AS ?n) (SUM(?age) AS ?s) WHERE {
                 ?p a bto:Patient ; bto:hasDisease NCIT:C3243 ; bto:undergo ?e .
                 ?e a bto:Onset ; bto:ageOnset ?age ; bto:bulbarOnset ?b . }"""
        _, _, res, _ = self.run_query(q)
        self.assert_same_rows(q, res)

    def test_rows_with_order_and_selection_on_constant(self):
        q = """SELECT ?p ?age WHERE {
                 ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; bto:sex "female" ; bto:undergo ?e .
                 ?e a bto:Onset ; bto:ageOnset ?age ; bto:bulbarOnset true . }"""
        p, _, res, _ = self.run_query(q)
        self.assertEqual(p.kind, "rewrite")
        self.assert_same_rows(q, res, total=False)

    def test_ask(self):
        q = """ASK { ?p a bto:Patient ; bto:hasDisease NCIT:C3243 ; bto:undergo ?e .
                     ?e a bto:Onset ; bto:ageOnset ?a . FILTER(?a > 79) }"""
        _, _, res, _ = self.run_query(q)
        for ep in EPS:
            self.assertEqual(res.boolean[ep.name], bool(direct(q, ep.graph).askAnswer))

    def test_instance_of_a_template_runs_it_whole(self):
        # q03_L1, with other variable names and spacing
        q = 'SELECT (COUNT(DISTINCT ?x) AS ?howMany) WHERE { ?x a bto:Patient ; bto:sex "female" ; bto:hasDisease NCIT:C34373 }'
        p, _, res, net = self.run_query(q)
        self.assertEqual((p.kind, p.calls[0].template.key, p.level), ("whole", "q03_L1", 1))
        self.assertEqual(len(net.queries), 1)
        self.assert_same_rows(q, res, total=False)

    def test_lowest_level_plan_preferred(self):
        q = 'ASK { ?p a bto:Patient ; bto:hasDisease NCIT:C34373 }'
        p, _, _, _ = self.run_query(q)
        self.assertEqual((p.kind, p.calls[0].template.key), ("whole", "q00_L0"))

    def test_same_iris_on_two_endpoints_are_different_entities(self):
        a = Ep("A", make_graph(1, 30, base="https://same.example/"))
        b = Ep("B", make_graph(1, 30, base="https://same.example/"))
        q = "SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; bto:sex ?s }"
        p, _ = service.plan(q, TEMPLATES)
        res = mediator.execute(p, dispatch=FakeNetwork([a, b]).dispatch)
        n = {r["endpoint"]: r["n"] for r in res.rows}
        self.assertEqual(n[mediator.ALL], n["A"] + n["B"])

    def test_unanswering_endpoint_left_out(self):
        q = "SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; bto:sex ?s }"
        _, _, res, _ = self.run_query(q, down={"B"})
        self.assertEqual((res.responders, res.failed), (["A"], ["B"]))
        self.assert_same_rows(q, res, eps=[EPS[0]])


class NoRewritingTests(SimpleTestCase):
    def test_pattern_outside_the_catalog(self):
        with self.assertRaises(minicon.NoRewriting) as cm:
            service.plan("SELECT ?p ?d WHERE { ?p a bto:Patient ; bto:deathDate ?d }", TEMPLATES)
        self.assertTrue(any("bto:deathDate" in r for r in cm.exception.reasons))

    def test_parameters_must_be_bound(self):
        # hasDisease appears in templates only with a parameter (or ALS as a constant):
        # a free disease variable cannot be answered
        with self.assertRaises(minicon.NoRewriting):
            service.plan("SELECT ?d (COUNT(?p) AS ?n) WHERE { ?p a bto:Patient ; bto:hasDisease ?d ; "
                         "bto:sex ?s } GROUP BY ?d", TEMPLATES)

    def test_value_outside_grammar_is_never_sent_as_parameter(self):
        # "fe male" is not a valid sex parameter: the plan reads ?sex unbound and
        # selects on Central instead
        p, _ = service.plan('SELECT ?p WHERE { ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; '
                            'bto:sex "fe male" }', TEMPLATES)
        self.assertTrue(all("fe male" not in v for c in p.calls for v in c.bindings.values()))
        self.assertTrue(any(str(v) == "fe male" for c in p.calls for _, v in c.selections))

    def test_unsupported_sparql(self):
        for q in ("SELECT ?p WHERE { ?p a bto:Patient OPTIONAL { ?p bto:sex ?s } }",
                  "SELECT ?p WHERE { { ?p a bto:Patient } UNION { ?p a bto:Onset } }",
                  "SELECT ?p WHERE { ?p ?pred ?o }", "not sparql"):
            with self.subTest(q):
                with self.assertRaises(ir.Unsupported):
                    service.plan(q, TEMPLATES)


class LatticeTests(SimpleTestCase):
    def test_derived_levels_keys_and_visibility(self):
        pub, _ = federated_templates()
        d = lattice.derive(pub)
        by_text = {x["sparql"]: x for x in d}
        core = by_text["SELECT ?clinicalTrial WHERE {\n  ?clinicalTrial a bto:ClinicalTrial .\n"
                       "  ?clinicalTrial bto:isAboutDisease {disease} .\n}"]
        self.assertEqual((core["level"], core["parents"]), (4, ["q15_L0", "q16_L1", "q17_L4"]))
        self.assertTrue(all(x["key"].startswith("d_") and x["derived"] for x in d))
        self.assertTrue(all(len(x["key"]) <= 40 for x in d))
        # la UI legacy elenca solo i template scritti a mano
        from catalogapp.queries import catalog
        self.assertEqual({e["key"] for e in catalog()}, {e["key"] for e in RAW_TEMPLATES})

    def test_new_template_extends_lattice_and_keeps_keys(self):
        pub, _ = federated_templates()
        before = {x["key"]: x for x in lattice.derive(pub)}
        extra = dict(pub[0], key="q99_L6", level=6, sparql=(
            "SELECT ?pat ?d WHERE {\n  ?pat a bto:Patient ;\n       bto:hasDisease {disease} ;\n"
            "       bto:deathDate ?d .\n}"))
        after = {x["key"]: x for x in lattice.derive(pub + [extra])}
        self.assertTrue(set(before) < set(after))
        new = [x for k, x in after.items() if k not in before]
        self.assertTrue(new and all("deathDate" in x["sparql"] and x["level"] == 6 for x in new))
        # derivata gia' esistente che ora ha anche il nuovo padre: livello massimo
        shared = [k for k in before if "q99_L6" in after[k]["parents"]]
        self.assertTrue(shared and all(after[k]["level"] == 6 for k in shared))
        # derivate non toccate dal nuovo template: stessa chiave, stesso testo, stesso livello
        untouched = [k for k in before if "q99_L6" not in after[k]["parents"]]
        self.assertTrue(all(before[k] == after[k] for k in untouched))
