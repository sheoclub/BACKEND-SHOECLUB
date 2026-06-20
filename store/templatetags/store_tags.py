"""
Template tags library alias for the store app.
Re-exports all tags/filters from store/templatetags/__init__.py.

This allows {% load store_tags %} to work across templates,
providing access to currency formatting (to_pkr, to_usd, format_pkr, format_usd),
image URL generation (image_url), math helpers (multiply, divide, subtract),
status badges, and other utility tags/filters.
"""
from store.templatetags import register as store_register

register = store_register