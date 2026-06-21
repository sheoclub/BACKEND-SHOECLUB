from decimal import Decimal
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─── Custom Managers ──────────────────────────────────────────────

class ActiveProductManager(models.Manager):
    """Returns only active (status=True) products with related category."""

    def get_queryset(self):
        return super().get_queryset().filter(status=True).select_related("category")

    def in_stock(self):
        return self.get_queryset().filter(stock__gt=0)

    def featured(self):
        return self.get_queryset().filter(is_featured=True)


class ProductManager(models.Manager):
    def active(self):
        return self.get_queryset().filter(status=True).select_related("category")

    def in_stock(self):
        return self.active().filter(stock__gt=0)

    def low_stock(self, threshold=5):
        return self.active().filter(stock__lte=threshold, stock__gt=0)

    def out_of_stock(self):
        return self.active().filter(stock=0)


# ─── Models ───────────────────────────────────────────────────────

class User(AbstractUser):
    email = models.EmailField(unique=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=40, blank=True)
    country = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    is_suspended = models.BooleanField(default=False)
    newsletter_subscribed = models.BooleanField(default=False, verbose_name="Subscribed to newsletter")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_suspended"]),
        ]
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    @property
    def name(self):
        return self.get_full_name() or self.username or self.email

    @property
    def order_count(self):
        return self.orders.count()

    @property
    def total_spent(self):
        return self.orders.aggregate(total=models.Sum("total"))["total"] or Decimal("0.00")

    def __str__(self):
        return self.email


class Brand(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=500, blank=True)
    website = models.URLField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)
            slug = base
            counter = 1
            while Brand.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=500, blank=True, null=True, verbose_name="Image URL")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name="Category Discount (%)", help_text="Percentage discount applied to all products in this category")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        indexes = [models.Index(fields=["name"]), models.Index(fields=["is_active"])]

    def __str__(self):
        return self.name

    @property
    def product_count(self):
        return self.product_set.filter(status=True).count()


class Product(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Selling Price")
    compare_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Original/compare-at price for showing discounts")
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Retail Price (Cost)", help_text="Cost/retail price for profit calculation")
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    image = models.CharField(max_length=500, blank=True)
    image_alt = models.CharField(max_length=255, blank=True, verbose_name="Image alt text")
    status = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    has_variants = models.BooleanField(default=False, verbose_name="Has size/color variants")
    free_delivery = models.BooleanField(default=False, verbose_name="Free delivery eligible", help_text="When checked, this product qualifies for free delivery regardless of cart total")
    min_quantity = models.PositiveIntegerField(default=1, verbose_name="Min quantity for delivery charge", help_text="Base quantity block for per-product delivery charge calculation. E.g., 4 means charge applies per 4 items.")
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Delivery charge per block", help_text="Fixed delivery charge per block of min_quantity items. E.g., min_quantity=4, charge=400 => 1-4 items = 400, 5-8 = 800, etc.")
    specifications = models.JSONField(blank=True, null=True, verbose_name="Product specifications (JSON)")
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags for filtering")
    meta_title = models.CharField(max_length=255, blank=True, verbose_name="Meta Title (SEO)")
    meta_keywords = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductManager()
    active = ActiveProductManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "is_featured"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["price"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name)
            slug = base
            counter = 1
            while Product.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def discount_percentage(self):
        if not self.compare_price or not self.price:
            return 0
        try:
            price_dec = Decimal(str(self.price))
            compare_price_dec = Decimal(str(self.compare_price))
            if compare_price_dec > price_dec:
                return int(((compare_price_dec - price_dec) / compare_price_dec) * 100)
        except Exception:
            pass
        return 0

    @property
    def is_in_stock(self):
        return self.stock > 0

    @property
    def average_rating(self):
        from django.db.models import Avg
        result = self.reviews.aggregate(avg=Avg("rating"))["avg"]
        return round(result, 1) if result else 0

    @property
    def review_count(self):
        return self.reviews.count()

    @property
    def profit_percentage(self):
        if not self.price or not self.retail_price:
            return 0
        try:
            price_dec = Decimal(str(self.price))
            retail_dec = Decimal(str(self.retail_price))
            if retail_dec > 0:
                return int(((price_dec - retail_dec) / retail_dec) * 100)
        except Exception:
            pass
        return 0

    @property
    def thumbnail_url(self):
        if self.image:
            return self.image
        return ""


class ProductVariant(models.Model):
    """Size/color variants for products."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=20, blank=True, verbose_name="Size (e.g. 7, 8, 9, M, L)")
    color = models.CharField(max_length=50, blank=True, verbose_name="Color name")
    color_code = models.CharField(max_length=7, blank=True, help_text="Hex color code e.g. #FF0000")
    sku = models.CharField(max_length=100, unique=True, blank=True, verbose_name="Stock Keeping Unit")
    price_override = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Override product price for this variant")
    stock = models.PositiveIntegerField(default=0)
    image = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["size", "color"]
        unique_together = [("product", "size", "color")]
        indexes = [models.Index(fields=["sku"]), models.Index(fields=["product", "is_active"])]
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"{self.product.id}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        parts = [self.product.name]
        if self.size:
            parts.append(f"Size: {self.size}")
        if self.color:
            parts.append(f"Color: {self.color}")
        return " / ".join(parts)

    @property
    def effective_price(self):
        return self.price_override or self.product.price

    @property
    def is_in_stock(self):
        return self.stock > 0


class ProductImage(models.Model):
    """Additional product gallery images."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="gallery_images")
    image = models.CharField(max_length=500)
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order"]
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")


class Review(models.Model):
    """Product reviews and ratings."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    rating = models.IntegerField(choices=RATING_CHOICES, validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("product", "user")]  # One review per product per user
        indexes = [
            models.Index(fields=["product", "is_approved"]),
            models.Index(fields=["rating"]),
        ]
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")

    def __str__(self):
        return f"{self.user.email} - {self.product.name} ({self.rating}★)"


class Wishlist(models.Model):
    """User wishlist items."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-added_at"]
        unique_together = [("user", "product")]
        indexes = [models.Index(fields=["user", "product"])]
        verbose_name = _("Wishlist Item")
        verbose_name_plural = _("Wishlist Items")

    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"


