"""Compose page: vocabulary, plan and run endpoints, legacy catalog unchanged."""
import json
import re
import subprocess
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase

from catalogapp import network
from catalogapp.models import CatalogRelease
from catalogapp.rewriting import mediator, service

from .test_rewriting import EPS, FakeNetwork

Q = """SELECT ?sex (COUNT(DISTINCT ?p) AS ?n) WHERE {
  ?p a bto:Patient ; bto:hasDisease NCIT:C34373 ; bto:sex ?sex ; bto:undergo ?e .
  ?e a bto:Onset ; bto:ageOnset ?a . FILTER(?a >= 40) } GROUP BY ?sex"""


class ComposeTests(TestCase):
    def setUp(self):
        self.c = Client()
        User.objects.create_user("u", password="pw-123456")
        self.c.login(username="u", password="pw-123456")
        service._cache["version"] = None

    def publish(self):
        release, _ = network.current_catalog_release()
        return release

    def post(self, url, sparql):
        return self.c.post(url, json.dumps({"sparql": sparql}), content_type="application/json")

    def test_requires_login_and_published_catalog(self):
        self.assertEqual(Client().get("/catalog/compose/").status_code, 302)
        self.assertEqual(self.post("/catalog/compose/plan/", Q).status_code, 409)

    def test_release_contains_derived_hidden_from_legacy_catalog(self):
        release = self.publish()
        keys = [t["key"] for t in release.document["templates"]]
        self.assertTrue(any(k.startswith("d_") for k in keys))
        page = self.c.get("/catalog/").content.decode()
        self.assertNotIn("d_", re.search(r'id="catalogData"[^>]*>(.*?)</script>', page, re.S).group(1))
        self.assertIn("Derived", json.dumps(release.document))

    def test_vocabulary(self):
        self.publish()
        voc = self.c.get("/catalog/compose/vocabulary/").json()
        patient = next(c for c in voc["classes"] if c["label"] == "bto:Patient")
        props = {p["label"]: p for p in patient["properties"]}
        self.assertEqual(props["bto:hasDisease"]["params"][0]["wire"], "disease")
        self.assertIn("https://w3id.org/brainteaser/ontology/schema/Onset", props["bto:undergo"]["classes"])
        self.assertTrue(props["bto:sex"]["value"])
        self.assertIn("disease", voc["choices"])

    def test_plan_and_run(self):
        self.publish()
        r = self.post("/catalog/compose/plan/", Q)
        self.assertEqual(r.status_code, 200)
        plan = r.json()["plan"]
        self.assertEqual(plan["kind"], "rewrite")
        self.assertTrue(any(n["type"] == "AGGREGATE" for n in plan["nodes"]))
        net = FakeNetwork(EPS)
        real = mediator.execute
        with mock.patch("catalogapp.compose_views.mediator.execute",
                        lambda p: real(p, dispatch=net.dispatch)):
            j = self.post("/catalog/compose/run/", Q).json()
        self.assertEqual(j["responders"], ["A", "B"])
        self.assertEqual(j["columns"], ["sex", "n"])
        self.assertIn("All endpoints", {row["endpoint"] for row in j["rows"]})
        # gli endpoint hanno ricevuto solo template del catalogo pubblicato
        texts = {t["sparql"] for t in CatalogRelease.objects.get().document["templates"]}
        for sent in net.queries:
            body = sent[len(mediator.PROLOGUE):]
            self.assertTrue(any(re.fullmatch(re.sub(r"\\\{\w+\\\}", r"[^\\s]+", re.escape(t)), body)
                                for t in texts), body)

    def test_errors(self):
        self.publish()
        r = self.post("/catalog/compose/plan/", "SELECT ?p WHERE { ?p a bto:Patient ; bto:deathDate ?d }")
        self.assertEqual(r.status_code, 422)
        self.assertTrue(any("deathDate" in x for x in r.json()["reasons"]))
        self.assertEqual(self.post("/catalog/compose/plan/", "SELECT * WHERE { ?s ?p ?o }").status_code, 400)
        self.assertEqual(self.post("/catalog/compose/plan/", "").status_code, 400)

    def test_page_script_is_valid_js(self):
        self.publish()
        html = self.c.get("/catalog/compose/").content.decode()
        js = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
        r = subprocess.run(["node", "--check", "-"], input=js, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
