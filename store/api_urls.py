from django.urls import path
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import api_views

router = routers.DefaultRouter()
router.register(r"products", api_views.ProductViewSet)
router.register(r"categories", api_views.CategoryViewSet)
router.register(r"orders", api_views.OrderViewSet, basename="order")
router.register(r"reviews", api_views.ReviewViewSet, basename="review")
router.register(r"wishlist", api_views.WishlistViewSet, basename="wishlist")
router.register(r"banners", api_views.BannerViewSet)
router.register(r"coupons", api_views.CouponViewSet, basename="coupon")

urlpatterns = router.urls + [
    # Auth
    path("auth/login/", api_views.LoginAPIView.as_view(), name="api_login"),
    path("auth/signup/", api_views.SignupAPIView.as_view(), name="api_signup"),
    path("auth/me/", api_views.CurrentUserAPIView.as_view(), name="api_current_user"),
    # JWT Token management (for React app to refresh/verify tokens)
    path("auth/token/", TokenObtainPairView.as_view(), name="api_token_obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="api_token_refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="api_token_verify"),
    # Cart
    path("cart/", api_views.CartAPIView.as_view(), name="api_cart"),
    path("cart/add/", api_views.CartAddAPIView.as_view(), name="api_cart_add"),
    path("cart/update/", api_views.CartUpdateAPIView.as_view(), name="api_cart_update"),
    path("cart/remove/<int:product_id>/", api_views.CartRemoveAPIView.as_view(), name="api_cart_remove"),
    # Checkout
    path("checkout/", api_views.CheckoutAPIView.as_view(), name="api_checkout"),
    path("checkout/validate-coupon/", api_views.CouponValidateAPIView.as_view(), name="api_validate_coupon"),
    # User profile
    path("user/profile/", api_views.UserProfileAPIView.as_view(), name="api_user_profile"),
    path("user/change-password/", api_views.ChangePasswordAPIView.as_view(), name="api_change_password"),
    # Site settings
    path("settings/", api_views.SiteSettingsAPIView.as_view(), name="api_settings"),
    # Announcements (public)
    path("announcements/", api_views.AnnouncementListAPIView.as_view(), name="api_announcements"),
    # Contact
    path("contact/", api_views.ContactAPIView.as_view(), name="api_contact"),
    path("user/contact-messages/", api_views.UserContactMessageListAPIView.as_view(), name="api_user_contact_messages"),
    # Track Order (public)
    path("track-order/", api_views.TrackOrderAPIView.as_view(), name="api_track_order"),
    # Delivery Charges (public)
    path("delivery-charges/", api_views.DeliveryChargeListAPIView.as_view(), name="api_delivery_charges"),
    path("delivery-charges/provinces/", api_views.ProvinceListAPIView.as_view(), name="api_delivery_charge_provinces"),
    # Admin endpoints
    path("admin/dashboard/", api_views.AdminDashboardAPIView.as_view(), name="api_admin_dashboard"),
    path("admin/products/", api_views.AdminProductListCreateAPIView.as_view(), name="api_admin_products"),
    path("admin/products/<int:product_id>/", api_views.AdminProductDetailAPIView.as_view(), name="api_admin_product_detail"),
    path("admin/products/<int:product_id>/variants/", api_views.AdminProductVariantListCreateAPIView.as_view(), name="api_admin_product_variants"),
    path("admin/products/<int:product_id>/variants/<int:variant_id>/", api_views.AdminProductVariantDetailAPIView.as_view(), name="api_admin_product_variant_detail"),
    path("admin/products/<int:product_id>/gallery/", api_views.AdminProductGalleryListCreateAPIView.as_view(), name="api_admin_product_gallery"),
    path("admin/products/<int:product_id>/gallery/<int:image_id>/", api_views.AdminProductGalleryDetailAPIView.as_view(), name="api_admin_product_gallery_detail"),
    path("admin/categories/", api_views.AdminCategoryListCreateAPIView.as_view(), name="api_admin_categories"),
    path("admin/categories/<int:pk>/", api_views.AdminCategoryDetailAPIView.as_view(), name="api_admin_category_detail"),
    path("admin/orders/create/", api_views.AdminOrderCreateAPIView.as_view(), name="api_admin_order_create"),
    path("admin/orders/", api_views.AdminOrderListAPIView.as_view(), name="api_admin_orders"),
    path("admin/orders/<int:order_id>/", api_views.AdminOrderDetailAPIView.as_view(), name="api_admin_order_detail"),
    path("admin/orders/<int:order_id>/status/", api_views.AdminOrderStatusAPIView.as_view(), name="api_admin_order_status"),
    path("admin/orders/<int:order_id>/delete/", api_views.AdminOrderDeleteAPIView.as_view(), name="api_admin_order_delete"),
    path("admin/users/", api_views.AdminUserListAPIView.as_view(), name="api_admin_users"),
    path("admin/users/<int:user_id>/", api_views.AdminUserDetailAPIView.as_view(), name="api_admin_user_detail"),
    path("admin/users/<int:user_id>/toggle/", api_views.AdminUserToggleAPIView.as_view(), name="api_admin_user_toggle"),
    path("admin/banners/", api_views.AdminBannerListCreateAPIView.as_view(), name="api_admin_banners"),
    path("admin/banners/bulk/", api_views.AdminBannerBulkCreateAPIView.as_view(), name="api_admin_banners_bulk"),
    path("admin/banners/<int:banner_id>/", api_views.AdminBannerToggleDeleteAPIView.as_view(), name="api_admin_banner_detail"),
    path("admin/banners/<int:banner_id>/reorder/<str:direction>/", api_views.AdminBannerReorderAPIView.as_view(), name="api_admin_banner_reorder"),
    path("admin/announcements/", api_views.AdminAnnouncementListCreateAPIView.as_view(), name="api_admin_announcements"),
    path("admin/announcements/<int:pk>/toggle/", api_views.AdminAnnouncementToggleAPIView.as_view(), name="api_admin_announcement_toggle"),
    path("admin/announcements/<int:pk>/", api_views.AdminAnnouncementDeleteAPIView.as_view(), name="api_admin_announcement_delete"),
    path("admin/contact-messages/", api_views.AdminContactMessageListAPIView.as_view(), name="api_admin_contact_messages"),
    path("admin/contact-messages/<int:pk>/reply/", api_views.AdminContactMessageReplyAPIView.as_view(), name="api_admin_contact_reply"),
    path("admin/contact-messages/<int:pk>/delete/", api_views.AdminContactMessageReplyAPIView.as_view(), name="api_admin_contact_message_delete"),
    path("admin/reviews/", api_views.AdminReviewListAPIView.as_view(), name="api_admin_reviews"),
    path("admin/settings/", api_views.AdminSettingsAPIView.as_view(), name="api_admin_settings"),
    path("admin/seo/", api_views.AdminSEOAPIView.as_view(), name="api_admin_seo"),
    path("admin/brands/", api_views.AdminBrandListAPIView.as_view(), name="api_admin_brands"),
    path("admin/reports/", api_views.AdminReportsAPIView.as_view(), name="api_admin_reports"),
    path("admin/analytics/", api_views.AdminAnalyticsAPIView.as_view(), name="api_admin_analytics"),
    # Admin: Delivery Charges CRUD
    path("admin/delivery-charges/", api_views.AdminDeliveryChargeListCreateAPIView.as_view(), name="api_admin_delivery_charges"),
    path("admin/delivery-charges/<int:pk>/", api_views.AdminDeliveryChargeDetailAPIView.as_view(), name="api_admin_delivery_charge_detail"),
    # Admin: Delivery Charge Tiers CRUD
    path("admin/delivery-charges/<int:delivery_charge_id>/tiers/", api_views.AdminDeliveryChargeTierListCreateAPIView.as_view(), name="api_admin_delivery_charge_tiers"),
    path("admin/delivery-charges/tiers/<int:pk>/", api_views.AdminDeliveryChargeTierDetailAPIView.as_view(), name="api_admin_delivery_charge_tier_detail"),
    # Admin: Coupon management
    path("admin/coupons/", api_views.AdminCouponListCreateAPIView.as_view(), name="api_admin_coupons"),
    path("admin/coupons/<int:pk>/", api_views.AdminCouponDetailAPIView.as_view(), name="api_admin_coupon_detail"),
    path("admin/coupons/export/", api_views.AdminCouponExportCSVAPIView.as_view(), name="api_admin_coupon_export"),
    # User notifications / inbox
    path("user/notifications/", api_views.UserNotificationListAPIView.as_view(), name="api_user_notifications"),
]