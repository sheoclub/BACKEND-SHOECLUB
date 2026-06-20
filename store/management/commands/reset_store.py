"""
Management command to reset the store for production deployment.

Clears all website transactional data (orders, products, announcements, etc.)
while preserving foundational data (users, categories, brands, delivery charges,
coupons, banners, and settings).

Usage:
    python manage.py reset_store          # Dry-run (shows what would be deleted)
    python manage.py reset_store --apply   # Actually delete the data
    python manage.py reset_store --apply --force   # Skip confirmation prompt
"""

from django.core.management.base import BaseCommand

from store.models import (
    Announcement,
    ContactMessage,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    UserNotification,
    Wishlist,
)


class Command(BaseCommand):
    help = "Remove all orders, products, announcements, and related transactional data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            dest="apply",
            help="Actually perform the deletion (default is dry-run).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Skip the confirmation prompt.",
        )

    def _log(self, msg, style=None):
        if style:
            self.stdout.write(style(msg))
        else:
            self.stdout.write(msg)

    def _print_counts(self, label, before, after):
        removed = before - after
        if removed > 0:
            self._log(
                "  %-40s %6d -> %-6d (removed %d)" % (label, before, after, removed),
                self.style.WARNING,
            )
        else:
            self._log(
                "  %-40s %6d -> %-6d (no change)" % (label, before, after),
            )

    def handle(self, *args, **options):
        apply = options["apply"]
        force = options["force"]

        # -- 1. Collect current counts ---------------------------------
        counts_before = {
            "OrderItem": OrderItem.objects.count(),
            "Order": Order.objects.count(),
            "Review": Review.objects.count(),
            "Wishlist": Wishlist.objects.count(),
            "ProductImage": ProductImage.objects.count(),
            "ProductVariant": ProductVariant.objects.count(),
            "Product": Product.objects.count(),
            "Announcement": Announcement.objects.count(),
            "ContactMessage": ContactMessage.objects.count(),
            "UserNotification": UserNotification.objects.count(),
        }

        total_to_remove = sum(counts_before.values())

        self._log("=" * 70)
        self._log("STORE RESET --- Dry-run" if not apply else "STORE RESET --- Applying", self.style.WARNING)
        self._log("=" * 70)

        self._log("\nCurrent row counts that would be affected:")
        for model_name, count in counts_before.items():
            if count > 0:
                self._log("  %-40s %d" % (model_name, count), self.style.WARNING)
        self._log("\n  %-40s %d" % ("TOTAL", total_to_remove), self.style.WARNING)

        if total_to_remove == 0:
            self._log("\nOK - No data to remove. The store is already clean.", self.style.SUCCESS)
            return

        if not apply:
            self._log(
                "\n[i] This was a dry-run. Pass --apply to actually perform the deletion.\n"
                "   Example: python manage.py reset_store --apply",
                self.style.NOTICE,
            )
            return

        # -- 2. Confirm ------------------------------------------------
        if not force:
            answer = input(
                "\n[WARNING] This will permanently delete %d records from the database.\n"
                "   Type 'yes' to continue: " % total_to_remove
            )
            if answer.lower() not in ("yes", "y"):
                self._log("Aborted.", self.style.ERROR)
                return

        # -- 3. Delete in dependency order -----------------------------
        self._log("\nDeleting data...", self.style.WARNING)

        delete_order = [
            ("OrderItem", OrderItem),
            ("Order", Order),
            ("Review", Review),
            ("Wishlist", Wishlist),
            ("ProductImage", ProductImage),
            ("ProductVariant", ProductVariant),
            ("Product", Product),
            ("Announcement", Announcement),
            ("ContactMessage", ContactMessage),
            ("UserNotification", UserNotification),
        ]

        results = {}
        for label, model_class in delete_order:
            before = model_class.objects.count()
            model_class.objects.all().delete()
            after = model_class.objects.count()
            results[label] = (before, after)
            self._print_counts(label, before, after)

        # -- 4. Summary ------------------------------------------------
        total_before = sum(v[0] for v in results.values())
        total_after = sum(v[1] for v in results.values())
        total_removed = total_before - total_after

        self._log("=" * 70, self.style.SUCCESS)
        self._log(
            "  %-40s %6d -> %-6d (removed %d)" % ("TOTAL", total_before, total_after, total_removed),
            self.style.SUCCESS,
        )
        self._log("=" * 70, self.style.SUCCESS)

        if total_removed > 0:
            self._log("\nOK - Store has been reset successfully. Ready for clean deployment!", self.style.SUCCESS)
        else:
            self._log("\nOK - No data was removed. The store is already clean.", self.style.SUCCESS)

        self._log("\nPreserved data (not touched):", self.style.NOTICE)
        self._log("  * Users (admin accounts, customers)")
        self._log("  * Categories")
        self._log("  * Brands")
        self._log("  * Banners")
        self._log("  * Coupons")
        self._log("  * Delivery charges & tiers")
        self._log("  * Settings")