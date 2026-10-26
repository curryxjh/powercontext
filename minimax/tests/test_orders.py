from minimax.sample_app.orders import Order, list_orders


ORDERS = [
    Order("A", "paid"),
    Order("B", "pending"),
    Order("C", "paid"),
    Order("D", ""),
]


def test_status_filter_matches_exact_value_in_input_order():
    assert list_orders(ORDERS, status="paid") == [ORDERS[0], ORDERS[2]]
    assert list_orders(ORDERS, status="missing") == []
    assert list_orders(ORDERS, status="") == [ORDERS[3]]


def test_existing_unfiltered_behavior_and_immutable_input():
    before = list(ORDERS)
    assert list_orders(ORDERS) == before
    assert ORDERS == before
