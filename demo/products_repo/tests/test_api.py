from shop.api import list_products


def test_lists_all_products():
    assert len(list_products()) == 37
