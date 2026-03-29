from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0005_sales_buyer_name"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="commodity",
            constraint=models.CheckConstraint(
                condition=models.Q(number_of_commodity__gte=0),
                name="commodity_quantity_gte_0",
            ),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(
                condition=models.Q(number_of_commodity__gte=0),
                name="stock_quantity_gte_0",
            ),
        ),
    ]
