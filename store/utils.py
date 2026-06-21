from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.templatetags.static import static
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from .models import Setting


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def is_base64_data_url(value):
    """Return True if value is a base64-encoded data URL (e.g. data:image/jpeg;base64,...)."""
    return bool(value and isinstance(value, str) and value.startswith("data:image/"))


def allowed_file(upload):
    return bool(upload and hasattr(upload, "name") and "." in upload.name and upload.name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS)


def save_upload(upload):
    suffix = Path(upload.name).suffix.lower()
    filename = f"{uuid.uuid4().hex}{suffix}"
    storage = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
    storage.save(filename, upload)
    return filename


def image_url(value):
    if not value:
        return ""
    value = str(value)
    if value.startswith(("http://", "https://", "/static/", "/media/")):
        return value
    return f"{settings.MEDIA_URL}{value}"


def get_setting(key, default=""):
    try:
        row = Setting.objects.get(pk=key)
    except Setting.DoesNotExist:
        return default
    return row.value


def settings_dict():
    return {item.key: item.value for item in Setting.objects.all()}


def decimal_value(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def to_pkr(amount):
    rate = decimal_value(get_setting("pkr_rate", "280"), "280")
    return decimal_value(amount) * rate


def format_currency(amount, currency="PKR"):
    amount = decimal_value(amount)
    prefix = "RS" if currency.upper() == "PKR" else "$"
    return f"{prefix} {amount:,.2f}"


def url_for(endpoint, **kwargs):
    if endpoint == "static":
        filename = kwargs.get("filename", "")
        if filename.startswith("uploads/"):
            return f"{settings.MEDIA_URL}{filename.removeprefix('uploads/')}"
        return static(filename)
    try:
        return reverse(endpoint, kwargs=kwargs)
    except NoReverseMatch:
        base_url = reverse(endpoint)
        return f"{base_url}?{urlencode(kwargs)}" if kwargs else base_url
