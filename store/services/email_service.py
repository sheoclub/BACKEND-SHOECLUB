import logging
import random
import string

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_coupon_email(coupon, user):
    """Send a coupon code email to a user. Returns True if sent successfully."""
    if not user.email:
        logger.warning(f"No email for user {user.id}, skipping coupon email")
        return False

    try:
        site_name = "Shoe Club"
        subject = f"🎉 {site_name} - You've received a coupon!"

        # Build discount display string
        if coupon.discount_type == "percent":
            discount_display = f"{coupon.discount_value}% OFF"
        elif coupon.discount_type == "fixed":
            discount_display = f"${coupon.discount_value} OFF"
        else:
            discount_display = f"{coupon.discount_value} {coupon.discount_type}"

        valid_until_str = ""
        if coupon.valid_until:
            valid_until_str = coupon.valid_until.strftime("%B %d, %Y")

        # Inline HTML email body
        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.1);">
<tr><td style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px 40px;text-align:center;">
<h1 style="color:#ffffff;margin:0;font-size:24px;">🎉 Special Coupon Just For You!</h1>
</td></tr>
<tr><td style="padding:30px 40px;text-align:center;">
<p style="font-size:16px;color:#333333;margin:0 0 20px;">Hello <strong>{user.get_full_name() or user.username}</strong>,</p>
<p style="font-size:14px;color:#666666;margin:0 0 25px;">Use the coupon code below to save on your next purchase at <strong>{site_name}</strong>.</p>
<div style="background:#f0f4ff;border:2px dashed #667eea;border-radius:12px;padding:20px;margin:0 0 25px;">
<p style="font-size:12px;color:#888888;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">Your Coupon Code</p>
<p style="font-size:32px;font-weight:bold;color:#667eea;margin:0 0 10px;letter-spacing:3px;">{coupon.code}</p>
<p style="font-size:18px;font-weight:bold;color:#764ba2;margin:0;">{discount_display}</p>
</div>
<table width="100%" cellpadding="8" cellspacing="0">
<tr><td style="border-bottom:1px solid #eee;"><strong style="color:#333;">Discount:</strong></td><td style="text-align:right;color:#666;">{discount_display}</td></tr>
{"<tr><td style=\"border-bottom:1px solid #eee;\"><strong style=\"color:#333;\">Minimum Order:</strong></td><td style=\"text-align:right;color:#666;\">$" + str(coupon.min_order_amount) + "</td></tr>" if coupon.min_order_amount else ""}
{"<tr><td style=\"border-bottom:1px solid #eee;\"><strong style=\"color:#333;\">Valid Until:</strong></td><td style=\"text-align:right;color:#666;\">" + valid_until_str + "</td></tr>" if valid_until_str else ""}
</table>
</td></tr>
<tr><td style="padding:20px 40px;text-align:center;background-color:#f9f9f9;">
<p style="font-size:12px;color:#999999;margin:0;">If you have any questions, feel free to contact us.</p>
<p style="font-size:12px;color:#999999;margin:5px 0 0;">Thank you for being a valued customer! 💜</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""

        email = EmailMessage(
            subject=subject,
            body=html_body,
            to=[user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=True)

        # Mark the coupon as emailed
        coupon.emailed_at = timezone.now()
        coupon.save(update_fields=["emailed_at"])

        logger.info(f"Coupon email sent to {user.email} for code {coupon.code}")
        return True

    except Exception as e:
        logger.error(f"Failed to send coupon email to {user.email}: {e}")
        return False