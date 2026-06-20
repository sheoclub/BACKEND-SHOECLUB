from decimal import Decimal

from django.core.management.base import BaseCommand

from store.models import Category, DeliveryCharge, Product, Setting, User


class Command(BaseCommand):
    help = "Seed initial Shoe Club data."

    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            email="admin@shooclub.com",
            defaults={"username": "admin@shooclub.com", "first_name": "Admin", "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password("Admin123!")
            admin.save()

        categories = [
            ("Heels", "Elegant heel shoes"),
            ("Flats", "Comfortable flats"),
            ("Sneakers", "Trendy sneakers"),
            ("Boots", "Stylish boots"),
        ]
        category_objects = {}
        for name, description in categories:
            category_objects[name], _ = Category.objects.get_or_create(name=name, defaults={"description": description})

        if not Product.objects.exists():
            Product.objects.bulk_create(
                [
                    Product(name="Rose Gold Stiletto", slug="rose-gold-stiletto", description="High-class stiletto with silk satin.", price="129.99", stock=12, category=category_objects["Heels"], image="https://images.unsplash.com/photo-1515548214581-7ecd27b77338?auto=format&fit=crop&w=800&q=80"),
                    Product(name="Powder Pink Flats", slug="powder-pink-flats", description="Soft leather ballet flats.", price="69.90", stock=24, category=category_objects["Flats"], image="https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?auto=format&fit=crop&w=800&q=80"),
                    Product(name="Ivory Sneakers", slug="ivory-sneakers", description="Luxury knit sneakers.", price="89.50", stock=15, category=category_objects["Sneakers"], image="https://images.unsplash.com/photo-1528701800489-20c6508a3d96?auto=format&fit=crop&w=800&q=80"),
                    Product(name="Suede Ankle Boots", slug="suede-ankle-boots", description="Chic ankle boots.", price="149.00", stock=8, category=category_objects["Boots"], image="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=80"),
                ]
            )

        defaults = {
            "site_name": "Ladies Shoe Club",
            "top_banner_text": "Flash Sale: Up to 50% off on select styles! New Arrivals Just In!",
            "bank_name": "Femme Bank",
            "account_name": "Ladies Shoe Club",
            "account_number": "1234567890",
            "pkr_rate": "280",
            "email": "contact@ladiesshoeclub.com",
            "phone": "+92 300 123 4567",
        }
        for key, value in defaults.items():
            Setting.objects.get_or_create(key=key, defaults={"value": value})

        # Seed delivery charges for common cities
        delivery_charges = [
            ("Karachi", Decimal("149.00"), Decimal("2000.00")),
            ("Lahore", Decimal("149.00"), Decimal("2000.00")),
            ("Islamabad", Decimal("199.00"), Decimal("2500.00")),
            ("Rawalpindi", Decimal("199.00"), Decimal("2500.00")),
            ("Faisalabad", Decimal("249.00"), Decimal("3000.00")),
            ("Multan", Decimal("299.00"), Decimal("3000.00")),
            ("Peshawar", Decimal("349.00"), Decimal("3500.00")),
            ("Quetta", Decimal("399.00"), Decimal("3500.00")),
            ("Gujranwala", Decimal("249.00"), Decimal("3000.00")),
            ("Sialkot", Decimal("249.00"), Decimal("3000.00")),
            ("Hyderabad", Decimal("299.00"), Decimal("3000.00")),
            ("Other", Decimal("399.00"), Decimal("4000.00")),
        ]
        if not DeliveryCharge.objects.exists():
            for city, charge, min_order in delivery_charges:
                DeliveryCharge.objects.create(city=city, charge=charge, min_order_for_free=min_order, is_active=True)
            self.stdout.write(self.style.SUCCESS(f"Seeded {len(delivery_charges)} delivery charge cities."))
        else:
            self.stdout.write(self.style.WARNING("Delivery charges already exist, skipping."))

        self.stdout.write(self.style.SUCCESS("Seed data ready. Admin: admin@shooclub.com / Admin123!"))