class Banner(models.Model):
    BANNER_TYPES = [
        ("hero", "Hero Banner"),
        ("promo", "Promotional"),
        ("sidebar", "Sidebar"),
    ]

    image = models.CharField(max_length=500)
    title = models.CharField(max_length=180, blank=True)
    subtitle = models.CharField(max_length=255, blank=True)
    link_url = models.CharField(max_length=500, blank=True, verbose_name="Link URL")
    banner_type = models.CharField(max_length=20, choices=BANNER_TYPES, default="hero")
    active = models.BooleanField(default=True, db_column="is_active")
    sort_order = models.IntegerField(default=0)
    product = models.ForeignKey(
        "Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="banners",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")

    def __str__(self):
        return self.title or f"Banner #{self.id}"


class Coupon(models.Model):
    DISCOUNT_TYPES = [
        ("percentage", "Percentage (%)"),
        ("fixed", "Fixed Amount (PKR)"),
    ]

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default="percentage")
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percentage (e.g. 10 = 10%) or fixed amount")
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Minimum order amount")
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    used_count = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField()
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_coupons", verbose_name="Assigned User (for gift vouchers)")
    categories = models.ManyToManyField(Category, blank=True, verbose_name="Applicable Categories (leave empty for all)")
    is_gift = models.BooleanField(default=False, verbose_name="Gift voucher (auto-generated token)")
    auto_generated = models.BooleanField(default=False, editable=False, verbose_name="Auto-generated token")
    batch_id = models.CharField(max_length=36, null=True, blank=True, db_index=True, help_text="UUID grouping coupons from a bulk generation")
    emailed_at = models.DateTimeField(null=True, blank=True, help_text="When the coupon code was emailed to the assigned user")
    description = models.TextField(blank=True, verbose_name="Description / Admin note")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["code"]), models.Index(fields=["is_active", "valid_from", "valid_to"]), models.Index(fields=["batch_id"])]
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_to and (self.max_uses == 0 or self.used_count < self.max_uses)

    def calculate_discount(self, total):
        """Calculate discount amount for a given total."""
        if self.discount_type == "percentage":
            return (total * self.discount_value) / Decimal("100")
        return min(self.discount_value, total)


class DeliveryCharge(models.Model):
    """Manage delivery/shipping charges by city."""
    PROVINCE_CHOICES = [
        ("Punjab", "Punjab"),
        ("Sindh", "Sindh"),
        ("Khyber Pakhtunkhwa", "Khyber Pakhtunkhwa"),
        ("Balochistan", "Balochistan"),
        ("Gilgit-Baltistan", "Gilgit-Baltistan"),
        ("Azad Jammu & Kashmir", "Azad Jammu & Kashmir"),
        ("Islamabad", "Islamabad"),
    ]
    province = models.CharField(max_length=50, choices=PROVINCE_CHOICES, default="Punjab", verbose_name="Province / District")
    city = models.CharField(max_length=120, unique=True, verbose_name="City / Area")
    charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Default Delivery Charge (PKR)", help_text="Fallback charge used when no quantity tier matches")
    min_order_for_free = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), verbose_name="Min order for free delivery (0 = no free delivery)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["province", "city"]
        verbose_name = _("Delivery Charge")
        verbose_name_plural = _("Delivery Charges")

    def __str__(self):
        return f"{self.city}, {self.province} — RS {self.charge:,.0f}"

    @property
    def effective_charge(self, order_total=Decimal("0.00")):
        """Return 0 if order qualifies for free delivery, otherwise the charge."""
        if self.min_order_for_free > 0 and order_total >= self.min_order_for_free:
            return Decimal("0.00")
        return self.charge

    def get_charge_for_quantity(self, total_qty):
        """Return the applicable delivery charge based on total item quantity."""
        tier = self.tiers.filter(min_quantity__lte=total_qty).filter(
            models.Q(max_quantity__gte=total_qty) | models.Q(max_quantity__isnull=True)
        ).order_by("-min_quantity").first()
        if tier:
            return tier.charge
        return self.charge


