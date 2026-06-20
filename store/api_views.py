from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncMonth, TruncDay
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    UserNotification,
    Wishlist,
)
from .utils import get_setting, image_url, is_base64_data_url, save_upload


# ─── Pagination ───────────────────────────────────────────────────


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


# ─── Serializers ──────────────────────────────────────────────────


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "description", "image", "sort_order", "is_active", "discount_percentage", "product_count", "created_at"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "sort_order"]


class ProductVariantSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "size", "color", "color_code", "sku", "price_override", "effective_price", "stock", "image", "is_active"]


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    thumbnail = serializers.SerializerMethodField()
    discount_percentage = serializers.IntegerField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    profit_percentage = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "price", "compare_price", "retail_price", "discount_percentage",
            "profit_percentage", "stock", "category_name", "brand_name",
            "thumbnail", "status", "is_featured",
            "free_delivery", "min_quantity", "delivery_charge", "average_rating", "review_count", "created_at",
        ]

    def get_thumbnail(self, obj):
        return image_url(obj.image)


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_detail = CategorySerializer(source="category", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True, allow_null=True)
    brand_id = serializers.IntegerField(source="brand.id", read_only=True, allow_null=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(source="gallery_images", many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()
    thumbnail_url = serializers.CharField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)
    profit_percentage = serializers.IntegerField(read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "name", "slug", "description", "price", "compare_price", "retail_price",
            "discount_percentage", "profit_percentage", "stock", "is_in_stock", "category",
            "category_name", "category_detail", "brand_id", "brand_name",
            "image", "image_alt",
            "variants", "images", "thumbnail", "thumbnail_url", "status",
            "is_featured", "has_variants", "free_delivery", "min_quantity", "delivery_charge",
            "specifications", "tags",
            "meta_title", "meta_description", "meta_keywords",
            "average_rating", "review_count", "created_at", "updated_at",
        ]

    def get_thumbnail(self, obj):
        return image_url(obj.image)

    def get_tags(self, obj):
        if obj.tags:
            return [t.strip() for t in obj.tags.split(",") if t.strip()]
        return []


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "product", "user", "user_name", "rating", "title", "comment", "is_approved", "created_at"]
        read_only_fields = ["user", "is_approved", "created_at"]

    def get_user_name(self, obj):
        return obj.user.name

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class WishlistSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source="product", read_only=True)

    class Meta:
        model = Wishlist
        fields = ["id", "user", "product", "product_detail", "added_at"]
        read_only_fields = ["user", "added_at"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "product_image", "quantity", "price", "total"]

    def get_product_name(self, obj):
        return obj.product.name if obj.product else "Deleted product"

    def get_product_image(self, obj):
        if obj.product:
            return image_url(obj.product.image)
        return ""


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user_name = serializers.CharField(read_only=True)
    user_email = serializers.CharField(read_only=True)
    payment_proof_url = serializers.SerializerMethodField()
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = [
            "id", "user", "user_name", "user_email", "customer_name",
            "customer_email", "shipping_address", "city", "phone", "total",
            "subtotal", "discount_amount", "shipping_cost", "paid_amount",
            "due_amount", "payment_method", "payment_status", "order_status",
            "tracking_number", "notes", "payment_proof", "payment_proof_url",
            "items", "created_at", "updated_at", "coupon", "coupon_code",
        ]
        read_only_fields = ["user", "created_at", "updated_at"]

    def get_payment_proof_url(self, obj):
        """Return a list of proof image URLs (comma-separated field)."""
        if not obj.payment_proof:
            return []
        proofs = [p.strip() for p in obj.payment_proof.split(",") if p.strip()]
        return [image_url(p) for p in proofs]


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = "__all__"


class CouponSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            "id", "code", "discount_type", "discount_value",
            "min_order_amount", "max_uses", "used_count", "is_active",
            "valid_from", "valid_to", "is_valid", "created_at",
            "assigned_to", "categories", "is_gift", "auto_generated", "description",
            "batch_id", "emailed_at",
        ]


class DeliveryChargeTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryChargeTier
        fields = ["id", "delivery_charge", "min_quantity", "max_quantity", "charge"]


class DeliveryChargeSerializer(serializers.ModelSerializer):
    tiers = DeliveryChargeTierSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryCharge
        fields = ["id", "province", "city", "charge", "min_order_for_free", "is_active", "effective_charge", "tiers", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    order_count = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "username", "first_name", "last_name", "name",
            "address", "city", "state", "postal_code", "country", "phone",
            "is_suspended", "is_staff", "is_superuser", "is_active",
            "order_count", "total_spent", "date_joined",
        ]


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "message", "active", "is_flash_sale", "created_at"]


class ContactMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(read_only=True)
    user_email = serializers.CharField(read_only=True)

    class Meta:
        model = ContactMessage
        fields = "__all__"
        read_only_fields = ["user", "user_name", "user_email", "reply"]


# ─── Auth API Views ─────────────────────────────────────────────


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user and not user.is_suspended:
            from rest_framework_simplejwt.tokens import RefreshToken

            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserSerializer(user, context={"request": request}).data,
            })
        return Response({"error": "Invalid credentials or suspended account"}, status=status.HTTP_401_UNAUTHORIZED)


class SignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        name = request.data.get("name", "").strip()

        if not email or not password:
            return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response({"error": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        first_name, _, last_name = name.partition(" ")
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=request.data.get("phone", ""),
            address=request.data.get("address", ""),
            city=request.data.get("city", ""),
            state=request.data.get("state", ""),
            postal_code=request.data.get("postal_code", ""),
            country=request.data.get("country", ""),
        )

        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user, context={"request": request}).data,
        }, status=status.HTTP_201_CREATED)


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)


# ─── Cart API Views ──────────────────────────────────────────────


class CartAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        cart = request.session.get("cart", {})
        items = []
        total = Decimal("0.00")
        for product_id, qty in cart.items():
            try:
                product = Product.active.get(id=int(product_id))
                qty = int(qty)
                subtotal = product.price * qty
                items.append({
                    "product": {
                        "id": product.id,
                        "name": product.name,
                        "slug": product.slug,
                        "image": product.image,
                        "price": float(product.price),
                        "compare_price": float(product.compare_price) if product.compare_price else None,
                        "stock": product.stock,
                        "min_quantity": product.min_quantity,
                        "delivery_charge": float(product.delivery_charge),
                    },
                    "quantity": qty,
                    "total_price": float(subtotal),
                    "subtotal": float(subtotal),
                })
                total += subtotal
            except (Product.DoesNotExist, ValueError):
                continue
        return Response({
            "items": items,
            "total": float(total),
            "item_count": sum(item["quantity"] for item in items),
        })


class CartAddAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))
        try:
            product = Product.active.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        cart = request.session.get("cart", {})
        current_qty = int(cart.get(str(product_id), 0))
        new_qty = current_qty + quantity
        if new_qty > product.stock:
            return Response({"error": "Not enough stock"}, status=status.HTTP_400_BAD_REQUEST)

        cart[str(product_id)] = new_qty
        request.session["cart"] = cart
        return Response({
            "message": "Item added to cart",
            "cart_count": sum(int(q) for q in cart.values()),
            "cart": cart,
        })


class CartUpdateAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        cart = {}
        for item in request.data.get("items", []):
            pid = str(item.get("product_id"))
            qty = int(item.get("quantity", 0))
            if qty > 0:
                try:
                    product = Product.active.get(id=int(pid))
                    if qty <= product.stock:
                        cart[pid] = qty
                except Product.DoesNotExist:
                    pass
        request.session["cart"] = cart
        return Response({
            "message": "Cart updated",
            "cart_count": sum(cart.values()),
        })


class CartRemoveAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, product_id):
        cart = request.session.get("cart", {})
        cart.pop(str(product_id), None)
        request.session["cart"] = cart
        return Response({
            "message": "Item removed from cart",
            "cart_count": sum(int(q) for q in cart.values()),
        })


# ─── Checkout API Views ─────────────────────────────────────────


class CouponValidateAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code", "")
        total = Decimal(str(request.data.get("total", 0)))
        category_ids = request.data.get("category_ids", [])
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True)
            if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
                return Response({"valid": False, "message": "This coupon has reached its maximum usage limit"}, status=status.HTTP_400_BAD_REQUEST)
            if not coupon.is_valid:
                return Response({"valid": False, "message": "Coupon expired or invalid"}, status=status.HTTP_400_BAD_REQUEST)
            if total < coupon.min_order_amount:
                return Response({"valid": False, "message": f"Minimum order: RS {coupon.min_order_amount:,.0f}"}, status=status.HTTP_400_BAD_REQUEST)
            # Check if coupon is assigned to a specific user
            if coupon.assigned_to and (not request.user.is_authenticated or coupon.assigned_to != request.user):
                return Response({"valid": False, "message": "This coupon is not assigned to you"}, status=status.HTTP_400_BAD_REQUEST)
            # Check category restriction if coupon is limited to specific categories
            if coupon.categories.exists():
                if not category_ids:
                    return Response({"valid": False, "message": "Coupon not applicable to items in cart"}, status=status.HTTP_400_BAD_REQUEST)
                coupon_cat_ids = set(coupon.categories.values_list("id", flat=True))
                cart_cat_ids = set(category_ids)
                if not cart_cat_ids.intersection(coupon_cat_ids):
                    return Response({"valid": False, "message": "Coupon not applicable to items in cart"}, status=status.HTTP_400_BAD_REQUEST)
            discount = coupon.calculate_discount(total)
            return Response({
                "valid": True,
                "code": coupon.code,
                "discount": float(discount),
                "discount_type": coupon.discount_type,
                "discount_value": float(coupon.discount_value),
            })
        except Coupon.DoesNotExist:
            return Response({"valid": False, "message": "Invalid coupon code"}, status=status.HTTP_400_BAD_REQUEST)


class CheckoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cart = request.session.get("cart", {})
        if not cart:
            return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        items_data = []
        total = Decimal("0.00")
        category_ids = set()
        for pid, qty in cart.items():
            try:
                product = Product.active.get(id=int(pid))
                qty = int(qty)
                items_data.append({"product": product, "qty": qty})
                total += product.price * qty
                category_ids.add(product.category_id)
            except Product.DoesNotExist:
                continue

        if not items_data:
            return Response({"error": "No valid items in cart"}, status=status.HTTP_400_BAD_REQUEST)

        address = request.data.get("shipping_address", "")
        city = request.data.get("city", "")
        phone = request.data.get("phone", "")
        payment_method = request.data.get("payment_method", "Cash on Delivery")
        # Map frontend values to model choices
        if payment_method == "bank_transfer":
            payment_method = "Bank Transfer"
        if payment_method == "online":
            payment_method = "Online Payment"
        coupon_code = request.data.get("coupon_code", "").strip()
        delivery_charge_id = request.data.get("delivery_charge_id")

        # Handle payment proof upload
        payment_proof = ""
        if payment_method in ("Bank Transfer", "Online Payment"):
            proof_file = request.FILES.get("payment_proof")
            if payment_method == "Bank Transfer" and not proof_file:
                return Response({"error": "Payment proof screenshot is required for bank transfer"}, status=status.HTTP_400_BAD_REQUEST)
            if proof_file:
                payment_proof = save_upload(proof_file)

        # Apply coupon with category restriction check
        discount = Decimal("0.00")
        coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code__iexact=coupon_code)
                if coupon.max_uses > 0 and coupon.used_count >= coupon.max_uses:
                    return Response({"error": "This coupon has reached its maximum usage limit"}, status=status.HTTP_400_BAD_REQUEST)
                is_applicable = coupon.is_valid and total >= coupon.min_order_amount
                # Check if coupon is assigned to a specific user
                if coupon.assigned_to and coupon.assigned_to != request.user:
                    is_applicable = False
                # Check category restriction
                if is_applicable and coupon.categories.exists():
                    coupon_cat_ids = set(coupon.categories.values_list("id", flat=True))
                    if not category_ids.intersection(coupon_cat_ids):
                        is_applicable = False
                if is_applicable:
                    discount = coupon.calculate_discount(total)
                    coupon.used_count += 1
                    coupon.save(update_fields=["used_count"])
            except Coupon.DoesNotExist:
                pass

        # Calculate delivery charge — driven by delivery_mode setting:
        # "quantity" mode: per-product block pricing via min_quantity/delivery_charge
        # "city" mode: city-to-city delivery charges by province
        # Free delivery on ALL items overrides in both modes
        delivery_mode = get_setting("delivery_mode", "quantity")
        shipping_cost = Decimal("0.00")
        all_free_delivery = all(item["product"].free_delivery for item in items_data)
        if all_free_delivery:
            shipping_cost = Decimal("0.00")
        elif delivery_mode == "quantity":
            # Per-product block pricing
            per_product_charges = []
            for item in items_data:
                product = item["product"]
                qty = item["qty"]
                if product.min_quantity > 1 and product.delivery_charge > 0:
                    blocks = (qty + product.min_quantity - 1) // product.min_quantity
                    per_product_charges.append(blocks * product.delivery_charge)
            if per_product_charges:
                shipping_cost = sum(per_product_charges, Decimal("0.00"))
        else:
            # City-based delivery charge lookup
            if delivery_charge_id:
                try:
                    dc = DeliveryCharge.objects.get(id=delivery_charge_id, is_active=True)
                    total_qty = sum(item["qty"] for item in items_data)
                    shipping_cost = dc.get_charge_for_quantity(total_qty)
                except DeliveryCharge.DoesNotExist:
                    pass

        discounted_total = max(total - discount, Decimal("0.00"))
        grand_total = discounted_total + shipping_cost
        payment_status = "Unpaid" if payment_method == "Cash on Delivery" else "Pending"
        # Set order status to "Payment Verification" for bank transfers / online payments awaiting admin verification
        order_status = "Payment Verification" if payment_method in ("Bank Transfer", "Online Payment") else "Processing"

        order = Order.objects.create(
            user=request.user,
            shipping_address=address,
            city=city,
            phone=phone,
            total=grand_total,
            subtotal=total,
            discount_amount=discount,
            shipping_cost=shipping_cost,
            coupon=coupon,
            paid_amount=Decimal("0.00"),
            due_amount=grand_total,
            payment_method=payment_method,
            payment_status=payment_status,
            order_status=order_status,
            payment_proof=payment_proof,
        )

        for item in items_data:
            product = item["product"]
            OrderItem.objects.create(order=order, product=product, quantity=item["qty"], price=product.price)
            Product.objects.filter(id=product.id).update(stock=models.F("stock") - item["qty"])

        request.session["cart"] = {}
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ─── Track Order API View ────────────────────────────────────────


