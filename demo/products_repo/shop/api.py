"""Product listing API."""
from .db import all_products


def list_products():
    """Return every product."""
    return all_products()
