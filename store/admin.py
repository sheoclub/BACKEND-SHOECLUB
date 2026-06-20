from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .utils import image_url

from .models import (
    Announcement,
    Banner,
    Brand,
    Category,
    ContactMessage,
    Coupon,
    DeliveryCharge,
    DeliveryChargeTier,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    Setting,
    User,
    Wishlist,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "variant", "quantity", "price", "total")
    can_delete = False
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order", "is_primary")


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("size", "color", "color_code", "sku", "price_override", "stock", "is_active")


@admin.register(User)
class StoreUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Store Profile", {"fields": ("address", "city", "state", "postal_code", "country", "phone", "is_suspended")}),
    )
    list_display = ("email", "get_full_name", "is_staff", "is_suspended", "date_joined", "order_count")
    list_filter = ("is_staff", "is_suspended", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "username", "phone")
    ordering = ("-date_joined",)

    @admin.display(description="Name")
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    @admin.display(description="Orders")
    def order_count(self, obj):
        count = obj.orders.count()
        return format_html('<a href="{}">{} orders</a>', f"/admin/store/order/?user__id={obj.id}", count)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "sort_order", "discount_percentage", "is_active", "product_count")
    list_editable = ("sort_order", "discount_percentage", "is_active")
    search_fields = ("name", "description")
    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at", "product_count")
    list_editable = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline, ProductVariantInline]
    list_display = (
        "name", "category", "brand", "price", "compare_price", "stock", "is_featured",
        "has_variants", "status", "thumbnail_preview", "created_at"
    )
    list_editable = ("price", "compare_price", "stock", "is_featured", "status")
    list_filter = ("status", "is_featured", "has_variants", "category", "brand", "created_at")
    search_fields = ("name", "description", "tags", "brand__name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "thumbnail_preview_detail")
    fieldsets = (
        ("Basic Info", {"fields": ("name", "slug", "category", "brand", "description", "tags")}),
        ("Pricing", {"fields": ("price", "compare_price", "retail_price")}),
        ("Delivery", {"fields": ("free_delivery", "min_quantity", "delivery_charge")}),
        ("Inventory", {"fields": ("stock", "has_variants")}),
        ("Media", {"fields": ("image", "thumbnail_preview_detail")}),
        ("Specifications", {"fields": ("specifications",)}),
        ("SEO / Meta", {"fields": ("meta_title", "meta_description", "meta_keywords")}),
        ("Status & Flags", {"fields": ("status", "is_featured")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Thumbnail")
    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:50px;height:50px;object-fit:cover;border-radius:4px;" />', image_url(obj.image))
        return "-"

    @admin.display(description="Thumbnail")
    def thumbnail_preview_detail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width:200px;max-height:200px;object-fit:cover;border-radius:8px;" />',
                image_url(obj.image)
            )
        return "-"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "rating", "is_approved", "created_at")
    list_editable = ("is_approved",)
    list_filter = ("rating", "is_approved", "created_at")
    search_fields = ("user__email", "product__name", "comment")
    readonly_fields = ("created_at",)
    actions = ("approve_reviews", "unapprove_reviews")

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} reviews approved.")

    @admin.action(description="Unapprove selected reviews")
    def unapprove_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} reviews unapproved.")


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "added_at")
    list_filter = ("added_at",)
    search_fields = ("user__email", "product__name")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "banner_type", "sort_order", "active", "created_at")
    list_editable = ("sort_order", "active")
    list_filter = ("banner_type", "active")
    search_fields = ("title", "subtitle")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "discount_type", "discount_value", "min_order_amount",
        "valid_from", "valid_to", "max_uses", "used_count", "is_active",
        "is_gift", "assigned_to"
    )
    list_filter = ("discount_type", "is_active", "is_gift", "valid_from", "valid_to")
    search_fields = ("code", "description")
    readonly_fields = ("used_count", "auto_generated")
    filter_horizontal = ("categories",)
    fieldsets = (
        ("Coupon Details", {"fields": ("code", "discount_type", "discount_value", "description")}),
        ("Usage Limits", {"fields": ("min_order_amount", "max_uses", "used_count")}),
        ("Validity", {"fields": ("is_active", "valid_from", "valid_to")}),
        ("Category Restriction", {"fields": ("categories",), "classes": ("collapse",)}),
        ("Gift Voucher", {"fields": ("is_gift", "auto_generated", "assigned_to"), "classes": ("collapse",)}),
    )


@admin.register(DeliveryCharge)
class DeliveryChargeAdmin(admin.ModelAdmin):
    list_display = ("city", "charge", "min_order_for_free", "is_active")
    list_editable = ("charge", "min_order_for_free", "is_active")
    list_filter = ("is_active",)
    search_fields = ("city",)
    ordering = ("city",)


@admin.register(DeliveryChargeTier)
class DeliveryChargeTierAdmin(admin.ModelAdmin):
    list_display = ("delivery_charge", "min_quantity", "max_quantity", "charge")
    list_filter = ("delivery_charge",)
    search_fields = ("delivery_charge__city",)
    ordering = ("delivery_charge", "min_quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]
    list_display = (
        "id", "user", "total", "discount_amount", "paid_amount",
        "payment_status", "order_status", "tracking_number", "created_at"
    )
    list_editable = ("order_status", "payment_status", "tracking_number")
    list_filter = ("payment_method", "payment_status", "order_status", "created_at")
    search_fields = ("user__email", "user__first_name", "phone", "tracking_number", "address")
    readonly_fields = ("created_at", "updated_at", "paid_amount", "due_amount")
    fieldsets = (
        ("Customer Info", {"fields": ("user", "address", "city", "phone")}),
        ("Order Details", {"fields": ("subtotal", "discount_amount", "coupon", "shipping_cost", "total")}),
        ("Payment", {"fields": ("payment_method", "payment_status", "proof_image", "paid_amount", "due_amount")}),
        ("Status", {"fields": ("order_status", "tracking_number", "notes")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Paid")
    def paid_amount(self, obj):
        return obj.paid_amount

    @admin.display(description="Due")
    def due_amount(self, obj):
        return obj.due_amount


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value")
    search_fields = ("key", "value")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("message", "active", "created_at")
    list_editable = ("active",)
    search_fields = ("message",)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "email", "subject", "message")
