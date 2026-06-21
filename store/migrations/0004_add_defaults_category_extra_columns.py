# NO-OP: These columns were manually added to the old production database
# and are NOT part of the Django model, so they don't exist on a fresh database.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0003_add_defaults_product_extra_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]