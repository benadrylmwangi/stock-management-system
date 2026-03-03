from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Customer, Commodity, Stock


@receiver(post_save, sender=Commodity)
def sync_stock_with_commodity(sender, instance, created, **kwargs):
    """Keep Stock rows in sync with the Commodity that backs them."""

    if created:
        for customer in Customer.objects.all():
            Stock.objects.update_or_create(
                customer=customer,
                commodity=instance,
                defaults={
                    "name_commodity": instance.name,
                    "number_of_commodity": instance.number_of_commodity,
                    "buying_price": instance.buying_price,
                    "amount": instance.amount,
                    "total_amount": instance.total_amount,
                },
            )
        return

    Stock.objects.filter(commodity=instance).update(
        name_commodity=instance.name,
        number_of_commodity=instance.number_of_commodity,
        buying_price=instance.buying_price,
        amount=instance.amount,
        total_amount=instance.total_amount,
    )
