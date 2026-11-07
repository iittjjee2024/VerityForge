"""Tiny in-memory product store."""

PRODUCTS = [{"id": i, "name": f"Product {i}", "price": 5 + i} for i in range(1, 38)]


def all_products():
    return list(PRODUCTS)
