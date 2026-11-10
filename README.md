# HDN Central

> **Research use only. Not a medical device.**
> This software was developed in the HEREDITARY project as a research prototype. It has not been assessed or certified under the EU Medical Device Regulation (EU) 2017/745. It must not be used to diagnose, treat, monitor or make any other decision about individual patients.

<!-- Before publication, replace every TODO and verify the release-specific statements below.
For this web application, also display the following notice in the user interface:
"Research prototype of the HEREDITARY project. Not a medical device and not for clinical use. Do not enter personal or patient data."
This README does not establish that the UI notice is already implemented. -->

## 1. Overview

HDN Central is a Django web application that dispatches catalog SPARQL queries to registered HDN endpoints (`tdn-endpoint`) and merges their answers. It manages endpoint enrollment, distributes the query catalog and ontology, and supports query composition and rewriting over the catalog.

| Field | Value |
|---|---|
| Name | HDN Central |
| Version | TODO: release tag or commit identifier |
| Type | Software / web application |
| Owner partner and contact | TODO: responsible HEREDITARY partner, maintainer name and email |
| License | TODO: SPDX identifier matching the repository LICENSE file |
| Repository and DOI | https://github.com/mircocazzaro/central-tdn; TODO: DOI, or state that none is assigned |
| Release date | TODO: date of the documented release |
| Related task or deliverable | TODO: development task and/or deliverable associated with this release |
| How to cite | TODO: software citation, publication or DOI |

## 2. Intended use

**Primary intended use.** Research on distributed querying of knowledge graphs through a shared query catalog and ontology. Central coordinates queries across registered endpoints and explores how user queries can be answered through permitted catalog queries, with endpoint-specific disclosure levels.

**Intended users.** Researchers and developers working on knowledge graphs, semantic data integration and distributed query processing, including biomedical research applications within HEREDITARY.

**Out-of-scope uses.** This release must not be used for:

- clinical diagnosis, prognosis, monitoring or treatment of individual patients;
- decisions about individuals, such as insurance, employment or access to care;
- re-identification of individuals or unauthorized linkage with other data sources;
- use with populations or data types beyond those documented and authorized for the relevant research deployment.

The application must not be used to enter personal or patient data. Endpoint data access and any permitted research use require a separately documented deployment context; this software release does not itself authorize access to data.

## 3. Data provenance

Central is query coordination software. Its behavior depends on the data available at the registered endpoints; a software release does not define a single study population.

| Dataset | Source partner | Type (public, synthetic, pseudonymized, anonymized) | Population (size, age, sex, country, condition) | Ethics approval or access conditions |
|---|---|---|---|---|
| TODO: list any datasets, fixtures, example data or database snapshots included in this release; if none, explicitly state this after verification | TODO | TODO | TODO, or N/A where appropriate | TODO |
| Endpoint data used for evaluation, if any | TODO: identify evaluation endpoints and source partners | TODO | TODO | TODO: applicable approval and access conditions, or N/A with reason |

**Release-content verification required.** TODO: inspect the repository and all released files, including fixtures, logs, database snapshots and configuration examples, before asserting: “This repository and the released files contain no personal data, pseudonymized records, identifiers or pseudonymization keys.”

Galois-mode endpoints hold public knowledge retrieved from an LLM instead of patient data. Their sources and any evaluation datasets must be documented for the specific deployment or evaluation; this README does not establish their factual accuracy or provenance.

## 4. Method

- **Algorithm or architecture.** Django mediator over registered SPARQL endpoints. Central distributes a catalog and ontology, dispatches catalog queries in parallel and merges responses. User queries are matched to catalog templates or rewritten using MiniCon. Joins are computed per endpoint; aggregates are reported per endpoint and over all endpoints.
- **Training setting.** Not applicable to Central: the described release does not train a model. Galois-mode endpoints may use an external LLM to populate their tables.
- **Privacy techniques.** The described implementation uses catalog login, a password-protected endpoint manager, signed Ed25519 network messages and endpoint-side query-level enforcement. These controls do not establish anonymization or a formal privacy guarantee. No differential privacy or secure aggregation mechanism is described in the supplied technical documentation.

