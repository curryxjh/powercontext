# Order listing

Task: add an exact `status` filter to `list_orders`.

- With `status=None`, return all orders in input order, as before.
- With a status, return only orders whose `Order.status` equals that value, preserving input order.
- A status with no matches returns an empty list.
- Do not mutate the input or any order.
- The empty string is a valid filter value; only `None` disables filtering.

Relevant source: `minimax/sample_app/orders.py`, symbol `list_orders`.
Functional and compatibility checks: `minimax/tests/test_orders.py`.
