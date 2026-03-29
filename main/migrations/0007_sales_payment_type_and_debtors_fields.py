from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0006_inventory_sync_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="sales",
            name="payment_type",
            field=models.CharField(
                choices=[("Cash", "Cash"), ("Credit", "Credit")],
                default="Cash",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="debtors",
            name="commodity_name",
            field=models.CharField(default="", max_length=200),
        ),
        migrations.AddField(
            model_name="debtors",
            name="customer_name",
            field=models.CharField(default="", max_length=200),
        ),
    ]
