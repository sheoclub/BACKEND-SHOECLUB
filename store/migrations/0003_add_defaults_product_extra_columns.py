# Generated manually - adds DEFAULT values to extra columns in store_product
# that exist in the database but are NOT in the Django model.
# These columns have NOT NULL constraints but no defaults, so Django INSERT
# statements fail with NotNullViolation.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0002_fix_category_and_announcement"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "hidden_tags" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "hidden_tags" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "meta_title" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "meta_title" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "canonical_url" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "canonical_url" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql="ALTER TABLE \"store_product\" ALTER COLUMN \"faq_content\" SET DEFAULT '{}';",
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "faq_content" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "focus_keyword" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "focus_keyword" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql="ALTER TABLE \"store_product\" ALTER COLUMN \"is_indexable\" SET DEFAULT true;",
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "is_indexable" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "og_description" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "og_description" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "og_title" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "og_title" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "seo_content" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "seo_content" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "seo_keywords" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "seo_keywords" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "seo_title" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "seo_title" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "twitter_description" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "twitter_description" DROP DEFAULT;',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE "store_product" ALTER COLUMN "twitter_title" SET DEFAULT \'\';',
            reverse_sql='ALTER TABLE "store_product" ALTER COLUMN "twitter_title" DROP DEFAULT;',
        ),
    ]