Installation, network administration, query rewriting and source layout are documented after Section 8.

## 5. Performance

- **Evaluation data.** TODO: document datasets, endpoint configurations and internal or external validation for this release; if no evaluation was performed, state that explicitly.
- **Metrics and results.** TODO: provide measured results, if available, for query-answer correctness/completeness, rewriting coverage and execution time, with the evaluation configuration. No numerical performance results are provided in the supplied technical documentation.
- **Results by subgroup.** TODO: report results by endpoint, data source or other relevant grouping, if evaluated; otherwise state N/A or not evaluated, with a reason. No demographic subgroup results are provided.

## 6. Known limitations and risks

- **Generalizability.** Behavior depends on the catalog, ontology, endpoint configuration, data and disclosure levels. Performance across deployments and populations has not been established by the supplied documentation.
- **Known biases and confounders.** Endpoint coverage and disclosure settings can affect which results are returned. In Galois mode, LLM-derived knowledge may contain errors or biases. TODO: add any release-specific bias evaluation; none is supplied here.
- **Failure modes.** Unsupported SPARQL constructs are refused. A rewriting plan can return incomplete results when an endpoint answers empty for a query above its level. Endpoint failures, timeouts and differences in installed catalog or ontology versions can affect results. Queries requiring joins across endpoints cannot be answered through the documented per-endpoint join behavior. Galois endpoints may take longer because they refill their tables from an LLM.
- **Privacy risks.** Query parameters and returned answers may contain sensitive information depending on the deployment. Signed messages authenticate network messages; they do not by themselves provide confidentiality or guarantee that repeated queries cannot disclose information. The admission module currently admits every plan, leaving query-level enforcement to endpoints. TODO: document any privacy or security assessment actually performed. Membership inference and model inversion testing are not directly applicable to Central as a non-model release; this does not assess external models used by endpoints.

## 7. Responsible use and reporting

- **Terms of use.** Research use only, within the scope described in Section 2 and under the repository license identified in Section 1. The described catalog requires login and the endpoint manager requires its configured password. Do not interpret these mechanisms as evidence of registration-based access to a trained model. Use only authorized endpoints and data, protect signing keys and configure access and transport security for the deployment.
- **Contact for misuse or vulnerability reports.** TODO: maintainer or project reporting email. Do not include sensitive data or credentials in public issue reports.

## 8. Acknowledgement

Funded by the European Union under grant agreement No 101137074 (HEREDITARY). Views and opinions expressed are however those of the author(s) only and do not necessarily reflect those of the European Union or the European Health and Digital Executive Agency (HaDEA). Neither the European Union nor the granting authority can be held responsible for them.

## Installation

Requires Python 3.10+.

``​`bash
git clone https://github.com/mircocazzaro/central-tdn.git
cd central-tdn
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser      # account used to log in to the catalog
python manage.py runserver 0.0.0.0:8000
``​`

Open `http://<host>:8000/` and log in with the account you just created.

## Installation with Docker

``​`bash
git clone https://github.com/mircocazzaro/central-tdn.git
cd central-tdn
CENTRAL_ADMIN_PASSWORD='choose-one' docker compose up -d --build
``​`

Central listens on port 8000. The login account `admin` (or
`CENTRAL_ADMIN_USER`) is created on first start. Database and logos are kept
in the `central-state` volume.

## Endpoints joining the network

Endpoints apply from their **HDN Network** page by entering this Central's
URL. Applications appear under **Endpoints** in the navbar (manager password:
`ENDPOINT_MANAGER_PASSWORD` in `centralproject/settings.py`), with the
endpoint's key fingerprint. When you approve an application, Central notifies
the endpoint. The endpoint joins only if it answers, signed with the key it
applied with, at the URL it declared. A new member immediately receives the
latest published catalog and ontology.

