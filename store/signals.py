import logging

from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Order, OrderItem, Product, Setting

logger = logging.getLogger(__name__)

User = get_user_model()


def _get_setting(key, default=""):
    try:
        return Setting.objects.get(key=key).value
    except Setting.DoesNotExist:
        return default


@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    """Handle stock updates when order is placed."""
    if created and instance.order_status in ["pending", "confirmed"]:
        for item in instance.items.all():
            product = item.product
            if not product.has_variants:
                product.stock = max(0, product.stock - item.quantity)
                product.save(update_fields=["stock"])
            else:
                variant = item.variant
                if variant:
                    variant.stock = max(0, variant.stock - item.quantity)
                    variant.save(update_fields=["stock"])


@receiver(post_save, sender=Order)
def send_order_confirmation_email(sender, instance, created, **kwargs):
    """Send order confirmation email to the user."""
    if not created:
        return

    user = instance.user
    if not user.email:
        return

    try:
        site_name = _get_setting("site_name", "Ladies Shoe Club")
        subject = f"{site_name} - Order #{instance.id} Confirmed"

        context = {
            "order": instance,
            "site_name": site_name,
            "user": user,
            "items": instance.items.all(),
        }

        html_message = render_to_string("emails/order_confirmation.html", context)
        plain_message = strip_tags(html_message)

        email = EmailMessage(
            subject=subject,
            body=html_message,
            to=[user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=True)
        logger.info(f"Order confirmation email sent to {user.email} for order #{instance.id}")
    except Exception as e:
        logger.error(f"Failed to send order confirmation email: {e}")


@receiver(pre_save, sender=Order)
def order_pre_save(sender, instance, **kwargs):
    """Send status update email when order status changes."""
    if not instance.pk:
        return

    try:
        old_instance = Order.objects.get(pk=instance.pk)
    except Order.DoesNotExist:
        return

    if old_instance.order_status == instance.order_status:
        return

    user = instance.user
    if not user.email:
        return

    try:
        site_name = _get_setting("site_name", "Ladies Shoe Club")
        subject = f"{site_name} - Order #{instance.id} Status Updated to {instance.get_order_status_display()}"

        context = {
            "order": instance,
            "site_name": site_name,
            "user": user,
            "old_status": old_instance.get_order_status_display(),
            "new_status": instance.get_order_status_display(),
        }

        html_message = render_to_string("emails/order_status_update.html", context)
        plain_message = strip_tags(html_message)

        email = EmailMessage(
            subject=subject,
            body=html_message,
            to=[user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=True)
        logger.info(f"Order status email sent to {user.email} for order #{instance.id}")
    except Exception as e:
        logger.error(f"Failed to send order status email: {e}")


@receiver(post_save, sender=OrderItem)
def order_item_post_save(sender, instance, created, **kwargs):
    """Update order total when items change."""
    if created:
        order = instance.order
        order.total = sum(item.total for item in order.items.all())
        order.save(update_fields=["total"])