class DeliveryChargeTier(models.Model):
    """Quantity-based pricing tiers for a delivery charge."""
    delivery_charge = models.ForeignKey(DeliveryCharge, on_delete=models.CASCADE, related_name="tiers")
    min_quantity = models.PositiveIntegerField(verbose_name="Min quantity")
    max_quantity = models.PositiveIntegerField(null=True, blank=True, verbose_name="Max quantity (leave blank for unlimited)")
    charge = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Charge (PKR)")

    class Meta:
        ordering = ["min_quantity"]
        verbose_name = _("Delivery Charge Tier")
        verbose_name_plural = _("Delivery Charge Tiers")

    def __str__(self):
        if self.max_quantity:
            return f"{self.delivery_charge.city}: Qty {self.min_quantity}-{self.max_quantity} → RS {self.charge:,.0f}"
        return f"{self.delivery_charge.city}: Qty {self.min_quantity}+ → RS {self.charge:,.0f}"


class Order(models.Model):
    PAYMENT_METHODS = [
        ("Cash on Delivery", "Cash on Delivery"),
        ("Online Payment", "Online Payment"),
        ("Card Payment", "Card Payment"),
        ("JazzCash", "JazzCash"),
        ("EasyPaisa", "EasyPaisa"),
        ("Bank Transfer", "Bank Transfer"),
    ]

    PAYMENT_STATUSES = [
        ("Unpaid", "Unpaid"),
        ("Paid", "Paid"),
        ("Partial", "Partial"),
        ("Rejected", "Rejected"),
        ("Refunded", "Refunded"),
    ]

    ORDER_STATUSES = [
        ("Pending", "Pending"),
        ("Payment Verification", "Payment Verification"),
        ("Processing", "Processing"),
        ("Shipped", "Shipped"),
        ("In Transit", "In Transit"),
        ("Delivered", "Delivered"),
        ("Completed", "Completed"),
        ("Cancelled", "Cancelled"),
        ("Returned", "Returned"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    customer_name = models.CharField(max_length=180, blank=True, verbose_name="Customer name (for manual orders)")
    customer_email = models.EmailField(max_length=254, blank=True, verbose_name="Customer email (for manual orders)")
    shipping_address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Subtotal (before discount)")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    due_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_method = models.CharField(max_length=40, choices=PAYMENT_METHODS, blank=True)
    payment_status = models.CharField(max_length=40, choices=PAYMENT_STATUSES, blank=True, default="Unpaid")
    order_status = models.CharField(max_length=40, choices=ORDER_STATUSES, blank=True, default="Pending")
    tracking_number = models.CharField(max_length=100, blank=True, verbose_name="Tracking / Reference number")
    notes = models.TextField(blank=True, verbose_name="Order notes")
    payment_proof = models.CharField(max_length=500, blank=True)
    is_priority = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["order_status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")

    @property
    def user_name(self):
        if self.customer_name:
            return self.customer_name
        return self.user.get_full_name() or self.user.username

    @property
    def user_email(self):
        if self.customer_email:
            return self.customer_email
        return self.user.email

    @property
    def item_count(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    def save(self, *args, **kwargs):
        """Auto-generate tracking number on first save."""
        if not self.tracking_number:
            super().save(*args, **kwargs)
            self.tracking_number = f"SHC-{self.id}-{int(timezone.now().timestamp())}"
            super().save(update_fields=["tracking_number"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Order #{self.id} by {self.user.email}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        indexes = [models.Index(fields=["order", "product"])]
        verbose_name = _("Order Item")
        verbose_name_plural = _("Order Items")

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.price * self.quantity

    @property
    def product_name(self):
        return self.product.name if self.product else "Deleted product"

    @property
    def image(self):
        return self.product.image if self.product else ""

    @property
    def unit_price(self):
        return self.price

    @property
    def product_image(self):
        return self.product.image if self.product else ""

    def __str__(self):
        name = self.product.name if self.product else "Deleted product"
        return f"{self.quantity}x {name} (Order #{self.order.id})"


class Setting(models.Model):
    key = models.CharField(max_length=120, primary_key=True)
    value = models.TextField(blank=True)

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = _("Setting")
        verbose_name_plural = _("Settings")


class Announcement(models.Model):
    message = models.TextField()
    is_flash_sale = models.BooleanField(default=False)
    active = models.BooleanField(default=True, db_column="is_active")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Announcement")
        verbose_name_plural = _("Announcements")

    def __str__(self):
        return self.message[:50]


class ContactMessage(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=180)
    message = models.TextField()
    reply = models.TextField(blank=True)
    status = models.CharField(max_length=40, default="new")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Contact Message")
        verbose_name_plural = _("Contact Messages")
        indexes = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.subject} - {self.name}"


class UserNotification(models.Model):
    """In-app notifications/mailbox for users (coupon alerts, order updates, etc.)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    subject = models.CharField(max_length=200)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL)
    review = models.ForeignKey(Review, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("User Notification")
        verbose_name_plural = _("User Notifications")
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{'Read' if self.is_read else 'Unread'}] {self.subject} — {self.user.email}"
