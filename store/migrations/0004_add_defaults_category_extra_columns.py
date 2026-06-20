# Generated manually - adds DEFAULT values to extra columns in store_category
# that exist in the database but are NOT in the Django model.
# These columns have NOT NULL constraints but no defaults, so Django INSERT
# statements fail with NotNullViolation.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0003_add_defaults_product_extra_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "store_category" ALTER COLUMN "meta_description" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_category" ALTER COLUMN "meta_description" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_category" ALTER COLUMN "meta_title" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_category" ALTER COLUMN "meta_title" DROP DEFAULT;',
        ),
    ]