from django import template
from django.template.defaultfilters import stringfilter
from decimal import Decimal, InvalidOperation
import re

register = template.Library()


@register.filter
def to_pkr(amount):
    """Format amount as PKR currency string."""
    try:
        val = Decimal(str(amount))
        if val == int(val):
            return f"Rs. {int(val):,}"
        return f"Rs. {val:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "Rs. 0"


@register.filter
def to_usd(amount):
    """Format amount as USD currency string."""
    try:
        val = Decimal(str(amount))
        if val == int(val):
            return f"${int(val):,}"
        return f"${val:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "$0.00"


@register.filter
def image_url(value):
    """Return the image URL for a given value (field, url string, or None)."""
    if not value:
        return ""
    # If it's a model instance with a url property or field
    if hasattr(value, "url"):
        return value.url
    # If it's already a URL string, return as-is
    return str(value)


@register.filter
def multiply(value, arg):
    """Multiply two values: value * arg"""
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.filter
def divide(value, arg):
    """Divide two values: value / arg"""
    try:
        val = Decimal(str(value))
        denom = Decimal(str(arg))
        if denom == 0:
            return 0
        return val / denom
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.filter
def subtract(value, arg):
    """Subtract arg from value: value - arg"""
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.filter
def pkr_to_usd(amount):
    """Convert PKR to USD using the pkr_rate from context."""
    try:
        val = Decimal(str(amount))
        rate = Decimal(str(getattr(amount, "pkr_rate", 280)))
        if rate == 0:
            return "$0.00"
        usd_val = val / rate
        if usd_val == int(usd_val):
            return f"${int(usd_val):,}"
        return f"${usd_val:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "$0.00"


@register.filter
@stringfilter
def split(value, delimiter=","):
    """Split a string by delimiter and return a list."""
    return value.split(delimiter)


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    if dictionary is None:
        return ""
    return dictionary.get(key, "")


@register.filter
def subtract_from(value, arg):
    """Subtract value from arg: arg - value"""
    try:
        return Decimal(str(arg)) - Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.filter
def status_badge(status):
    """Convert a status string to a Bootstrap badge class."""
    status_map = {
        "pending": "warning",
        "confirmed": "info",
        "processing": "primary",
        "shipped": "primary",
        "delivered": "success",
        "completed": "success",
        "cancelled": "danger",
        "paid": "success",
        "unpaid": "secondary",
        "refunded": "info",
        "active": "success",
        "inactive": "secondary",
        "read": "info",
        "unread": "warning",
    }
    badge_class = status_map.get(status.lower(), "secondary") if status else "secondary"
    return f'<span class="badge bg-{badge_class}">{status or "N/A"}</span>'


@register.filter
@stringfilter
def truncate_chars(value, arg):
    """Truncate a string after a certain number of characters."""
    try:
        length = int(arg)
        if len(value) <= length:
            return value
        return value[:length] + "..."
    except (ValueError, TypeError):
        return value


@register.simple_tag(takes_context=True)
def format_pkr(context, amount):
    """Template tag to format amount in PKR using context pkr_rate."""
    pkr_rate = context.get("pkr_rate", 280)
    try:
        val = Decimal(str(amount))
        if val == int(val):
            return f"Rs. {int(val):,}"
        return f"Rs. {val:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "Rs. 0"


@register.simple_tag(takes_context=True)
def format_usd(context, amount):
    """Template tag to format amount in USD using context pkr_rate."""
    pkr_rate = context.get("pkr_rate", 280)
    try:
        val = Decimal(str(amount))
        usd_val = val / Decimal(str(pkr_rate))
        if usd_val == int(usd_val):
            return f"${int(usd_val):,}"
        return f"${usd_val:,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "$0.00"