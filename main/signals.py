from allauth.account.signals import user_signed_up
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .customer_sync import ensure_customer_for_user, sync_customer_session
from .models import Commodity, Customer, Debtor, Stock


@receiver(post_save, sender=Customer)
def bootstrap_customer_dependencies(sender, instance, created, **kwargs):
    """
    Ensure every customer has required related records.
    Runs only on first create.
    """
    if not created:
        return

    def _create_related_rows():
        Debtor.objects.get_or_create(customer=instance)
        default_commodity, _ = Commodity.objects.get_or_create(
            customer=instance,
            name="Default Commodity",
            defaults={
                "buying_price": 0,
                "selling_price": 0,
                "number_of_commodity": 0,
                "amount": 0,
                "total_amount": 0,
            },
        )
        if not Stock.objects.filter(customer=instance, commodity=default_commodity).exists():
            Stock(
                customer=instance,
                commodity=default_commodity,
                name_commodity=default_commodity.name,
                number_of_commodity=default_commodity.number_of_commodity,
                buying_price=default_commodity.buying_price,
                amount=default_commodity.amount,
                total_amount=default_commodity.total_amount,
            ).save(skip_sync=True)

    transaction.on_commit(_create_related_rows)


@receiver(post_save, sender=Commodity)
def sync_stock_with_commodity(sender, instance, created, **kwargs):
    """
    Keep one Stock row in sync with each customer-owned Commodity.
    Quantity is managed from stock mutations to avoid circular updates.
    """
    if not instance.customer_id:
        return

    defaults = {
        "name_commodity": instance.name,
        "buying_price": instance.buying_price,
        "amount": instance.amount,
        "total_amount": instance.total_amount,
    }
    if created:
        if not Stock.objects.filter(customer=instance.customer, commodity=instance).exists():
            Stock(
                customer=instance.customer,
                commodity=instance,
                name_commodity=instance.name,
                number_of_commodity=instance.number_of_commodity,
                buying_price=instance.buying_price,
                amount=instance.amount,
                total_amount=instance.total_amount,
            ).save(skip_sync=True)
        return

    Stock.objects.filter(customer=instance.customer, commodity=instance).update(**defaults)


@receiver(user_signed_up)
def sync_customer_on_allauth_signup(request, user, **kwargs):
    customer = ensure_customer_for_user(user)
    sync_customer_session(request, customer)


@receiver(user_logged_in)
def sync_customer_on_login(sender, request, user, **kwargs):
    customer = ensure_customer_for_user(user)
    sync_customer_session(request, customer)
