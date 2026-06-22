from django.contrib import messages
from django.middleware.csrf import get_token

from .utils import get_setting, settings_dict as get_all_settings


def store_context(request):
    """Context processor for Django templates."""
    data = get_all_settings()

    # Count cart items
    cart = request.session.get("cart", {})
    cart_count = sum(int(qty) for qty in cart.values())

    # Is admin?
    is_admin = request.user.is_authenticated and request.user.is_staff

    return {
        "settings": data,
        "pkr_rate": float(data.get("pkr_rate", "280") or 280),
        "logo_url": data.get("logo_url", ""),
        "site_name": data.get("site_name", "Ladies Shoe Club"),
        "contact_email": data.get("email", "contact@ladiesshoeclub.com"),
        "contact_phone": data.get("phone", "+92 300 123 4567"),
        "top_banner_text": data.get("top_banner_text", "Flash Sale: Up to 50% off on select styles! New Arrivals Just In!"),
        "facebook_url": data.get("facebook", "#"),
        "instagram_url": data.get("instagram", "#"),
        "twitter_url": data.get("twitter", "#"),
        "linkedin_url": data.get("linkedin", "#"),
        "youtube_url": data.get("youtube", "#"),
        "about_text": data.get("about_text", ""),
        "about_photo_url": data.get(
            "about_photo_url",
            "https://images.unsplash.com/photo-1521335629791-ce4aec67dd50?auto=format&fit=crop&w=1000&q=80",
        ),
        "contact_address": data.get("contact_address", ""),
        "is_admin": is_admin,
        "cart_count": cart_count,
    }
