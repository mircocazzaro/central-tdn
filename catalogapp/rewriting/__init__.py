"""Query rewriting using views over the HDN catalog.

Users may write (or compose visually) their own SPARQL query. Endpoints only
execute catalog templates, so Central looks for an *equivalent* rewriting of
the query in terms of catalog templates, runs those templates on the
endpoints and computes the rest (joins, filters, aggregates) itself.

- ``ir``: intermediate representation of templates and queries (rdflib);
- ``lattice``: derived templates, the connected sub-patterns of the
  hand-written ones, published in the catalog but hidden from the legacy UI;
- ``minicon``: MiniCon (Pottinger & Halevy, VLDB J. 2001) restricted to
  equivalent, bag-preserving rewritings, with templates' parameters treated
  as binding patterns (Rajaraman, Sagiv & Ullman, PODS 1995);
- ``admission``: whether a rewriting may run (today: the template levels);
- ``mediator``: execution on the endpoints and final computation in DuckDB.
"""
