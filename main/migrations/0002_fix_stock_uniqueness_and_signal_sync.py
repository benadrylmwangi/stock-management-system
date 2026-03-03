from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stock",
            name="name_commodity",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterUniqueTogether(
            name="stock",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.UniqueConstraint(
                fields=("customer", "commodity"),
                name="unique_stock_per_customer_commodity",
            ),
        ),
    ]
