from django.db import migrations, models


def mark_existing_customers_verified(apps, schema_editor):
    Customer = apps.get_model("main", "Customer")
    Customer.objects.all().update(
        is_verified=True,
        otp_code="",
        otp_expiry=None,
        otp_attempts=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0012_expense_returnentry"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="is_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="customer",
            name="otp_code",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="customer",
            name="otp_expiry",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="otp_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(mark_existing_customers_verified, migrations.RunPython.noop),
    ]