Endpoints can still be added by hand (**+ Add**, base URL such as
`http://tdn.example.org/api0`). They receive queries, but no catalog or
ontology updates, because Central has no key for them. Central posts queries
to `<base URL>/sparql-protected/`. The logo is optional.

## Distributing the query catalog and the ontology

From the same page:

- **Publish query catalog** sends the catalog in `catalogapp/queries.py` to
  every enrolled endpoint. The version number increases only when the content
  changes. Templates whose parameters have no grammar on the endpoints (today
  `q05_L2`, `starting_date`) are left out, and a message says so.
  `q15_L0`–`q18_L4` (clinical trials, drugs by ATC group) target endpoints in
  Galois mode, whose tables hold public knowledge retrieved from an LLM instead
  of patient data.
- **Publish ontology** needs two files: the ontology (`.ttl`) and the mapping
  template written for it (`.obda`). The template holds the blocks that
  *Map Data to HERO* offers on each endpoint. The version increases when
  either file changes. Each endpoint installs both right away. It also removes
  the site mappings that use terms the new ontology no longer declares. The
  page reports, for each endpoint, how many mappings were removed and kept, or
  why the update was refused: invalid Turtle, `owl:imports` not available
  offline, or a template using terms the ontology does not declare.

The table shows the catalog and ontology version installed on each endpoint.
All network messages are signed with Ed25519. This Central's key is created on
first use in `hdn/identity.pem` (or `$HDN_STATE_DIR/hdn/` in Docker). Its
fingerprint is shown on the Endpoints page. Keep the key: if it changes,
enrolled endpoints refuse this Central. `HDN_CENTRAL_NAME` sets the name shown
to endpoints.

Central waits up to 240 s for each endpoint (`HDN_ENDPOINT_TIMEOUT`), in
parallel. Galois endpoints first refill their tables from an LLM and can take
that long.

## Composing your own query (query rewriting)

**Compose a query** in the navbar lets users build a query visually or write
it in SPARQL. Endpoints still execute only catalog queries: Central looks for
an equivalent rewriting of the user query in terms of catalog queries, runs
those, and computes joins, filters and aggregates itself.

- **Derived queries.** At every catalog publication, Central factorizes the
  hand-written templates into their sub-patterns. A sub-pattern has at least
  two triples, is connected and contains a typing triple. Each one becomes a
  derived catalog query with a `d_...` key: published to the endpoints like
  the others, but not listed in the legacy Catalog page.
  - A derived query inherits the highest level among the templates it comes
    from.
  - Adding a template adds its sub-patterns and never lowers an existing
    level. Unchanged sub-patterns keep their key.
- **Rewriting.**
  - A query that is an instance of a template runs that template as it is.
  - Otherwise Central applies MiniCon over the queries that return rows. A
    template parameter must be bound to a constant of the user query that its
    grammar accepts.
  - The plan with the lowest level is chosen.
  - Results are joined per endpoint, never across endpoints. Aggregates are
    given per endpoint and over all endpoints.
  - The plan, with the SPARQL sent to the endpoints, is shown to the user.
- **Admission.** `catalogapp/rewriting/admission.py` decides whether a plan
  may run. Today it admits every plan, and endpoints enforce their own level
  on each catalog query. This module is the intended integration point for a
  new disclosure formalism.
- **Fragment.** Supported: basic graph patterns, FILTER comparisons with
  `&&`, `||`, `!`, COUNT/SUM/AVG/MIN/MAX, GROUP BY, ORDER BY, LIMIT.
  OPTIONAL, UNION, BIND, sub-queries and variable predicates are refused.
- **Known limit.** An endpoint answers empty when a query is above its level,
  so a plan can return less than it should. The page says so.

## Layout

``​`text
centralproject/   settings, root URLs
catalogapp/
  queries.py      query catalog (must match the endpoints' catalog)
  forms.py        parameter forms and allowed values
  views.py        catalog, dispatch, analytics, endpoint manager
  rewriting/      query rewriting over the catalog (lattice, MiniCon, mediator)
  compose_views.py  "Compose a query" page and API
  tests/          python manage.py test catalogapp
  templates/      UI
``​`