from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter(name="to_pkr")
def to_pkr(value):
    """Format a number as PKR currency (RS X,XXX.XX)."""
    try:
        amount = Decimal(str(value))
        return f"RS {amount:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "RS 0.00"


@register.filter(name="to_usd")
def to_usd(value):
    """Format a number as USD currency ($X,XXX.XX)."""
    try:
        amount = Decimal(str(value))
        return f"${amount:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "$0.00"


@register.filter(name="multiply")
def multiply(value, arg):
    """Multiply value by arg: value|multiply:arg"""
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")