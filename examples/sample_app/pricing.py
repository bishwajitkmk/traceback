"""Pricing helpers, kept in their own module so stack traces show an in-app frame."""

UNIT_PRICE = 19.99


def cart_total(quantity: int) -> float:
    return round(quantity * UNIT_PRICE, 2)


def unit_price(total: float, quantity: int) -> float:
    return round(total / quantity, 2)
