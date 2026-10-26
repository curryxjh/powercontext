You are implementing the order-listing task in this repository. The attached
context-before.json was produced by `python -m minimax.sdd_context context`
after importing the actual spec, code, and tests into embedded seekdb and
recovering task progress from PowerContext. Use its `documents` and `progress`
to decide the change.

Modify only `minimax/sample_app/orders.py`. Implement the exact `status`
filter described in the retrieved spec. Preserve input order and existing
unfiltered behavior. Do not edit the tests, spec, context module, or evidence.
Explain your code change and the retrieved sources used. Do not commit.