class TrackOrderAPIView(APIView):
    """Public endpoint to track an order by tracking number."""
    permission_classes = [AllowAny]

    def get(self, request):
        tracking_number = request.query_params.get("tracking_number", "").strip()
        if not tracking_number:
            return Response({"error": "Tracking number is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            order = Order.objects.get(tracking_number__iexact=tracking_number)
            serializer = OrderSerializer(order, context={"request": request})
            return Response(serializer.data)
        except Order.DoesNotExist:
            return Response({"error": "Order not found with that tracking number"}, status=status.HTTP_404_NOT_FOUND)


# ─── Delivery Charges API View (Public) ─────────────────────────


class DeliveryChargeListAPIView(APIView):
    """Public endpoint to get active delivery charges for checkout."""
    permission_classes = [AllowAny]

    def get(self, request):
        charges = DeliveryCharge.objects.filter(is_active=True)
        serializer = DeliveryChargeSerializer(charges, many=True)
        return Response(serializer.data)


class ProvinceListAPIView(APIView):
    """Public endpoint to list all province choices for the cascade selector."""
    permission_classes = [AllowAny]

    def get(self, request):
        choices = DeliveryCharge._meta.get_field("province").choices
        provinces = [{"value": key, "label": label} for key, label in choices]
        return Response(provinces)


class AdminDeliveryChargeListCreateAPIView(APIView):
    """Admin CRUD for delivery charges."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = DeliveryCharge.objects.all()
        province = request.query_params.get("province", "").strip()
        if province:
            qs = qs.filter(province=province)
        charges = qs.order_by("province", "city")
        serializer = DeliveryChargeSerializer(charges, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = DeliveryChargeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminDeliveryChargeDetailAPIView(APIView):
    """Admin retrieve / update / delete a single delivery charge."""
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        try:
            return DeliveryCharge.objects.get(id=pk)
        except DeliveryCharge.DoesNotExist:
            return None

    def get(self, request, pk):
        charge = self.get_object(pk)
        if not charge:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeSerializer(charge)
        return Response(serializer.data)

    def patch(self, request, pk):
        charge = self.get_object(pk)
        if not charge:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeSerializer(charge, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        charge = self.get_object(pk)
        if not charge:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        charge.delete()
        return Response({"message": "Deleted"})


class AdminDeliveryChargeTierListCreateAPIView(APIView):
    """Admin CRUD for quantity tiers of a delivery charge."""
    permission_classes = [IsAdminUser]

    def get(self, request, delivery_charge_id):
        try:
            dc = DeliveryCharge.objects.get(id=delivery_charge_id)
        except DeliveryCharge.DoesNotExist:
            return Response({"error": "Delivery charge not found"}, status=status.HTTP_404_NOT_FOUND)
        tiers = dc.tiers.all().order_by("min_quantity")
        serializer = DeliveryChargeTierSerializer(tiers, many=True)
        return Response(serializer.data)

    def post(self, request, delivery_charge_id):
        try:
            dc = DeliveryCharge.objects.get(id=delivery_charge_id)
        except DeliveryCharge.DoesNotExist:
            return Response({"error": "Delivery charge not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeTierSerializer(data={**request.data, "delivery_charge": dc.id})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminDeliveryChargeTierDetailAPIView(APIView):
    """Admin retrieve / update / delete a single tier."""
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        try:
            return DeliveryChargeTier.objects.get(id=pk)
        except DeliveryChargeTier.DoesNotExist:
            return None

    def get(self, request, pk):
        tier = self.get_object(pk)
        if not tier:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeTierSerializer(tier)
        return Response(serializer.data)

    def put(self, request, pk):
        tier = self.get_object(pk)
        if not tier:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeTierSerializer(tier, data={**request.data, "delivery_charge": tier.delivery_charge.id})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        tier = self.get_object(pk)
        if not tier:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = DeliveryChargeTierSerializer(tier, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        tier = self.get_object(pk)
        if not tier:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        tier.delete()
        return Response({"message": "Deleted"})


# ─── Admin Coupon Management API Views ────────────────────────


class AdminCouponListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        coupons = Coupon.objects.all().order_by("-created_at")
        assigned_to = request.GET.get("assigned_to")
        if assigned_to:
            coupons = coupons.filter(assigned_to_id=assigned_to)
        is_gift = request.GET.get("is_gift")
        if is_gift:
            coupons = coupons.filter(is_gift=(is_gift.lower() == "true"))

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(coupons, request)
        if page is not None:
            serializer = CouponSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = CouponSerializer(coupons, many=True)
        return Response(serializer.data)

    def post(self, request):
        import secrets
        import string
        import uuid

        from .services.email_service import send_coupon_email

        generate_token = request.data.get("generate_token", False)
        assign_to_all = request.data.get("assign_to_all", False)
        bulk_count = request.data.get("bulk_count", None)

        # ── "Generate for Everyone" Mode ──────────────────────────────
        if assign_to_all:
            active_users = User.objects.filter(is_active=True)
            if not active_users.exists():
                return Response({"error": "No active users found"}, status=status.HTTP_400_BAD_REQUEST)

            discount_type = request.data.get("discount_type", "percentage")
            discount_value = request.data.get("discount_value", 0)
            valid_days = int(request.data.get("valid_days", 30))
            valid_from = timezone.now()
            valid_to = valid_from + timedelta(days=valid_days)
            batch_id = str(uuid.uuid4())
            description = request.data.get("description", "Promotional voucher - auto generated")
            category_ids = request.data.get("categories", [])

            created_codes = []
            email_sent = 0
            alphabet = string.ascii_uppercase + string.digits
            for user in active_users:
                random_part = "".join(secrets.choice(alphabet) for _ in range(8))
                code = f"GIFT-{user.id}-{random_part}"
                coupon = Coupon.objects.create(
                    code=code,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    is_gift=True,
                    auto_generated=True,
                    assigned_to=user,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    description=description,
                    batch_id=batch_id,
                )
                if category_ids:
                    coupon.categories.set(category_ids)
                created_codes.append(code)

                # Create in-app notification
                UserNotification.objects.create(
                    user=user,
                    subject="You received a promotional coupon! 🎉",
                    body=f"Coupon code: {code} — {discount_value}{'%' if discount_type == 'percentage' else ' PKR'} off your next order.",
                    coupon=coupon,
                )

                # Send email
                if send_coupon_email(coupon, user):
                    email_sent += 1

            return Response({
                "message": f"Created coupons for {active_users.count()} users (emails sent: {email_sent})",
                "batch_id": batch_id,
                "count": len(created_codes),
                "emails_sent": email_sent,
            }, status=status.HTTP_201_CREATED)

        # ── Bulk Promotion Voucher Generation ─────────────────────────
        if bulk_count:
            try:
                count = int(bulk_count)
            except (ValueError, TypeError):
                return Response({"error": "Invalid bulk_count"}, status=status.HTTP_400_BAD_REQUEST)
            if count < 1 or count > 500:
                return Response({"error": "bulk_count must be between 1 and 500"}, status=status.HTTP_400_BAD_REQUEST)

            discount_type = request.data.get("discount_type", "percentage")
            discount_value = request.data.get("discount_value", 0)
            valid_days = int(request.data.get("valid_days", 30))
            valid_from = timezone.now()
            valid_to = valid_from + timedelta(days=valid_days)
            batch_id = str(uuid.uuid4())
            description = request.data.get("description", "Bulk promotion voucher")
            category_ids = request.data.get("categories", [])

            created_codes = []
            alphabet = string.ascii_uppercase + string.digits
            for i in range(count):
                random_part = "".join(secrets.choice(alphabet) for _ in range(10))
                code = f"BULK-{random_part}"
                coupon = Coupon.objects.create(
                    code=code,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    auto_generated=True,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    description=description,
                    batch_id=batch_id,
                )
                if category_ids:
                    coupon.categories.set(category_ids)
                created_codes.append(code)

            return Response({
                "message": f"Created {count} bulk promotion vouchers",
                "batch_id": batch_id,
                "count": count,
            }, status=status.HTTP_201_CREATED)

        # ── Single Gift Token Generation ──────────────────────────────
        if generate_token:
            token_length = int(request.data.get("token_length", 12))
            discount_type = request.data.get("discount_type", "percentage")
            discount_value = request.data.get("discount_value", 0)
            assigned_user_id = request.data.get("assigned_to")
            valid_from = timezone.now()
            valid_days = int(request.data.get("valid_days", 30))
            valid_to = valid_from + timedelta(days=valid_days)

            alphabet = string.ascii_uppercase + string.digits
            code = "GIFT-" + "".join(secrets.choice(alphabet) for _ in range(token_length))

            coupon = Coupon.objects.create(
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                is_gift=True,
                auto_generated=True,
                assigned_to_id=assigned_user_id or None,
                valid_from=valid_from,
                valid_to=valid_to,
                description=request.data.get("description", "Gift voucher - auto generated"),
            )
            category_ids = request.data.get("categories", [])
            if category_ids:
                coupon.categories.set(category_ids)

            # Create notification if assigned to a user
            if assigned_user_id:
                try:
                    assigned_user = User.objects.get(id=assigned_user_id)
                    UserNotification.objects.create(
                        user=assigned_user,
                        subject="You received a gift coupon! 🎁",
                        body=f"Coupon code: {code} — {discount_value}{'%' if discount_type == 'percentage' else ' PKR'} off your next order.",
                        coupon=coupon,
                    )
                    # Send email to assigned user
                    send_coupon_email(coupon, assigned_user)
                except User.DoesNotExist:
                    pass

            serializer = CouponSerializer(coupon)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # ── Regular Coupon Creation ───────────────────────────────────
        serializer = CouponSerializer(data=request.data)
        if serializer.is_valid():
            coupon = serializer.save()
            category_ids = request.data.get("categories", [])
            if category_ids:
                coupon.categories.set(category_ids)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminCouponDetailAPIView(APIView):
    """Admin retrieve / update / delete a single coupon."""
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        try:
            return Coupon.objects.get(id=pk)
        except Coupon.DoesNotExist:
            return None

    def get(self, request, pk):
        coupon = self.get_object(pk)
        if not coupon:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = CouponSerializer(coupon)
        return Response(serializer.data)

    def patch(self, request, pk):
        coupon = self.get_object(pk)
        if not coupon:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = CouponSerializer(coupon, data=request.data, partial=True)
        if serializer.is_valid():
            coupon = serializer.save()
            if "categories" in request.data:
                coupon.categories.set(request.data.get("categories", []))
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        coupon = self.get_object(pk)
        if not coupon:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        coupon.delete()
        return Response({"message": "Deleted"})


# ─── CSV Export ──────────────────────────────────────────────────


class AdminCouponExportCSVAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        import csv
        from django.http import HttpResponse

        coupons = Coupon.objects.all().order_by("-created_at")

        # Optional filtering by query params
        is_active = request.query_params.get("is_active")
        discount_type = request.query_params.get("discount_type")
        batch_id = request.query_params.get("batch_id")

        if is_active is not None:
            coupons = coupons.filter(is_active=is_active.lower() in ("true", "1"))
        if discount_type:
            coupons = coupons.filter(discount_type=discount_type)
        if batch_id:
            coupons = coupons.filter(batch_id=batch_id)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="coupons.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "ID", "Code", "Discount Type", "Discount Value",
            "Min Order", "Max Uses", "Times Used", "Is Active",
            "Is Gift", "Auto Generated", "Assigned To",
            "Valid From", "Valid Until", "Created At",
            "Batch ID", "Emailed At",
        ])

        for c in coupons:
            writer.writerow([
                c.id, c.code, c.discount_type, c.discount_value,
                c.min_order_amount, c.max_uses, c.used_count, c.is_active,
                c.is_gift, c.auto_generated,
                c.assigned_to.username if c.assigned_to else "",
                c.valid_from, c.valid_to, c.created_at,
                c.batch_id or "", c.emailed_at or "",
            ])

        return response


# ─── User Notification Serializer ────────────────────────────────


class UserNotificationSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, allow_null=True)
    coupon_discount = serializers.SerializerMethodField()
    review_detail = ReviewSerializer(source="review", read_only=True)

    class Meta:
        model = UserNotification
        fields = [
            "id", "subject", "body", "is_read",
            "coupon", "coupon_code", "coupon_discount",
            "review", "review_detail",
            "created_at",
        ]

    def get_coupon_discount(self, obj):
        if obj.coupon:
            return f"{obj.coupon.discount_value}{'%' if obj.coupon.discount_type == 'percent' else ''}"
        return None


# ─── User Notification API ───────────────────────────────────────


class UserNotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = UserNotification.objects.filter(user=request.user)
        serializer = UserNotificationSerializer(notifications, many=True)
        return Response(serializer.data)

    def patch(self, request):
        notification_id = request.data.get("notification_id")

        if notification_id:
            # Mark single notification as read
            UserNotification.objects.filter(
                id=notification_id, user=request.user
            ).update(is_read=True)
        else:
            # Mark all as read
            UserNotification.objects.filter(user=request.user).update(is_read=True)

        return Response({"message": "Notifications updated"})


# ─── User Profile API Views ──────────────────────────────────────


class UserProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        for field in ["first_name", "last_name", "name", "address", "city", "state", "postal_code", "country", "phone"]:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save(update_fields=[f for f in ["first_name", "last_name", "name", "address", "city", "state", "postal_code", "country", "phone"] if f in request.data])
        serializer = UserSerializer(user, context={"request": request})
        return Response(serializer.data)


class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password", "")
        new_password = request.data.get("new_password", "")

        if not user.check_password(old_password):
            return Response({"error": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return Response({"error": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password changed successfully"})


# ─── Site Settings API ────────────────────────────────────────────


class SiteSettingsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from .utils import settings_dict

        data = settings_dict()
        cart = request.session.get("cart", {})
        data["cart_count"] = sum(int(q) for q in cart.values())
        # Get active announcements
        announcements = Announcement.objects.filter(active=True)
        data["announcements"] = AnnouncementSerializer(announcements, many=True).data
        return Response(data)


# ─── Contact API ─────────────────────────────────────────────────


class AnnouncementListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        announcements = Announcement.objects.filter(active=True).order_by("-created_at")
        serializer = AnnouncementSerializer(announcements, many=True)
        return Response(serializer.data)


class ContactAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        name = request.data.get("name", "")
        email = request.data.get("email", "")
        subject = request.data.get("subject", "")
        message = request.data.get("message", "")

        if not all([name, email, message]):
            return Response({"error": "Name, email, and message are required"}, status=status.HTTP_400_BAD_REQUEST)

        contact = ContactMessage.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=name,
            email=email,
            subject=subject,
            message=message,
        )
        return Response({"message": "Message sent successfully", "id": contact.id}, status=status.HTTP_201_CREATED)


class UserContactMessageListAPIView(APIView):
    """Authenticated user can list their own contact messages."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = ContactMessage.objects.filter(user=request.user)
        serializer = ContactMessageSerializer(messages, many=True)
        return Response(serializer.data)


# ─── Admin API Views ──────────────────────────────────────────────


class AdminDashboardAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        total_products = Product.objects.count()
        total_users = User.objects.count()
        total_orders = Order.objects.count()
        total_revenue = Order.objects.aggregate(s=Sum("paid_amount"))["s"] or 0
        pending_orders = Order.objects.filter(order_status="Processing").count()
        pending_payments = Order.objects.filter(payment_status="Pending").count()
        low_stock = Product.objects.filter(stock__lte=5).count()
        recent_orders = Order.objects.order_by("-created_at")[:10]

        # Total profit = sum of (sale_price - retail_price) * quantity across paid orders
        paid_orders = Order.objects.filter(payment_status__in=["Paid", "Approved"])
        total_profit = Decimal("0.00")
        for order in paid_orders:
            for item in order.items.select_related("product"):
                if not item.product:
                    continue
                sale_price = item.price
                retail = item.product.retail_price
                if retail and retail > 0:
                    total_profit += (sale_price - retail) * Decimal(str(item.quantity))

        return Response({
            "total_products": total_products,
            "total_users": total_users,
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "total_profit": float(total_profit),
            "pending_orders": pending_orders,
            "pending_payments": pending_payments,
            "low_stock": low_stock,
            "recent_orders": OrderSerializer(recent_orders, many=True, context={"request": request}).data,
        })


class AdminProductListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        products = Product.objects.all().select_related("category")
        search = request.GET.get("search", "")
        status_filter = request.GET.get("status", "")
        if search:
            products = products.filter(Q(name__icontains=search) | Q(tags__icontains=search))
        if status_filter:
            # Convert string filter to boolean for BooleanField
            products = products.filter(status=(status_filter == "active"))
        products = products.order_by("-created_at")
        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        name = request.data.get("name", "")
        if not name:
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)

        category_id = request.data.get("category")
        category = Category.objects.get(id=category_id) if category_id else None

        brand_id = request.data.get("brand")
        brand = Brand.objects.get(id=brand_id) if brand_id else None

        image_file = request.FILES.get("image")
        raw_image = request.data.get("image", "")
        if image_file:
            image = save_upload(image_file)
        elif raw_image and not is_base64_data_url(raw_image):
            image = raw_image
        else:
            image = ""

        # Convert status string ("active"/"inactive") to boolean for BooleanField
        raw_status = request.data.get("status", "true")
        if isinstance(raw_status, str):
            status_value = raw_status.lower() in ("true", "active", "1")
        else:
            status_value = bool(raw_status)

        # Convert FormData string values to proper types
        try:
            stock_val = int(request.data.get("stock", 0))
        except (ValueError, TypeError):
            stock_val = 0

        def _to_bool(val, default=False):
            if isinstance(val, str):
                return val.lower() in ("true", "1")
            return bool(val) if val is not None else default

        try:
            min_qty = int(request.data.get("min_quantity", 1))
        except (ValueError, TypeError):
            min_qty = 1

        raw_price = request.data.get("price", 0)
        try:
            price_val = Decimal(str(raw_price))
        except Exception:
            price_val = Decimal("0.00")

        raw_compare = request.data.get("compare_price")
        if raw_compare in (None, "", "null", "undefined"):
            compare_val = None
        else:
            try:
                compare_val = Decimal(str(raw_compare))
            except Exception:
                compare_val = None

        raw_retail = request.data.get("retail_price", 0)
        try:
            retail_val = Decimal(str(raw_retail))
        except Exception:
            retail_val = Decimal("0.00")

        product = Product.objects.create(
            name=name,
            category=category,
            brand=brand,
            price=price_val,
            compare_price=compare_val,
            retail_price=retail_val,
            description=request.data.get("description", ""),
            stock=stock_val,
            status=status_value,
            is_featured=_to_bool(request.data.get("is_featured")),
            has_variants=_to_bool(request.data.get("has_variants")),
            free_delivery=_to_bool(request.data.get("free_delivery")),
            min_quantity=min_qty,
            delivery_charge=request.data.get("delivery_charge", 0),
            tags=request.data.get("tags", ""),
            image=image,
            specifications=request.data.get("specifications", {}),
            meta_title=request.data.get("meta_title", ""),
            meta_description=request.data.get("meta_description", ""),
            meta_keywords=request.data.get("meta_keywords", ""),
        )
        serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminProductDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Simple string fields
        for field in ("name", "description", "tags"):
            if field in request.data:
                setattr(product, field, request.data[field])

        if "price" in request.data:
            try:
                product.price = Decimal(str(request.data["price"]))
            except Exception:
                pass

        if "compare_price" in request.data:
            val = request.data["compare_price"]
            if val in (None, "", "null", "undefined"):
                product.compare_price = None
            else:
                try:
                    product.compare_price = Decimal(str(val))
                except Exception:
                    pass

        if "retail_price" in request.data:
            try:
                product.retail_price = Decimal(str(request.data["retail_price"]))
            except (ValueError, TypeError):
                pass

        # Stock — ensure it's cast to int so PositiveIntegerField doesn't choke
        if "stock" in request.data:
            try:
                product.stock = int(request.data["stock"])
            except (ValueError, TypeError):
                pass

        # min_quantity — integer field
        if "min_quantity" in request.data:
            try:
                product.min_quantity = int(request.data["min_quantity"])
            except (ValueError, TypeError):
                pass

        # delivery_charge — decimal field
        if "delivery_charge" in request.data:
            try:
                product.delivery_charge = Decimal(str(request.data["delivery_charge"]))
            except (ValueError, TypeError):
                pass

        # Boolean fields — FormData sends "true"/"false" as strings, convert properly
        for bool_field in ("is_featured", "has_variants", "free_delivery"):
            if bool_field in request.data:
                raw = request.data[bool_field]
                if isinstance(raw, str):
                    setattr(product, bool_field, raw.lower() in ("true", "1"))
                else:
                    setattr(product, bool_field, bool(raw))

        # Handle status separately — convert string to boolean for BooleanField
        if "status" in request.data:
            raw_status = request.data["status"]
            if isinstance(raw_status, str):
                product.status = raw_status.lower() in ("true", "active", "1")
            else:
                product.status = bool(raw_status)

        if "category" in request.data:
            try:
                product.category = Category.objects.get(id=request.data["category"])
            except (Category.DoesNotExist, ValueError):
                pass

        # Brand — convert brand_id to Brand FK
        if "brand" in request.data:
            brand_val = request.data["brand"]
            if brand_val in (None, "", "null", "undefined"):
                product.brand = None
            else:
                try:
                    product.brand = Brand.objects.get(id=int(brand_val))
                except (Brand.DoesNotExist, ValueError, TypeError):
                    pass

        # SEO meta fields — simple string fields
        for meta_field in ("meta_title", "meta_description", "meta_keywords"):
            if meta_field in request.data:
                setattr(product, meta_field, request.data[meta_field])

        # image_alt
        if "image_alt" in request.data:
            product.image_alt = request.data["image_alt"]

        image_file = request.FILES.get("image")
        if image_file:
            product.image = save_upload(image_file)
        elif "image" in request.data and request.data["image"]:
            if not is_base64_data_url(request.data["image"]):
                product.image = request.data["image"]

        product.save()
        serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(serializer.data)

    def delete(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
            product.delete()
            return Response({"message": "Product deleted"})
        except Product.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


# ─── Admin Product Variant CRUD ────────────────────────────────────


class AdminProductVariantListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        variants = product.variants.all()
        serializer = ProductVariantSerializer(variants, many=True)
        return Response(serializer.data)

    def post(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        image_file = request.FILES.get("image")
        raw_image = request.data.get("image", "")
        if image_file:
            image = save_upload(image_file)
        elif raw_image and not is_base64_data_url(raw_image):
            image = raw_image
        else:
            image = ""

        raw_price = request.data.get("price_override")
        price_override = None
        if raw_price not in (None, "", "null", "undefined"):
            try:
                price_override = Decimal(str(raw_price))
            except Exception:
                pass

        try:
            stock = int(request.data.get("stock", 0))
        except (ValueError, TypeError):
            stock = 0

        is_active_raw = request.data.get("is_active", "true")
        if isinstance(is_active_raw, str):
            is_active = is_active_raw.lower() in ("true", "1", "yes")
        else:
            is_active = bool(is_active_raw)

        variant = ProductVariant.objects.create(
            product=product,
            size=request.data.get("size", ""),
            color=request.data.get("color", ""),
            color_code=request.data.get("color_code", ""),
            sku=request.data.get("sku", ""),
            price_override=price_override,
            stock=stock,
            image=image,
            is_active=is_active,
        )
        serializer = ProductVariantSerializer(variant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminProductVariantDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get_object(self, variant_id):
        try:
            return ProductVariant.objects.get(id=variant_id)
        except ProductVariant.DoesNotExist:
            return None

    def patch(self, request, *args, **kwargs):
        variant_id = kwargs.get("variant_id")
        variant = self.get_object(variant_id)
        if not variant:
            return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)

        for field in ("size", "color", "color_code", "sku"):
            if field in request.data:
                setattr(variant, field, request.data[field])

        raw_price = request.data.get("price_override")
        if raw_price is not None:
            if raw_price in ("", "null", "undefined"):
                variant.price_override = None
            else:
                try:
                    variant.price_override = Decimal(str(raw_price))
                except Exception:
                    pass

        if "stock" in request.data:
            try:
                variant.stock = int(request.data["stock"])
            except (ValueError, TypeError):
                pass

        if "is_active" in request.data:
            raw = request.data["is_active"]
            if isinstance(raw, str):
                variant.is_active = raw.lower() in ("true", "1")
            else:
                variant.is_active = bool(raw)

        image_file = request.FILES.get("image")
        if image_file:
            variant.image = save_upload(image_file)

        variant.save()
        serializer = ProductVariantSerializer(variant)
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        variant_id = kwargs.get("variant_id")
        variant = self.get_object(variant_id)
        if not variant:
            return Response({"error": "Variant not found"}, status=status.HTTP_404_NOT_FOUND)
        variant.delete()
        return Response({"message": "Variant deleted"})


# ─── Admin Product Gallery Images CRUD ─────────────────────────────


class AdminProductGalleryListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        images = product.gallery_images.all().order_by("sort_order")
        serializer = ProductImageSerializer(images, many=True)
        return Response(serializer.data)

    def post(self, request, product_id):
        """Upload one or more gallery images for a product."""
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        created = []
        # Handle single file
        image_file = request.FILES.get("image")
        if image_file:
            filename = save_upload(image_file)
            img = ProductImage.objects.create(
                product=product,
                image=filename,
                alt_text=request.data.get("alt_text", ""),
                sort_order=request.data.get("sort_order", 0),
            )
            created.append(img)

        # Handle multiple files (images[])
        files = request.FILES.getlist("images")
        for i, f in enumerate(files):
            filename = save_upload(f)
            img = ProductImage.objects.create(
                product=product,
                image=filename,
                alt_text=request.data.get(f"alt_text_{i}", ""),
                sort_order=request.data.get(f"sort_order_{i}", i),
            )
            created.append(img)

        serializer = ProductImageSerializer(created, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminProductGalleryDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get_object(self, image_id):
        try:
            return ProductImage.objects.get(id=image_id)
        except ProductImage.DoesNotExist:
            return None

    def patch(self, request, *args, **kwargs):
        image_id = kwargs.get("image_id")
        img = self.get_object(image_id)
        if not img:
            return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)

        if "alt_text" in request.data:
            img.alt_text = request.data["alt_text"]
        if "sort_order" in request.data:
            try:
                img.sort_order = int(request.data["sort_order"])
            except (ValueError, TypeError):
                pass

        image_file = request.FILES.get("image")
        if image_file:
            img.image = save_upload(image_file)

        img.save()
        serializer = ProductImageSerializer(img)
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        image_id = kwargs.get("image_id")
        img = self.get_object(image_id)
        if not img:
            return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)
        img.delete()
        return Response({"message": "Gallery image deleted"})


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "description", "image", "website", "is_active", "product_count", "created_at"]


class AdminBrandListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        brands = Brand.objects.annotate(product_count=Count("products")).order_by("name")
        serializer = BrandSerializer(brands, many=True)
        return Response(serializer.data)


class AdminCategoryListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        categories = Category.objects.all().order_by("sort_order")
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)

    def post(self, request):
        name = request.data.get("name", "")
        if not name:
            return Response({"error": "Name is required"}, status=status.HTTP_400_BAD_REQUEST)

        raw_image = request.data.get("image", "")
        image_file = request.FILES.get("image")
        if image_file:
            image = save_upload(image_file)
        elif raw_image and not is_base64_data_url(raw_image):
            image = raw_image
        else:
            image = ""

        category = Category.objects.create(
            name=name,
            description=request.data.get("description", ""),
            image=image,
            sort_order=request.data.get("sort_order", 0),
            discount_percentage=request.data.get("discount_percentage", Decimal("0.00")),
            is_active=request.data.get("is_active", True),
        )
        serializer = CategorySerializer(category)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminCategoryDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get_object(self, pk):
        try:
            return Category.objects.get(id=pk)
        except Category.DoesNotExist:
            return None

    def patch(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if "name" in request.data:
            category.name = request.data["name"]
        if "description" in request.data:
            category.description = request.data["description"]
        if "sort_order" in request.data:
            category.sort_order = request.data["sort_order"]
        if "discount_percentage" in request.data:
            category.discount_percentage = request.data["discount_percentage"]
        if "is_active" in request.data:
            category.is_active = request.data["is_active"]
        if "image" in request.data:
            raw_image = request.data["image"]
            if not is_base64_data_url(raw_image):
                category.image = raw_image
        category.save()
        serializer = CategorySerializer(category)
        return Response(serializer.data)

    def delete(self, request, pk):
        category = self.get_object(pk)
        if not category:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        category.delete()
        return Response({"message": "Deleted"}, status=status.HTTP_204_NO_CONTENT)


class AdminOrderCreateAPIView(APIView):
    """Admin can create a manual order with custom customer details and products."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        # ── Customer details ──────────────────────────────────────
        user_id = request.data.get("user_id")
        customer_name = request.data.get("customer_name", "").strip()
        customer_email = request.data.get("customer_email", "").strip()
        customer_phone = request.data.get("customer_phone", "").strip()
        shipping_address = request.data.get("shipping_address", "").strip()
        city = request.data.get("city", "").strip()
        province = request.data.get("province", "").strip()

        # ── Order meta ────────────────────────────────────────────
        payment_method = request.data.get("payment_method", "Cash on Delivery")
        payment_status = request.data.get("payment_status", "Unpaid")
        order_status = request.data.get("order_status", "Pending")
        paid_amount = Decimal(str(request.data.get("paid_amount", 0)))
        notes = request.data.get("notes", "").strip()
        tracking_number = request.data.get("tracking_number", "").strip()

        # ── Items ─────────────────────────────────────────────────
        items_data = request.data.get("items", [])
        if not items_data:
            return Response({"error": "At least one product is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not customer_name and not user_id:
            return Response({"error": "Customer name or user is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Resolve user ──────────────────────────────────────────
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # ── Build item list & compute totals ──────────────────────
        order_items = []
        subtotal = Decimal("0.00")
        for idx, item in enumerate(items_data):
            product_id = item.get("product_id")
            quantity = int(item.get("quantity", 1))
            if not product_id:
                return Response({"error": f"Item {idx}: product_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                product = Product.active.get(id=product_id)
            except Product.DoesNotExist:
                return Response({"error": f"Item {idx}: Product #{product_id} not found"}, status=status.HTTP_404_NOT_FOUND)

            # Allow admin to override price; otherwise use product price
            price = Decimal(str(item.get("price", product.price)))
            line_total = price * quantity
            subtotal += line_total
            order_items.append({
                "product": product,
                "quantity": quantity,
                "price": price,
                "total": line_total,
            })

        # ── Delivery charge (optional) ────────────────────────────
        shipping_cost = Decimal(str(request.data.get("shipping_cost", 0)))
        discount_amount = Decimal(str(request.data.get("discount_amount", 0)))
        grand_total = max(subtotal + shipping_cost - discount_amount, Decimal("0.00"))

        # ── Create the Order ──────────────────────────────────────
        order = Order.objects.create(
            user=user or request.user,
            customer_name=customer_name,
            customer_email=customer_email,
            shipping_address=shipping_address,
            city=city,
            phone=customer_phone,
            total=grand_total,
            subtotal=subtotal,
            discount_amount=discount_amount,
            shipping_cost=shipping_cost,
            paid_amount=paid_amount,
            due_amount=max(grand_total - paid_amount, Decimal("0.00")),
            payment_method=payment_method,
            payment_status=payment_status,
            order_status=order_status,
            notes=notes,
            tracking_number=tracking_number,
        )

        # Append extra customer info to notes for manual orders (no user linked)
        if not user and customer_name:
            order.notes = (f"[Manual Order] Customer: {customer_name}"
                           f"{' | Email: ' + customer_email if customer_email else ''}"
                           f"{' | Phone: ' + customer_phone if customer_phone else ''}"
                           f"\n{order.notes}").strip()
            # Save the updated notes
            Order.objects.filter(id=order.id).update(notes=order.notes)

        # ── Create OrderItems & deduct stock ──────────────────────
        for oi in order_items:
            OrderItem.objects.create(
                order=order,
                product=oi["product"],
                quantity=oi["quantity"],
                price=oi["price"],
            )
            Product.objects.filter(id=oi["product"].id).update(
                stock=models.F("stock") - oi["quantity"]
            )

        # ── Notify user if linked ─────────────────────────────────
        if user:
            UserNotification.objects.create(
                user=user,
                notification_type="order",
                title="New Order Created (Admin)",
                message=f"An order #{order.id} has been created for you by the admin. Total: RS {grand_total:,.0f}",
            )

        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminOrderListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        orders = Order.objects.all().prefetch_related("items__product").order_by("-created_at")
        payment_status = request.GET.get("payment_status", "")
        order_status = request.GET.get("order_status", "")
        if payment_status:
            orders = orders.filter(payment_status=payment_status)
        if order_status:
            orders = orders.filter(order_status=order_status)
        serializer = OrderSerializer(orders, many=True, context={"request": request})
        return Response(serializer.data)


class AdminOrderDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, order_id):
        try:
            order = Order.objects.prefetch_related("items__product").get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class AdminOrderStatusAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status", "")
        if new_status:
            order.order_status = new_status

        if "paid_amount" in request.data:
            paid = Decimal(str(request.data["paid_amount"]))
            order.paid_amount = paid
            order.due_amount = max(order.total - paid, Decimal("0.00"))

            # Auto-determine payment_status based on paid_amount vs total
            if paid >= order.total:
                order.payment_status = "Paid"
                # Only auto-set order_status if user didn't explicitly provide one
                if not new_status:
                    order.order_status = "Pending"
            elif paid > 0:
                order.payment_status = "Partial"
            else:
                order.payment_status = "Rejected"
                if not new_status:
                    order.order_status = "Cancelled"
        elif "payment_status" in request.data:
            order.payment_status = request.data["payment_status"]

        if "tracking_number" in request.data:
            order.tracking_number = request.data["tracking_number"]
        if "notes" in request.data:
            order.notes = request.data["notes"]

        order.save()
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class AdminOrderDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, order_id):
        try:
            order = Order.objects.prefetch_related("items__product", "items__variant").get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # ── Reverse stock ──────────────────────────────────────────────
        for item in order.items.all():
            product = item.product
            if not product.has_variants:
                product.stock += item.quantity
                product.save(update_fields=["stock"])
            else:
                variant = item.variant
                if variant:
                    variant.stock += item.quantity
                    variant.save(update_fields=["stock"])

        # ── Reverse coupon usage count ─────────────────────────────────
        if order.coupon:
            coupon = order.coupon
            if coupon.used_count > 0:
                coupon.used_count -= 1
                coupon.save(update_fields=["used_count"])

        # ── Delete the order (cascades to OrderItem) ───────────────────
        order.delete()

        return Response({"message": "Order deleted and stock reversed"})


class AdminUserListAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by("-date_joined")
        search = request.GET.get("search", "")
        if search:
            users = users.filter(Q(email__icontains=search) | Q(name__icontains=search) | Q(phone__icontains=search))
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserSerializer(user)
        orders = Order.objects.filter(user=user).prefetch_related("items__product").order_by("-created_at")
        return Response({
            "user": serializer.data,
            "orders": OrderSerializer(orders, many=True, context={"request": request}).data,
        })


class AdminUserToggleAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.is_suspended = not user.is_suspended
            user.save(update_fields=["is_suspended"])
            return Response({
                "message": f"User {'suspended' if user.is_suspended else 'activated'}",
                "is_suspended": user.is_suspended,
            })
        except User.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


class AdminBannerListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        banners = Banner.objects.all().order_by("sort_order")
        serializer = BannerSerializer(banners, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Create a single banner."""
        image_file = request.FILES.get("image")
        raw_image = request.data.get("image", "")
        if image_file:
            image = save_upload(image_file)
        elif raw_image and not is_base64_data_url(raw_image):
            image = raw_image
        else:
            image = ""
        product_id = request.data.get("product")
        product = None
        if product_id:
            try:
                product = Product.objects.get(id=int(product_id))
            except (Product.DoesNotExist, ValueError, TypeError):
                pass
        banner = Banner.objects.create(
            title=request.data.get("title", ""),
            subtitle=request.data.get("subtitle", ""),
            image=image,
            link_url=request.data.get("link_url", ""),
            banner_type=request.data.get("banner_type", "hero"),
            active=request.data.get("active", True),
            sort_order=request.data.get("sort_order", 0),
            product=product,
        )
        serializer = BannerSerializer(banner)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminBannerBulkCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        """Create multiple banners at once."""
        import json
        banners_raw = request.data.get("banners", [])
        if isinstance(banners_raw, str):
            try:
                banners_data = json.loads(banners_raw)
            except (json.JSONDecodeError, TypeError):
                return Response({"error": "Invalid banners JSON"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            banners_data = banners_raw
        if not banners_data:
            return Response({"error": "No banners data provided"}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        files = request.FILES
        for i, item in enumerate(banners_data):
            image_key = item.get("image_key", "")
            image_file = files.get(image_key) if image_key else None
            raw_image = item.get("image", "")
            if image_file:
                image = save_upload(image_file)
            elif raw_image and not is_base64_data_url(raw_image):
                image = raw_image
            else:
                image = ""

            product_id = item.get("product")
            product = None
            if product_id:
                try:
                    product = Product.objects.get(id=int(product_id))
                except (Product.DoesNotExist, ValueError, TypeError):
                    pass

            banner = Banner.objects.create(
                title=item.get("title", ""),
                subtitle=item.get("subtitle", ""),
                image=image,
                link_url=item.get("link_url", ""),
                banner_type=item.get("banner_type", "hero"),
                active=item.get("active", True),
                sort_order=item.get("sort_order", 0),
                product=product,
            )
            created.append(banner)

        serializer = BannerSerializer(created, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminBannerToggleDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, banner_id):
        try:
            banner = Banner.objects.get(id=banner_id)
            banner.active = not banner.active
            banner.save(update_fields=["active"])
            return Response({"active": banner.active})
        except Banner.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, banner_id):
        try:
            Banner.objects.get(id=banner_id).delete()
            return Response({"message": "Banner deleted"})
        except Banner.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


class AdminBannerReorderAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, banner_id, direction):
        try:
            banner = Banner.objects.get(id=banner_id)
        except Banner.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        swap_with = None
        if direction == "up":
            swap_with = Banner.objects.filter(sort_order__lt=banner.sort_order).order_by("-sort_order").first()
        elif direction == "down":
            swap_with = Banner.objects.filter(sort_order__gt=banner.sort_order).order_by("sort_order").first()

        if swap_with:
            banner.sort_order, swap_with.sort_order = swap_with.sort_order, banner.sort_order
            banner.save(update_fields=["sort_order"])
            swap_with.save(update_fields=["sort_order"])

        return Response({"message": f"Banner moved {direction}"})


class AdminAnnouncementListCreateAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        announcements = Announcement.objects.all().order_by("-created_at")
        serializer = AnnouncementSerializer(announcements, many=True)
        return Response(serializer.data)

    def post(self, request):
        announcement = Announcement.objects.create(
            message=request.data.get("message", ""),
            is_flash_sale=request.data.get("is_flash_sale", False),
            active=request.data.get("active", True),
        )
        serializer = AnnouncementSerializer(announcement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminAnnouncementToggleAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            ann = Announcement.objects.get(id=pk)
            ann.active = not ann.active
            ann.save(update_fields=["active"])
            return Response({"active": ann.active})
        except Announcement.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


class AdminAnnouncementDeleteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def delete(self, request, pk):
        try:
            Announcement.objects.get(id=pk).delete()
            return Response({"message": "Deleted"})
        except Announcement.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

class AdminReviewListAPIView(APIView):
    """Admin API for managing reviews (list, approve, delete)."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        reviews = Review.objects.all().select_related("user", "product").order_by("-created_at")
        serializer = ReviewSerializer(reviews, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        review_id = request.data.get("review_id")
        action = request.data.get("action")
        try:
            review = Review.objects.get(id=review_id)
        except Review.DoesNotExist:
            return Response({"error": "Review not found"}, status=status.HTTP_404_NOT_FOUND)

        if action == "approve":
            review.is_approved = True
            review.save(update_fields=["is_approved"])
            return Response({"message": "Review approved"})
        elif action == "reject":
            review.is_approved = False
            review.save(update_fields=["is_approved"])
            return Response({"message": "Review rejected"})
        elif action == "delete":
            review.delete()
            return Response({"message": "Review deleted"})

        return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


class AdminContactMessageListAPIView(APIView):

    permission_classes = [IsAdminUser]

    def get(self, request):
        messages = ContactMessage.objects.all().order_by("-created_at")
        serializer = ContactMessageSerializer(messages, many=True)
        return Response(serializer.data)


class AdminContactMessageReplyAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            msg = ContactMessage.objects.get(id=pk)
        except ContactMessage.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        reply = request.data.get("reply", "")
        if reply:
            msg.reply = reply
            msg.status = "replied"
            msg.save(update_fields=["reply", "status"])
        return Response({"message": "Reply sent"})

    def delete(self, request, pk):
        try:
            msg = ContactMessage.objects.get(id=pk)
        except ContactMessage.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        msg.delete()
        return Response({"message": "Message deleted"}, status=status.HTTP_200_OK)


class AdminSettingsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .utils import settings_dict

        return Response(settings_dict())

    def post(self, request):
        from .utils import save_upload

        # Handle file uploads first
        for key in request.FILES:
            filename = save_upload(request.FILES[key])
            Setting.objects.update_or_create(key=key, defaults={"value": filename})

        # Handle text fields
        for key, value in request.data.items():
            if key.startswith("_") or not value:
                continue
            if key in request.FILES:
                continue  # already handled above
            Setting.objects.update_or_create(key=key, defaults={"value": str(value)})

        # --- Sync legacy key aliases so both old and new keys exist in DB ---
        # Mapping of (new_key, old_key) pairs to keep in sync
        KEY_ALIASES = [
            ("contact_phone", "phone"),
            ("contact_email", "email"),
            ("facebook_url", "facebook"),
            ("instagram_url", "instagram"),
            ("twitter_url", "twitter"),
            ("linkedin_url", "linkedin"),
            ("youtube_url", "youtube"),
        ]
        for new_key, old_key in KEY_ALIASES:
            new_setting = Setting.objects.filter(key=new_key).first()
            old_setting = Setting.objects.filter(key=old_key).first()
            if new_setting and old_setting:
                # Both exist — sync old value to new if user saved via old form
                pass
            elif new_setting and not old_setting:
                # New key exists but old doesn't — create old key with same value
                Setting.objects.update_or_create(key=old_key, defaults={"value": new_setting.value})
            elif old_setting and not new_setting:
                # Old key exists but new doesn't — create new key with same value
                Setting.objects.update_or_create(key=new_key, defaults={"value": old_setting.value})

        return Response({"message": "Settings saved"})


class AdminSEOAPIView(APIView):
    permission_classes = [IsAdminUser]

    SEO_KEYS = [
        "site_title",
        "meta_description",
        "meta_keywords",
        "og_image",
        "og_title",
        "og_description",
        "canonical_url",
        "google_analytics_id",
    ]

    def get(self, request):
        from .utils import settings_dict

        all_settings = settings_dict()
        seo_data = {k: all_settings.get(k, "") for k in self.SEO_KEYS}
        return Response(seo_data)

    def post(self, request):
        from .models import Setting

        for key in self.SEO_KEYS:
            if key in request.data:
                Setting.objects.update_or_create(key=key, defaults={"value": str(request.data[key])})
        return Response({"message": "SEO settings saved"})


class AdminReportsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .utils import decimal_value

        orders = Order.objects.all()
        total_revenue = orders.aggregate(s=Sum("paid_amount"))["s"] or 0
        total_discounts = orders.aggregate(s=Sum("discount_amount"))["s"] or 0
        total_orders_count = orders.count()
        avg_order_value = float(total_revenue / total_orders_count) if total_orders_count > 0 else 0

        # Sales by payment method
        payment_methods = orders.values("payment_method").annotate(total=Sum("paid_amount"), count=Count("id"))

        # Monthly sales
        monthly_sales = (
            orders.filter(payment_status="Paid")
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Sum("paid_amount"), count=Count("id"))
            .order_by("month")
        )

        return Response({
            "total_revenue": float(total_revenue),
            "total_discounts": float(total_discounts),
            "total_orders": total_orders_count,
            "avg_order_value": avg_order_value,
            "payment_methods": [
                {"method": pm["payment_method"], "total": float(pm["total"] or 0), "count": pm["count"]}
                for pm in payment_methods
            ],
            "monthly_sales": [
                {"month": ms["month"].strftime("%Y-%m") if ms["month"] else "", "total": float(ms["total"] or 0), "count": ms["count"]}
                for ms in monthly_sales
            ],
        })


class AdminAnalyticsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Top products
        top_products = (
            OrderItem.objects.values("product__name", "product__id")
            .annotate(total_qty=Sum("quantity"), total_revenue=Sum(models.F("quantity") * models.F("price")))
            .order_by("-total_qty")[:10]
        )

        # Category sales
        category_sales = (
            OrderItem.objects.values("product__category__name")
            .annotate(total=Sum(models.F("quantity") * models.F("price")))
            .order_by("-total")
        )

        # User signups per month
        users_per_month = (
            User.objects.annotate(month=TruncMonth("date_joined"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Orders per month
        orders_per_month = (
            Order.objects.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        return Response({
            "top_products": [
                {
                    "name": tp["product__name"],
                    "id": tp["product__id"],
                    "total_qty": tp["total_qty"],
                    "total_revenue": float(tp["total_revenue"] or 0),
                }
                for tp in top_products
            ],
            "category_sales": [
                {"category": cs["product__category__name"] or "Uncategorized", "total": float(cs["total"] or 0)}
                for cs in category_sales
            ],
            "users_per_month": [
                {"month": upm["month"].strftime("%Y-%m") if upm["month"] else "", "count": upm["count"]}
                for upm in users_per_month
            ],
            "orders_per_month": [
                {"month": opm["month"].strftime("%Y-%m") if opm["month"] else "", "count": opm["count"]}
                for opm in orders_per_month
            ],
        })


# ─── ViewSets (original DRF router views) ─────────────────────


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for products. Public read-only access."""
    queryset = Product.active.all()
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "is_featured", "status", "category__name"]
    search_fields = ["name", "description", "tags"]
    ordering_fields = ["price", "created_at", "name", "stock"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    @action(detail=False, methods=["get"])
    def featured(self, request):
        products = self.get_queryset().filter(is_featured=True)[:8]
        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def new_arrivals(self, request):
        products = self.get_queryset().order_by("-created_at")[:8]
        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def on_sale(self, request):
        products = self.get_queryset().filter(compare_price__isnull=False, compare_price__gt=models.F("price"))[:8]
        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def reviews(self, request, slug=None):
        """Get or create reviews for a product by slug."""
        try:
            product = self.get_object()
        except Product.DoesNotExist:
            return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "GET":
            reviews = Review.objects.filter(product=product).select_related("user")
            serializer = ReviewSerializer(reviews, many=True, context={"request": request})
            return Response(serializer.data)

        # POST — submit a review (uses update_or_create like AddReviewView in views.py)
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        rating = request.data.get("rating")
        comment = request.data.get("comment", "")
        title = request.data.get("title", "")

        if not rating:
            return Response({"error": "Rating is required"}, status=status.HTTP_400_BAD_REQUEST)

        review, created = Review.objects.update_or_create(
            product=product,
            user=request.user,
            defaults={
                "rating": int(rating),
                "comment": comment,
                "title": title,
                "is_approved": True,
            }
        )
        serializer = ReviewSerializer(review, context={"request": request})
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for categories."""
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


class OrderViewSet(viewsets.ModelViewSet):
    """API endpoint for orders. Users see their own orders."""
    serializer_class = OrderSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["payment_status", "order_status", "payment_method"]
    ordering_fields = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all().prefetch_related("items__product")
        return Order.objects.filter(user=user).prefetch_related("items__product")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def upload_proof(self, request, pk=None):
        """Upload payment proof screenshot — appends to comma-separated list."""
        try:
            order = self.get_object()
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        # Ensure the order belongs to the authenticated user
        if order.user != request.user and not request.user.is_staff:
            return Response({"error": "Not authorized"}, status=status.HTTP_403_FORBIDDEN)

        proof_file = request.FILES.get("payment_proof")
        if not proof_file:
            return Response({"error": "No payment proof file provided"}, status=status.HTTP_400_BAD_REQUEST)

        if proof_file.size > 5 * 1024 * 1024:
            return Response({"error": "File size must be less than 5MB"}, status=status.HTTP_400_BAD_REQUEST)

        # Append to comma-separated list instead of overwriting
        new_proof = save_upload(proof_file)
        existing_proofs = [p.strip() for p in order.payment_proof.split(",") if p.strip()] if order.payment_proof else []
        existing_proofs.append(new_proof)
        order.payment_proof = ",".join(existing_proofs)

        # If order was previously Partial/Rejected, reset to Pending + Verification
        order.payment_status = "Pending"
        order.order_status = "Payment Verification"
        order.save(update_fields=["payment_proof", "payment_status", "order_status"])

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReviewViewSet(viewsets.ModelViewSet):
    """API endpoint for reviews."""
    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["product", "rating", "is_approved"]
    ordering_fields = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Review.objects.all().select_related("user", "product")
        return Review.objects.filter(Q(user=user) | Q(is_approved=True)).select_related("user", "product")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class WishlistViewSet(viewsets.ModelViewSet):
    """API endpoint for wishlist."""
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).select_related("product")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class BannerViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for active banners."""
    queryset = Banner.objects.filter(active=True)
    serializer_class = BannerSerializer


class CouponViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for coupon validation."""
    serializer_class = CouponSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["code"]

    def get_queryset(self):
        return Coupon.objects.filter(is_active=True)

    @action(detail=False, methods=["post"])
    def validate(self, request):
        code = request.data.get("code", "")
        total = Decimal(str(request.data.get("total", 0)))
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True)
            if not coupon.is_valid:
                return Response({"valid": False, "message": "Coupon expired or invalid"}, status=status.HTTP_400_BAD_REQUEST)
            if total < coupon.min_order_amount:
                return Response({"valid": False, "message": f"Minimum order: RS {coupon.min_order_amount:,.0f}"}, status=status.HTTP_400_BAD_REQUEST)
            discount = coupon.calculate_discount(total)
            return Response({
                "valid": True,
                "code": coupon.code,
                "discount": float(discount),
                "discount_type": coupon.discount_type,
                "discount_value": float(coupon.discount_value),
            })
        except Coupon.DoesNotExist:
            return Response({"valid": False, "message": "Invalid coupon code"}, status=status.HTTP_400_BAD_REQUEST)