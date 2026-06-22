from django.http import JsonResponse
from django.urls import include, path

from . import views


def backend_status(request):
    return JsonResponse({"message": "Backend is running"})


urlpatterns = [
    # Backend health/status endpoints for API-only deployment.
    path("", backend_status, name="home"),
    path("health/", backend_status, name="health"),
    path("api/health/", backend_status, name="api_health"),

    # Legacy Django template pages
    path("shop", views.ShopView.as_view(), name="shop"),
    path("product/<int:product_id>", views.ProductDetailView.as_view(), name="product_detail"),
    path("about", views.AboutView.as_view(), name="about"),
    path("shipping-info", views.ShippingInfoView.as_view(), name="shipping_info"),
    path("return-policy", views.ReturnPolicyView.as_view(), name="return_policy"),
    path("contact", views.ContactView.as_view(), name="contact"),

    # Auth
    path("login", views.LoginView.as_view(), name="login"),
    path("signup", views.SignupView.as_view(), name="signup"),
    path("logout", views.LogoutView.as_view(), name="logout"),

    # Cart
    path("cart", views.CartView.as_view(), name="cart_page"),
    path("add-to-cart/<int:product_id>", views.AddToCartView.as_view(), name="add_to_cart"),
    path("update-cart", views.UpdateCartView.as_view(), name="update_cart"),
    path("remove-from-cart/<int:product_id>", views.RemoveFromCartView.as_view(), name="remove_from_cart"),

    # AJAX Cart
    path("ajax/add-to-cart/<int:product_id>", views.AJAXAddToCartView.as_view(), name="ajax_add_to_cart"),
    path("ajax/update-cart", views.AJAXUpdateCartView.as_view(), name="ajax_update_cart"),
    path("ajax/cart-detail", views.AJAXCartDetailView.as_view(), name="ajax_cart_detail"),

    # Checkout & Orders
    path("checkout", views.CheckoutView.as_view(), name="checkout"),
    path("online-payment", views.OnlinePaymentView.as_view(), name="online_payment"),
    path("order/<int:order_id>", views.OrderDetailView.as_view(), name="order_detail"),
    path("invoice/<int:order_id>", views.InvoiceView.as_view(), name="invoice"),

    # User Dashboard
    path("dashboard", views.UserDashboardView.as_view(), name="user_dashboard"),
    path("dashboard/update-profile", views.UpdateProfileView.as_view(), name="update_profile"),
    path("dashboard/change-password", views.ChangePasswordView.as_view(), name="change_password"),

    # Wishlist
    path("wishlist", views.WishlistView.as_view(), name="wishlist"),
    path("wishlist/toggle/<int:product_id>", views.WishlistToggleView.as_view(), name="wishlist_toggle"),
    path("wishlist/remove/<int:product_id>", views.WishlistRemoveView.as_view(), name="wishlist_remove"),

    # Reviews
    path("review/add/<int:product_id>", views.AddReviewView.as_view(), name="add_review"),

    # Admin
    path("admin", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin/products", views.AdminProductListView.as_view(), name="admin_products"),
    path("admin/products/add", views.AdminProductCreateView.as_view(), name="admin_add_product"),
    path("admin/products/edit/<int:product_id>", views.AdminProductUpdateView.as_view(), name="admin_edit_product"),
    path("admin/products/delete/<int:product_id>", views.AdminProductDeleteView.as_view(), name="admin_delete_product"),
    path("admin/categories", views.AdminCategoryListView.as_view(), name="admin_categories"),
    path("admin/categories/delete/<int:category_id>", views.AdminCategoryDeleteView.as_view(), name="admin_delete_category"),
    path("admin/users", views.AdminUserListView.as_view(), name="admin_users"),
    path("admin/users/<int:user_id>", views.AdminUserDetailView.as_view(), name="admin_user_detail"),
    path("admin/users/delete/<int:user_id>", views.AdminUserDeleteView.as_view(), name="admin_delete_user"),
    path("admin/users/toggle/<int:user_id>", views.AdminUserToggleView.as_view(), name="admin_toggle_user"),
    path("admin/orders", views.AdminOrderListView.as_view(), name="admin_orders"),
    path("admin/orders/<int:order_id>", views.AdminOrderDetailView.as_view(), name="admin_order_detail"),
    path("admin/orders/status/<int:order_id>", views.AdminOrderStatusUpdateView.as_view(), name="admin_order_status"),
    path("admin/orders/verify/<int:order_id>", views.AdminPaymentVerifyView.as_view(), name="admin_verify_payment"),
    path("admin/orders/reject/<int:order_id>", views.AdminPaymentRejectView.as_view(), name="admin_reject_payment"),
    path("admin/orders/pay/<int:order_id>", views.AdminPaymentRecordView.as_view(), name="admin_pay_order"),
    path("admin/orders/notify/<int:order_id>", views.AdminDueNotifyView.as_view(), name="admin_notify_due"),
    path("admin/payments", views.AdminPaymentListView.as_view(), name="admin_payments"),
    path("admin/banners", views.AdminBannerListView.as_view(), name="admin_banners"),
    path("admin/banners/toggle/<int:banner_id>", views.AdminBannerToggleView.as_view(), name="admin_banner_toggle"),
    path("admin/banners/delete/<int:banner_id>", views.AdminBannerDeleteView.as_view(), name="admin_banner_delete"),
    path("admin/banners/reorder/<int:banner_id>/<str:direction>", views.AdminBannerReorderView.as_view(), name="admin_banner_reorder"),
    path("admin/announcements", views.AdminAnnouncementListView.as_view(), name="admin_announcements"),
    path("admin/announcements/toggle/<int:announcement_id>", views.AdminAnnouncementToggleView.as_view(), name="admin_announcement_toggle"),
    path("admin/announcements/flash-sale", views.AdminAnnouncementFlashSaleView.as_view(), name="admin_announcement_flash_sale"),
    path("admin/announcements/delete/<int:announcement_id>", views.AdminAnnouncementDeleteView.as_view(), name="admin_announcement_delete"),
    path("admin/contact-messages", views.AdminContactMessageListView.as_view(), name="admin_contact_messages"),
    path("admin/contact-messages/reply/<int:message_id>", views.AdminContactMessageReplyView.as_view(), name="admin_contact_message_reply"),
    path("admin/delivery-charges", views.AdminDeliveryChargeListView.as_view(), name="admin_delivery_charges"),
    path("admin/delivery-charges/update/<int:charge_id>", views.AdminDeliveryChargeUpdateView.as_view(), name="admin_delivery_charge_update"),
    path("admin/delivery-charges/toggle/<int:charge_id>", views.AdminDeliveryChargeToggleView.as_view(), name="admin_delivery_charge_toggle"),
    path("admin/delivery-charges/delete/<int:charge_id>", views.AdminDeliveryChargeDeleteView.as_view(), name="admin_delivery_charge_delete"),
    path("admin/delivery-charges/tiers/<int:charge_id>", views.AdminDeliveryChargeTierListView.as_view(), name="admin_delivery_charge_tiers"),
    path("admin/delivery-charges/tiers/<int:charge_id>/add", views.AdminDeliveryChargeTierCreateView.as_view(), name="admin_delivery_charge_tier_add"),
    path("admin/delivery-charges/tiers/<int:tier_id>/delete", views.AdminDeliveryChargeTierDeleteView.as_view(), name="admin_delivery_charge_tier_delete"),
    path("admin/settings", views.AdminSettingsView.as_view(), name="admin_settings"),
    path("admin/reports", views.AdminReportView.as_view(), name="admin_reports"),

    # REST API
    # Sitemap
    path("sitemap.xml", views.sitemap, name="sitemap"),

    # REST API
    path("api/", include("store.api_urls")),
]
