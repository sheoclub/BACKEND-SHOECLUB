from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, TemplateView, View
from django.views.generic.edit import CreateView, DeleteView, FormMixin, UpdateView

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
    ProductVariant,
    Review,
    Setting,
    User,
    Wishlist,
)
from .utils import allowed_file, decimal_value, get_setting, image_url, save_upload, settings_dict, to_pkr


# ─── Mixins ───────────────────────────────────────────────────────

class CartMixin:
    """Mixin providing cart helper methods."""

    def get_cart_items(self):
        cart = self.request.session.get("cart", {})
        items = []
        total = Decimal("0.00")
        product_ids = [int(pid) for pid in cart.keys() if str(pid).isdigit()]
        products = Product.objects.filter(id__in=product_ids)
        product_map = {str(p.id): p for p in products}
        for pid, qty in cart.items():
            product = product_map.get(str(pid))
            if not product:
                continue
            quantity = int(qty)
            line = product.price * quantity
            items.append({"product": product, "qty": quantity, "line": line})
            total += line
        return items, total

    def get_cart_count(self):
        return sum(int(qty) for qty in self.request.session.get("cart", {}).values())


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to restrict access to admin users."""

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, "Access denied. Admin privileges required.")
        return redirect("login")


class TitleMixin:
    """Mixin to set page title."""
    page_title = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = self.page_title
        return context


# ─── Auth Views ───────────────────────────────────────────────────

class LoginView(TemplateView):
    template_name = "login.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("user_dashboard")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user and not user.is_suspended:
            auth_login(request, user)
            next_url = request.GET.get("next")
            return redirect(next_url if next_url and next_url.startswith("/") else "user_dashboard")
        messages.error(request, "Invalid login or suspended account")
        return self.get(request, *args, **kwargs)


class SignupView(TemplateView):
    template_name = "signup.html"

    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        if User.objects.filter(email=email).exists():
            messages.warning(request, "Email already registered")
            return redirect("signup")
        try:
            validate_password(password)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("signup")
        name = request.POST.get("name", "").strip()
        first_name, _, last_name = name.partition(" ")
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=request.POST.get("phone", ""),
            address=request.POST.get("address", ""),
            city=request.POST.get("city", ""),
            state=request.POST.get("state", ""),
            postal_code=request.POST.get("postal_code", ""),
            country=request.POST.get("country", ""),
        )
        auth_login(request, user)
        messages.success(request, "Account created successfully!")
        return redirect("user_dashboard")


class LogoutView(View):
    def get(self, request, *args, **kwargs):
        auth_logout(request)
        return redirect("home")


# ─── Public Views ─────────────────────────────────────────────────

class HomeView(TemplateView, CartMixin):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["banners"] = Banner.objects.filter(active=True)
        context["announcements"] = Announcement.objects.filter(active=True)
        context["products"] = Product.active.all()[:8]
        context["featured_products"] = Product.active.filter(is_featured=True)[:4]
        context["categories"] = Category.objects.filter(is_active=True)
        context["cart_count"] = self.get_cart_count()
        context["new_arrivals"] = Product.active.all().order_by("-created_at")[:4]
        return context


class ShopView(ListView, CartMixin):
    template_name = "shop.html"
    model = Product
    paginate_by = 12

    def get_queryset(self):
        qs = Product.active.all()
        query = self.request.GET.get("q", "").strip()
        category = self.request.GET.get("category")
        sort = self.request.GET.get("sort", "")
        min_price = self.request.GET.get("min_price")
        max_price = self.request.GET.get("max_price")

        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(tags__icontains=query))
        if category:
            qs = qs.filter(category_id=category)
        if min_price:
            qs = qs.filter(price__gte=decimal_value(min_price))
        if max_price:
            qs = qs.filter(price__lte=decimal_value(max_price))

        if sort == "price_asc":
            qs = qs.order_by("price")
        elif sort == "price_desc":
            qs = qs.order_by("-price")
        elif sort == "newest":
            qs = qs.order_by("-created_at")
        elif sort == "name":
            qs = qs.order_by("name")
        elif sort == "popular":
            qs = qs.annotate(order_count=Count("orderitem")).order_by("-order_count")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(is_active=True)
        context["query"] = self.request.GET.get("q", "")
        context["selected_category"] = self.request.GET.get("category")
        context["selected_sort"] = self.request.GET.get("sort", "")
        context["min_price"] = self.request.GET.get("min_price", "")
        context["max_price"] = self.request.GET.get("max_price", "")
        context["cart_count"] = self.get_cart_count()
        context["price_range"] = Product.active.aggregate(min=Min("price"), max=Max("price"))
        return context


class ProductDetailView(DetailView, CartMixin):
    model = Product
    template_name = "product.html"
    context_object_name = "product"
    pk_url_kwarg = "product_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context["cart_count"] = self.get_cart_count()
        context["related_products"] = Product.active.filter(category=product.category).exclude(id=product.id)[:4]
        context["variants"] = product.variants.filter(is_active=True)
        context["reviews"] = product.reviews.filter(is_approved=True).select_related("user")
        context["user_review"] = product.reviews.filter(user=self.request.user).first() if self.request.user.is_authenticated else None
        context["in_wishlist"] = (
            Wishlist.objects.filter(user=self.request.user, product=product).exists()
            if self.request.user.is_authenticated
            else False
        )
        context["average_rating"] = product.average_rating
        context["review_count"] = product.review_count
        context["gallery"] = product.gallery_images.all()
        return context


# ─── Cart Views ───────────────────────────────────────────────────

class CartView(TemplateView, CartMixin):
    template_name = "cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items, total = self.get_cart_items()
        context["items"] = items
        context["total"] = total
        context["pkr_total"] = to_pkr(total)
        context["cart_count"] = self.get_cart_count()
        return context


class AddToCartView(View):
    def post(self, request, product_id):
        quantity = max(int(request.POST.get("quantity", 1) or 1), 1)
        cart = request.session.get("cart", {})
        key = str(product_id)
        cart[key] = int(cart.get(key, 0)) + quantity
        request.session["cart"] = cart
        messages.success(request, "Added to cart!")
        return redirect(request.META.get("HTTP_REFERER") or reverse("shop"))


class UpdateCartView(View):
    def post(self, request):
        cart = request.session.get("cart", {})
        for pid, qty in request.POST.items():
            if not pid.isdigit() or not str(qty).isdigit():
                continue
            if int(qty) <= 0:
                cart.pop(pid, None)
            else:
                cart[pid] = int(qty)
        request.session["cart"] = cart
        messages.success(request, "Cart updated")
        return redirect("cart_page")


class RemoveFromCartView(View):
    def post(self, request, product_id):
        cart = request.session.get("cart", {})
        cart.pop(str(product_id), None)
        request.session["cart"] = cart
        messages.success(request, "Item removed from cart")
        return redirect("cart_page")


# ─── AJAX Cart ────────────────────────────────────────────────────

class AJAXAddToCartView(View):
    def post(self, request, product_id):
        quantity = max(int(request.POST.get("quantity", 1) or 1), 1)
        cart = request.session.get("cart", {})
        key = str(product_id)
        cart[key] = int(cart.get(key, 0)) + quantity
        request.session["cart"] = cart
        cart_count = sum(int(qty) for qty in cart.values())
        return JsonResponse({"success": True, "cart_count": cart_count, "message": "Added to cart!"})


class AJAXUpdateCartView(View):
    def post(self, request):
        cart = request.session.get("cart", {})
        pid = request.POST.get("product_id", "")
        qty = request.POST.get("quantity", "0")
        if pid.isdigit() and qty.isdigit():
            if int(qty) <= 0:
                cart.pop(pid, None)
            else:
                cart[pid] = int(qty)
        request.session["cart"] = cart
        cart_count = sum(int(qty) for qty in cart.values())
        return JsonResponse({"success": True, "cart_count": cart_count})


class AJAXCartDetailView(View):
    def get(self, request):
        cart = request.session.get("cart", {})
        items = []
        total = Decimal("0.00")
        product_ids = [int(pid) for pid in cart.keys() if str(pid).isdigit()]
        products = Product.objects.filter(id__in=product_ids)
        product_map = {str(p.id): p for p in products}
        for pid, qty in cart.items():
            product = product_map.get(str(pid))
            if not product:
                continue
            quantity = int(qty)
            line = float(product.price * quantity)
            items.append({
                "id": product.id,
                "name": product.name,
                "price": float(product.price),
                "quantity": quantity,
                "line_total": line,
                "image": image_url(product.image),
            })
            total += product.price * quantity
        return JsonResponse({
            "success": True,
            "items": items,
            "total": float(total),
            "cart_count": sum(int(qty) for qty in cart.values()),
        })


# ─── Checkout / Order Views ───────────────────────────────────────

class CheckoutView(LoginRequiredMixin, TemplateView, CartMixin):
    template_name = "checkout.html"
    login_url = "login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items, total = self.get_cart_items()
        context["items"] = items
        context["total"] = total
        context["pkr_total"] = to_pkr(total)
        context["user"] = self.request.user
        context["cart_count"] = self.get_cart_count()
        context["settings"] = settings_dict()
        context["delivery_charges"] = DeliveryCharge.objects.filter(is_active=True)
        return context

    def post(self, request, *args, **kwargs):
        items, total = self.get_cart_items()
        if not items:
            messages.warning(request, "Cart is empty")
            return redirect("shop")

        address = request.POST.get("address", "")
        city = request.POST.get("city", "")
        phone = request.POST.get("phone", "")
        coupon_code = request.POST.get("coupon_code", "").strip()
        delivery_charge_id = request.POST.get("delivery_charge_id", "")

        # Apply coupon
        discount = Decimal("0.00")
        coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code__iexact=coupon_code)
                if not coupon.is_valid:
                    messages.error(request, "Coupon is expired or invalid")
                    coupon = None
                elif total < coupon.min_order_amount:
                    messages.error(request, f"Minimum order amount for this coupon is RS {coupon.min_order_amount:,.0f}")
                    coupon = None
                else:
                    discount = coupon.calculate_discount(total)
                    messages.success(request, f"Coupon applied! You saved RS {discount:,.0f}")
            except Coupon.DoesNotExist:
                messages.error(request, "Invalid coupon code")

        if request.POST.get("flow") == "online":
            request.session["payment_shipping"] = {
                "address": address, "city": city, "phone": phone,
                "coupon_code": coupon_code,
                "delivery_charge_id": delivery_charge_id,
            }
            return redirect("online_payment")

        order = self._create_order(
            request.user, items, total, discount, coupon,
            address, city, phone, "Cash on Delivery",
            "Unpaid", "Processing",
            delivery_charge_id=delivery_charge_id,
        )
        if coupon:
            coupon.used_count += 1
            coupon.save(update_fields=["used_count"])
        request.session["cart"] = {}
        messages.success(request, "Order placed successfully (COD)!")
        return redirect("order_detail", order_id=order.id)

    def _create_order(self, user, items, total, discount, coupon, address, city, phone, payment_method, payment_status, order_status, proof="", delivery_charge_id=None):
        discounted_total = max(total - discount, Decimal("0.00"))

        # Calculate delivery charge:
        # 1. Free if ALL products have free_delivery=True
        # 2. Per-product if any product has min_quantity/delivery_charge set
        # 3. Fallback to city-based tier system
        shipping_cost = Decimal("0.00")
        all_free_delivery = all(item["product"].free_delivery for item in items)
        if all_free_delivery:
            shipping_cost = Decimal("0.00")
        else:
            # Check if any product has per-product delivery charge configured
            per_product_charges = []
            for item in items:
                product = item["product"]
                qty = item["qty"]
                if product.min_quantity > 1 and product.delivery_charge > 0:
                    # Calculate blocks: ceil(qty / min_quantity) * delivery_charge
                    blocks = (qty + product.min_quantity - 1) // product.min_quantity
                    per_product_charges.append(blocks * product.delivery_charge)

            if per_product_charges:
                # Use per-product delivery charges (sum all)
                shipping_cost = sum(per_product_charges, Decimal("0.00"))
            elif delivery_charge_id:
                try:
                    dc = DeliveryCharge.objects.get(id=int(delivery_charge_id), is_active=True)
                    total_qty = sum(item["qty"] for item in items)
                    shipping_cost = dc.get_charge_for_quantity(total_qty)
                except (DeliveryCharge.DoesNotExist, ValueError, TypeError):
                    pass

        grand_total = discounted_total + shipping_cost

        order = Order.objects.create(
            user=user,
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
            payment_proof=proof,
        )
        for item in items:
            product = item["product"]
            OrderItem.objects.create(order=order, product=product, quantity=item["qty"], price=product.price)
            Product.objects.filter(id=product.id).update(stock=max(product.stock - item["qty"], 0))
        return order


class OnlinePaymentView(LoginRequiredMixin, TemplateView, CartMixin):
    template_name = "payment.html"
    login_url = "login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items, total = self.get_cart_items()
        shipping = self.request.session.get("payment_shipping") or {"address": "", "city": "", "phone": ""}
        context["items"] = items
        context["total"] = total
        context["shipping"] = shipping
        context["settings"] = settings_dict()
        context["cart_count"] = self.get_cart_count()
        context["delivery_charges"] = DeliveryCharge.objects.filter(is_active=True)
        return context

    def post(self, request, *args, **kwargs):
        items, total = self.get_cart_items()
        if not items:
            messages.warning(request, "Cart is empty")
            return redirect("shop")

        upload = request.FILES.get("payment_proof")
        if not allowed_file(upload):
            messages.error(request, "Upload a valid payment screenshot for online payment")
            return redirect("online_payment")

        proof = save_upload(upload)
        shipping = request.session.get("payment_shipping") or {}
        coupon_code = shipping.get("coupon_code", "")
        delivery_charge_id = shipping.get("delivery_charge_id", "")
        discount = Decimal("0.00")
        coupon = None

        if coupon_code:
            try:
                coupon = Coupon.objects.get(code__iexact=coupon_code)
                if coupon.is_valid and total >= coupon.min_order_amount:
                    discount = coupon.calculate_discount(total)
            except Coupon.DoesNotExist:
                pass

        discounted_total = max(total - discount, Decimal("0.00"))

        # Calculate delivery charge:
        # 1. Free if ALL products have free_delivery=True
        # 2. Per-product if any product has min_quantity/delivery_charge set
        # 3. Fallback to city-based tier system
        shipping_cost = Decimal("0.00")
        all_free_delivery = all(item["product"].free_delivery for item in items)
        if all_free_delivery:
            shipping_cost = Decimal("0.00")
        else:
            # Check if any product has per-product delivery charge configured
            per_product_charges = []
            for item in items:
                product = item["product"]
                qty = item["qty"]
                if product.min_quantity > 1 and product.delivery_charge > 0:
                    blocks = (qty + product.min_quantity - 1) // product.min_quantity
                    per_product_charges.append(blocks * product.delivery_charge)

            if per_product_charges:
                shipping_cost = sum(per_product_charges, Decimal("0.00"))
            elif delivery_charge_id:
                try:
                    dc = DeliveryCharge.objects.get(id=int(delivery_charge_id), is_active=True)
                    total_qty = sum(item["qty"] for item in items)
                    shipping_cost = dc.get_charge_for_quantity(total_qty)
                except (DeliveryCharge.DoesNotExist, ValueError, TypeError):
                    pass

        grand_total = discounted_total + shipping_cost

        order = Order.objects.create(
            user=request.user,
            shipping_address=request.POST.get("address") or shipping.get("address", ""),
            city=request.POST.get("city") or shipping.get("city", ""),
            phone=request.POST.get("phone") or shipping.get("phone", ""),
            total=grand_total,
            subtotal=total,
            discount_amount=discount,
            shipping_cost=shipping_cost,
            coupon=coupon,
            paid_amount=Decimal("0.00"),
            due_amount=grand_total,
            payment_method="Online Payment",
            payment_status="Unpaid",
            order_status="Payment Verification",
            payment_proof=proof,
        )
        for item in items:
            product = item["product"]
            OrderItem.objects.create(order=order, product=product, quantity=item["qty"], price=product.price)
            Product.objects.filter(id=product.id).update(stock=max(product.stock - item["qty"], 0))

        if coupon:
            coupon.used_count += 1
            coupon.save(update_fields=["used_count"])

        self.request.session.pop("payment_shipping", None)
        self.request.session["cart"] = {}
        messages.success(request, "Online payment request submitted. Await admin verification.")
        return redirect("order_detail", order_id=order.id)


class OrderDetailView(LoginRequiredMixin, DetailView, CartMixin):
    model = Order
    template_name = "order.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.get_object().items.select_related("product")
        context["cart_count"] = self.get_cart_count()
        return context


class InvoiceView(LoginRequiredMixin, DetailView, CartMixin):
    model = Order
    template_name = "invoice.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_object()
        context["items"] = order.items.select_related("product")
        context["pkr_rate"] = float(get_setting("pkr_rate", "280"))
        context["pkr_total"] = to_pkr(order.total)
        context["pkr_subtotal"] = to_pkr(order.subtotal)
        context["pkr_discount"] = to_pkr(order.discount_amount) if order.discount_amount > 0 else None
        context["pkr_shipping"] = to_pkr(order.shipping_cost)
        context["pkr_paid"] = to_pkr(order.paid_amount)
        context["pkr_due"] = to_pkr(order.due_amount)
        return context


# ─── User Dashboard ───────────────────────────────────────────────

class UserDashboardView(LoginRequiredMixin, TemplateView, CartMixin):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        context["orders"] = self.request.user.orders.all()[:10]
        context["cart_count"] = self.get_cart_count()
        context["wishlist"] = Wishlist.objects.filter(user=self.request.user).select_related("product")[:10]
        context["recent_reviews"] = Review.objects.filter(user=self.request.user).select_related("product")[:5]
        return context


class UpdateProfileView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        user = request.user
        name = request.POST.get("name", "").strip()
        user.first_name, _, user.last_name = name.partition(" ")
        for field in ("address", "city", "state", "postal_code", "country", "phone"):
            setattr(user, field, request.POST.get(field, ""))
        user.save()
        messages.success(request, "Profile updated successfully!")
        return redirect("user_dashboard")


class ChangePasswordView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.check_password(request.POST.get("old_password", "")):
            messages.error(request, "Current password is incorrect")
            return redirect("user_dashboard")
        request.user.set_password(request.POST.get("new_password", ""))
        request.user.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Password changed successfully!")
        return redirect("user_dashboard")


# ─── Wishlist ─────────────────────────────────────────────────────

class WishlistToggleView(LoginRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        wishlist_item = Wishlist.objects.filter(user=request.user, product=product)
        if wishlist_item.exists():
            wishlist_item.delete()
            return JsonResponse({"success": True, "in_wishlist": False, "message": "Removed from wishlist"})
        else:
            Wishlist.objects.create(user=request.user, product=product)
            return JsonResponse({"success": True, "in_wishlist": True, "message": "Added to wishlist!"})


class WishlistView(LoginRequiredMixin, ListView, CartMixin):
    template_name = "wishlist.html"
    context_object_name = "wishlist_items"
    paginate_by = 20

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).select_related("product").order_by("-added_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart_count"] = self.get_cart_count()
        return context


class WishlistRemoveView(LoginRequiredMixin, View):
    def post(self, request, product_id):
        Wishlist.objects.filter(user=request.user, product_id=product_id).delete()
        messages.success(request, "Removed from wishlist")
        return redirect("wishlist")


# ─── Reviews ──────────────────────────────────────────────────────

class AddReviewView(LoginRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        if Review.objects.filter(product=product, user=request.user).exists():
            messages.warning(request, "You have already reviewed this product")
            return redirect("product_detail", product_id=product.id)

        rating = int(request.POST.get("rating", 5))
        if rating < 1 or rating > 5:
            rating = 5
        Review.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            title=request.POST.get("title", ""),
            comment=request.POST.get("comment", ""),
        )
        messages.success(request, "Review submitted! It will be visible after approval.")
        return redirect("product_detail", product_id=product.id)


# ─── Static Pages ─────────────────────────────────────────────────

class AboutView(TemplateView, CartMixin):
    template_name = "about.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart_count"] = self.get_cart_count()
        return context


class ShippingInfoView(TemplateView, CartMixin):
    template_name = "shipping_info.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart_count"] = self.get_cart_count()
        return context


class ReturnPolicyView(TemplateView, CartMixin):
    template_name = "return_policy.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart_count"] = self.get_cart_count()
        return context


class ContactView(TemplateView, CartMixin):
    template_name = "contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart_count"] = self.get_cart_count()
        context["user_messages"] = ContactMessage.objects.filter(user=self.request.user) if self.request.user.is_authenticated else []
        return context

    def post(self, request, *args, **kwargs):
        ContactMessage.objects.create(
            user=request.user if request.user.is_authenticated else None,
            name=request.POST.get("name", ""),
            email=request.POST.get("email", ""),
            subject=request.POST.get("subject", ""),
            message=request.POST.get("message", ""),
        )
        messages.success(request, "Message sent successfully! We'll get back to you soon.")
        return redirect("contact")


# ─── Admin Views ──────────────────────────────────────────────────

class AdminDashboardView(AdminRequiredMixin, TemplateView, CartMixin):
    template_name = "admin/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        generate_analytics_chart()
        orders = Order.objects.all()
        today = timezone.localdate()
        today_orders = orders.filter(created_at__date=today)
        total_revenue = orders.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        today_sales = today_orders.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
        context["total_orders"] = orders.count()
        context["total_revenue"] = total_revenue
        context["total_profit"] = total_revenue
        context["today_sales"] = today_sales
        context["today_profit"] = today_sales
        context["pending_orders"] = orders.exclude(order_status__in=["Delivered", "Completed", "Cancelled"]).count()
        context["pending_verifications"] = orders.filter(order_status="Payment Verification").count()
        context["completed_orders"] = orders.filter(order_status__in=["Delivered", "Completed"]).count()
        context["dues_remaining"] = orders.aggregate(total=Sum("due_amount"))["total"] or Decimal("0.00")
        context["total_users"] = User.objects.count()
        context["total_products"] = Product.objects.count()
        context["recent_orders"] = orders.select_related("user")[:5]
        context["low_stock"] = Product.objects.filter(stock__lte=5, status=True)
        context["title"] = "Dashboard"
        context["cart_count"] = self.get_cart_count()

        # Charts
        context["chart_monthly_sales"] = "/static/analytics/monthly_sales.png"
        context["chart_orders_per_month"] = "/static/analytics/orders_per_month.png"
        context["chart_top_products"] = "/static/analytics/top_products.png"
        context["chart_category_sales"] = "/static/analytics/category_sales.png"
        context["chart_users_per_month"] = "/static/analytics/users_per_month.png"
        return context


class AdminProductListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/products.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = Product.objects.select_related("category").all()
        context["categories"] = Category.objects.all()
        context["title"] = "Products"
        return context


class AdminProductCreateView(AdminRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("image_file")
        image = request.POST.get("image_url", "")
        if allowed_file(upload):
            image = image_url(save_upload(upload))
        Product.objects.create(
            name=request.POST.get("name", ""),
            description=request.POST.get("description", ""),
            price=decimal_value(request.POST.get("price")),
            stock=int(request.POST.get("stock", 0) or 0),
            category_id=request.POST.get("category") or None,
            image=image,
            is_featured=request.POST.get("is_featured", "0") == "1",
            has_variants=request.POST.get("has_variants", "0") == "1",
            free_delivery=request.POST.get("free_delivery", "0") == "1",
            min_quantity=int(request.POST.get("min_quantity", 1) or 1),
            delivery_charge=decimal_value(request.POST.get("delivery_charge")),
            status=request.POST.get("status", "1") == "1",
        )
        messages.success(request, "Product added successfully!")
        return redirect("admin_products")


class AdminProductUpdateView(AdminRequiredMixin, View):
    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id)
        product.name = request.POST.get("name", product.name)
        product.description = request.POST.get("description", product.description)
        product.price = decimal_value(request.POST.get("price"), product.price)
        product.stock = int(request.POST.get("stock", product.stock) or 0)
        product.category_id = request.POST.get("category") or None
        product.is_featured = request.POST.get("is_featured", "0") == "1"
        product.has_variants = request.POST.get("has_variants", "0") == "1"
        product.free_delivery = request.POST.get("free_delivery", "0") == "1"
        product.min_quantity = int(request.POST.get("min_quantity", product.min_quantity) or 1)
        product.delivery_charge = decimal_value(request.POST.get("delivery_charge"), product.delivery_charge)
        product.status = request.POST.get("status", "1") == "1"
        if request.POST.get("image_url"):
            product.image = request.POST.get("image_url")
        upload = request.FILES.get("image_file")
        if allowed_file(upload):
            product.image = image_url(save_upload(upload))
        product.save()
        messages.success(request, "Product updated successfully!")
        return redirect("admin_products")


class AdminProductDeleteView(AdminRequiredMixin, View):
    def post(self, request, product_id):
        Product.objects.filter(id=product_id).delete()
        messages.success(request, "Product deleted")
        return redirect("admin_products")


class AdminCategoryListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/categories.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()
        context["title"] = "Categories"
        return context

    def post(self, request, *args, **kwargs):
        Category.objects.get_or_create(name=request.POST.get("name", ""), defaults={"description": request.POST.get("description", "")})
        messages.success(request, "Category saved")
        return redirect("admin_categories")


class AdminCategoryDeleteView(AdminRequiredMixin, View):
    def post(self, request, category_id):
        Category.objects.filter(id=category_id).delete()
        messages.success(request, "Category deleted")
        return redirect("admin_categories")


class AdminUserListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/users.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["users"] = User.objects.all()
        context["title"] = "Users"
        return context


class AdminUserDetailView(AdminRequiredMixin, DetailView):
    model = User
    template_name = "admin/user_detail.html"
    context_object_name = "user_obj"
    pk_url_kwarg = "user_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["orders"] = self.get_object().orders.all()
        context["title"] = f"User: {self.get_object().email}"
        return context


class AdminUserDeleteView(AdminRequiredMixin, View):
    def post(self, request, user_id):
        User.objects.filter(id=user_id).delete()
        messages.success(request, "User deleted")
        return redirect("admin_users")


class AdminUserToggleView(AdminRequiredMixin, View):
    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        user.is_suspended = not user.is_suspended
        user.save(update_fields=["is_suspended"])
        return redirect("admin_users")


class AdminOrderListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/orders.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["orders"] = Order.objects.select_related("user")
        context["title"] = "Orders"
        context["statuses"] = [s[0] for s in Order.ORDER_STATUSES]
        return context


class AdminOrderDetailView(AdminRequiredMixin, DetailView):
    model = Order
    template_name = "admin/order_detail.html"
    context_object_name = "order"
    pk_url_kwarg = "order_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items"] = self.get_object().items.select_related("product")
        context["title"] = f"Order #{self.get_object().id}"
        return context


class AdminOrderStatusUpdateView(AdminRequiredMixin, View):
    def post(self, request, order_id):
        Order.objects.filter(id=order_id).update(order_status=request.POST.get("status", ""), updated_at=timezone.now())
        messages.success(request, "Order status updated")
        return redirect("admin_orders")


class AdminPaymentVerifyView(AdminRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        order.paid_amount = order.total
        order.due_amount = Decimal("0.00")
        order.payment_status = "Paid"
        order.order_status = "Processing"
        order.save()
        messages.success(request, "Payment verified!")
        return redirect("admin_orders")


class AdminPaymentRejectView(AdminRequiredMixin, View):
    def post(self, request, order_id):
        Order.objects.filter(id=order_id).update(payment_status="Rejected", order_status="Cancelled", updated_at=timezone.now())
        messages.warning(request, "Payment rejected")
        return redirect("admin_orders")


class AdminPaymentRecordView(AdminRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, id=order_id)
        amount = decimal_value(request.POST.get("amount"))
        if amount <= 0 or amount > order.due_amount:
            messages.warning(request, "Enter a valid payment amount")
            return redirect("admin_orders")
        order.paid_amount += amount
        order.due_amount = max(order.total - order.paid_amount, Decimal("0.00"))
        order.payment_status = "Paid" if order.due_amount == 0 else "Partial"
        order.order_status = "Completed" if order.due_amount == 0 else "Processing"
        order.save()
        messages.success(request, f"Payment recorded: {amount:.2f}, remaining due: {order.due_amount:.2f}")
        return redirect("admin_orders")


class AdminPaymentListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/payments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["payments"] = Order.objects.select_related("user")
        context["orders"] = Order.objects.select_related("user")
        context["title"] = "Payments"
        return context


class AdminBannerListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/banners.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["banners"] = Banner.objects.all()
        context["title"] = "Banners"
        return context

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get("image")
        if not allowed_file(upload):
            messages.warning(request, "Valid banner image required")
            return redirect("admin_banners")
        Banner.objects.create(
            image=image_url(save_upload(upload)),
            title=request.POST.get("title", ""),
            subtitle=request.POST.get("subtitle", ""),
            sort_order=(Banner.objects.aggregate(max_order=Max("sort_order"))["max_order"] or 0) + 1,
        )
        messages.success(request, "Banner uploaded")
        return redirect("admin_banners")


class AdminBannerToggleView(AdminRequiredMixin, View):
    def post(self, request, banner_id):
        banner = get_object_or_404(Banner, id=banner_id)
        banner.active = not banner.active
        banner.save()
        return redirect("admin_banners")


class AdminBannerDeleteView(AdminRequiredMixin, View):
    def post(self, request, banner_id):
        Banner.objects.filter(id=banner_id).delete()
        messages.success(request, "Banner deleted")
        return redirect("admin_banners")


class AdminBannerReorderView(AdminRequiredMixin, View):
    def post(self, request, banner_id, direction):
        current = get_object_or_404(Banner, id=banner_id)
        if direction == "up":
            swap = Banner.objects.filter(sort_order__lt=current.sort_order).order_by("-sort_order").first()
        else:
            swap = Banner.objects.filter(sort_order__gt=current.sort_order).order_by("sort_order").first()
        if swap:
            current.sort_order, swap.sort_order = swap.sort_order, current.sort_order
            current.save()
            swap.save()
        return redirect("admin_banners")


class AdminAnnouncementListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/announcements.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["announcements"] = Announcement.objects.all()
        context["title"] = "Announcements"
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("message"):
            Announcement.objects.create(message=request.POST["message"], active=True)
            messages.success(request, "Announcement created")
        return redirect("admin_announcements")


class AdminAnnouncementToggleView(AdminRequiredMixin, View):
    def post(self, request, announcement_id):
        item = get_object_or_404(Announcement, id=announcement_id)
        item.active = not item.active
        item.save()
        return redirect("admin_announcements")


class AdminAnnouncementFlashSaleView(AdminRequiredMixin, View):
    def post(self, request):
        message = "Flash Sale: Up to 50% off on select styles! New Arrivals Just In!"
        Announcement.objects.get_or_create(message=message, defaults={"active": True})
        messages.success(request, "Flash sale announcement ready!")
        return redirect("admin_announcements")


class AdminAnnouncementDeleteView(AdminRequiredMixin, View):
    def post(self, request, announcement_id):
        Announcement.objects.filter(id=announcement_id).delete()
        messages.success(request, "Announcement deleted")
        return redirect("admin_announcements")


class AdminContactMessageListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/contact_messages.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["messages"] = ContactMessage.objects.all()
        context["title"] = "Contact Messages"
        return context


class AdminContactMessageReplyView(AdminRequiredMixin, View):
    def post(self, request, message_id):
        item = get_object_or_404(ContactMessage, id=message_id)
        item.reply = request.POST.get("reply", "")
        item.status = "responded"
        item.save()
        messages.success(request, "Reply saved and marked as responded")
        return redirect("admin_contact_messages")


class AdminDeliveryChargeListView(AdminRequiredMixin, TemplateView):
    template_name = "admin/delivery_charges.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delivery_charges"] = DeliveryCharge.objects.all()
        context["title"] = "Delivery Charges"
        return context

    def post(self, request, *args, **kwargs):
        city = request.POST.get("city", "").strip()
        charge = request.POST.get("charge", "0")
        if city and charge:
            is_active = request.POST.get("is_active") == "1"
            DeliveryCharge.objects.create(city=city, charge=charge, is_active=is_active)
            messages.success(request, f"Delivery charge for '{city}' created")
        else:
            messages.error(request, "City and charge are required")
        return redirect("admin_delivery_charges")


class AdminDeliveryChargeUpdateView(AdminRequiredMixin, View):
    def post(self, request, charge_id):
        dc = get_object_or_404(DeliveryCharge, id=charge_id)
        city = request.POST.get("city", "").strip()
        charge = request.POST.get("charge", "0")
        if city and charge:
            dc.city = city
            dc.charge = charge
            dc.is_active = request.POST.get("is_active") == "1"
            dc.save()
            messages.success(request, f"Delivery charge for '{city}' updated")
        else:
            messages.error(request, "City and charge are required")
        return redirect("admin_delivery_charges")


class AdminDeliveryChargeToggleView(AdminRequiredMixin, View):
    def post(self, request, charge_id):
        dc = get_object_or_404(DeliveryCharge, id=charge_id)
        dc.is_active = not dc.is_active
        dc.save()
        status = "enabled" if dc.is_active else "disabled"
        messages.success(request, f"Delivery charge for '{dc.city}' {status}")
        return redirect("admin_delivery_charges")


class AdminDeliveryChargeDeleteView(AdminRequiredMixin, View):
    def post(self, request, charge_id):
        dc = get_object_or_404(DeliveryCharge, id=charge_id)
        city = dc.city
        dc.delete()
        messages.success(request, f"Delivery charge for '{city}' deleted")
        return redirect("admin_delivery_charges")


# ─── Delivery Charge Tier Management (Template-based) ──────────────


class AdminDeliveryChargeTierListView(AdminRequiredMixin, TemplateView):
    """Show delivery charge detail page with its tiers."""
    template_name = "admin/delivery_charges.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        charge_id = self.kwargs.get("charge_id")
        dc = get_object_or_404(DeliveryCharge, id=charge_id)
        context["delivery_charges"] = DeliveryCharge.objects.all()
        context["title"] = f"Tiers for {dc.city}"
        context["focus_charge"] = dc
        return context


class AdminDeliveryChargeTierCreateView(AdminRequiredMixin, View):
    def post(self, request, charge_id):
        dc = get_object_or_404(DeliveryCharge, id=charge_id)
        min_qty = request.POST.get("min_quantity", "0")
        max_qty = request.POST.get("max_quantity", "")
        charge = request.POST.get("charge", "0")
        if min_qty and charge:
            DeliveryChargeTier.objects.create(
                delivery_charge=dc,
                min_quantity=int(min_qty),
                max_quantity=int(max_qty) if max_qty.strip() else None,
                charge=charge,
            )
            messages.success(request, f"Tier added for {dc.city}")
        else:
            messages.error(request, "Min quantity and charge are required")
        return redirect("admin_delivery_charges")


class AdminDeliveryChargeTierDeleteView(AdminRequiredMixin, View):
    def post(self, request, tier_id):
        tier = get_object_or_404(DeliveryChargeTier, id=tier_id)
        tier.delete()
        messages.success(request, "Tier deleted")
        return redirect("admin_delivery_charges")


class AdminSettingsView(AdminRequiredMixin, TemplateView):
    template_name = "admin/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["settings"] = settings_dict()
        context["title"] = "Settings"
        return context

    def post(self, request, *args, **kwargs):
        settings_keys = (
            "site_name", "top_banner_text", "bank_name", "account_name", "account_number",
            "pkr_rate", "instagram", "facebook", "twitter", "linkedin", "about_photo_url",
            "email", "phone", "logo_url",
        )
        for key in settings_keys:
            if key in request.POST:
                Setting.objects.update_or_create(key=key, defaults={"value": request.POST.get(key, "")})
        for field, key in (("logo_file", "logo_url"), ("about_photo_file", "about_photo_url")):
            upload = request.FILES.get(field)
            if allowed_file(upload):
                Setting.objects.update_or_create(key=key, defaults={"value": image_url(save_upload(upload))})
        messages.success(request, "Settings updated successfully!")
        return redirect("admin_settings")


class AdminReportView(AdminRequiredMixin, TemplateView):
    template_name = "admin/report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["orders"] = Order.objects.select_related("user")
        context["title"] = "Reports"
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("format", "html").lower() == "csv":
            return self._export_csv()
        return super().get(request, *args, **kwargs)

    def _export_csv(self):
        import csv
        from io import StringIO
        orders = Order.objects.select_related("user")
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Order ID", "User", "Email", "Total", "Payment", "Order Status", "Payment Status", "Date"])
        for order in orders:
            writer.writerow([order.id, order.user_name, order.user_email, order.total, order.payment_method, order.order_status, order.payment_status, order.created_at])
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="orders_report.csv"'
        return response


class AdminDueNotifyView(AdminRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order.objects.select_related("user"), id=order_id)
        if order.due_amount <= 0:
            messages.info(request, "No pending due for this order")
        else:
            messages.success(request, f"Notification simulated for {order.user.email} due {order.due_amount:.2f}")
        return redirect("admin_orders")


# ─── Analytics ────────────────────────────────────────────────────

def generate_analytics_chart():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    analytics_dir = settings.BASE_DIR / "static" / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)

    orders = Order.objects.all()

    # Monthly sales
    monthly = {}
    for order in orders:
        key = order.created_at.strftime("%Y-%m")
        monthly[key] = monthly.get(key, Decimal("0.00")) + order.total
    _save_chart(analytics_dir / "monthly_sales.png", list(monthly.keys()), [float(v) for v in monthly.values()], "Monthly Sales", "line")

    # Orders per month
    order_counts = {}
    for order in orders:
        key = order.created_at.strftime("%Y-%m")
        order_counts[key] = order_counts.get(key, 0) + 1
    _save_chart(analytics_dir / "orders_per_month.png", list(order_counts.keys()), list(order_counts.values()), "Orders Per Month", "bar")

    # Top products
    top_products = OrderItem.objects.values("product__name").annotate(sold=Sum("quantity")).order_by("-sold")[:5]
    _save_chart(analytics_dir / "top_products.png", [x["product__name"] for x in top_products], [x["sold"] for x in top_products], "Top Selling Products", "barh")

    # Category sales
    category_sales = OrderItem.objects.values("product__category__name").annotate(sold=Sum("quantity")).order_by("-sold")
    _save_chart(analytics_dir / "category_sales.png", [x["product__category__name"] or "Uncategorized" for x in category_sales], [x["sold"] for x in category_sales], "Category Sales", "barh")

    # Users per month
    user_counts = {}
    for user in User.objects.all():
        key = user.date_joined.strftime("%Y-%m")
        user_counts[key] = user_counts.get(key, 0) + 1
    _save_chart(analytics_dir / "users_per_month.png", list(user_counts.keys()), list(user_counts.values()), "New Users Per Month", "line")

    plt.close("all")


def _save_chart(path, labels, values, title, kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(7, 3.5))
    if labels and values:
        if kind == "line":
            plt.plot(labels, values, marker="o", color="#e91e63", linewidth=2)
            plt.xticks(rotation=45, ha="right")
        elif kind == "barh":
            colors = ["#e91e63", "#f06292", "#f48fb1", "#f8bbd0", "#fce4ec"]
            plt.barh(labels, values, color=colors[:len(labels)])
        else:
            plt.bar(labels, values, color="#e91e63")
            plt.xticks(rotation=45, ha="right")
        plt.title(title, fontsize=12, fontweight="bold")
        plt.tight_layout()
    else:
        plt.text(0.5, 0.5, f"No {title.lower()} data", ha="center", va="center")
        plt.axis("off")
    plt.tight_layout()
    plt.savefig(path, dpi=100, bbox_inches="tight")
    plt.clf()


# ─── Sitemap XML ──────────────────────────────────────────────────

def sitemap(request):
    """Generate sitemap.xml for search engine indexing."""
    from django.contrib.sitemaps import Sitemap
    from django.contrib.sitemaps.views import sitemap as sitemap_view
    from django.urls import reverse

    class StaticViewSitemap(Sitemap):
        priority = 0.8
        changefreq = "weekly"

        def items(self):
            return ["home", "shop", "about", "shipping_info", "return_policy", "contact"]

        def location(self, item):
            return reverse(item)

    class ProductSitemap(Sitemap):
        priority = 0.9
        changefreq = "daily"

        def items(self):
            return Product.objects.filter(status=True)

        def lastmod(self, obj):
            return obj.updated_at

        def location(self, obj):
            return reverse("product_detail", args=[obj.id])

    class CategorySitemap(Sitemap):
        priority = 0.7
        changefreq = "weekly"

        def items(self):
            return Category.objects.filter(is_active=True)

        def location(self, obj):
            return reverse("shop") + f"?category={obj.id}"

    class BrandSitemap(Sitemap):
        priority = 0.6
        changefreq = "weekly"

        def items(self):
            return Brand.objects.filter(is_active=True)

        def location(self, obj):
            return reverse("shop") + f"?brand={obj.id}"

    sitemaps = {
        "static": StaticViewSitemap,
        "products": ProductSitemap,
        "categories": CategorySitemap,
        "brands": BrandSitemap,
    }

    return sitemap_view(request, sitemaps, content_type="application/xml")
