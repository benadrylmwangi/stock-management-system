from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils import timezone

# Create your models here.
class Customer(models.Model):
    business_name=models.CharField(max_length=200,unique=True, null=False)
    email=models.EmailField(max_length=200,unique=True,null=False)
    phone_number=models.CharField(max_length=10,unique=True,null=False,default='0700000000')
    password=models.CharField(max_length=200,null=False)
    confirm_password=models.CharField(max_length=200,null=False,default='password')
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=200, blank=True, default="")
    otp_expiry = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    timestamp=models.DateTimeField(auto_now_add=True)

    def __str__(self):        
        return f"{self.business_name} - {self.timestamp}"


class Debtor(models.Model):
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="debtor",
    )
    current_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.business_name} - {self.current_balance}"
    
class Commodity(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="commodities",
        null=True,
        blank=True,
    )
    name=models.CharField(max_length=200)
    buying_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_sales=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_total=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp=models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "name"],
                name="unique_commodity_per_customer_name",
            ),
            models.CheckConstraint(
                condition=models.Q(number_of_commodity__gte=0),
                name="commodity_quantity_gte_0",
            ),
        ]

    @classmethod
    def add_stock(
        cls,
        *,
        customer,
        name,
        quantity,
        buying_price=0,
        selling_price=0,
        amount=0,
        expected_sales=0,
        expected_total=None,
        total_amount=None,
    ):
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        buying_price = Decimal(buying_price or 0)
        selling_price = Decimal(selling_price or 0)
        amount = Decimal(amount or 0)
        expected_sales = Decimal(expected_sales or 0)
        expected_total = Decimal(expected_total or 0) if expected_total is not None else None
        total_amount = Decimal(total_amount) if total_amount is not None else None

        with transaction.atomic():
            commodity = (
                cls.objects.select_for_update()
                .filter(customer=customer, name=name)
                .first()
            )
            if commodity:
                commodity.number_of_commodity += quantity
                commodity.buying_price = buying_price
                commodity.selling_price = selling_price
                commodity.amount = buying_price * Decimal(commodity.number_of_commodity)
                commodity.expected_sales = selling_price * Decimal(commodity.number_of_commodity)
                if expected_total is None:
                    commodity.expected_total = (commodity.expected_total or 0) + (
                        selling_price * Decimal(quantity)
                    )
                else:
                    commodity.expected_total = expected_total
                commodity.total_amount = (
                    total_amount
                    if total_amount is not None
                    else buying_price * Decimal(commodity.number_of_commodity)
                )
                commodity.save()
            else:
                commodity = cls.objects.create(
                    customer=customer,
                    name=name,
                    buying_price=buying_price,
                    selling_price=selling_price,
                    number_of_commodity=quantity,
                    amount=buying_price * Decimal(quantity),
                    expected_sales=selling_price * Decimal(quantity),
                    expected_total=expected_sales if expected_total is None else expected_total,
                    total_amount=(
                        total_amount
                        if total_amount is not None
                        else buying_price * Decimal(quantity)
                    ),
                )

            stock, _ = Stock.objects.select_for_update().get_or_create(
                customer=customer,
                commodity=commodity,
                defaults={
                    "name_commodity": commodity.name,
                    "number_of_commodity": 0,
                    "buying_price": commodity.buying_price,
                    "amount": commodity.amount,
                    "total_amount": commodity.total_amount,
                },
            )
            stock.number_of_commodity = commodity.number_of_commodity
            stock.buying_price = commodity.buying_price
            stock.amount = commodity.amount
            stock.total_amount = commodity.total_amount
            stock.expected_selling_price = commodity.selling_price
            stock.expected_sales = commodity.expected_sales
            stock.expected_total = commodity.expected_total
            stock.name_commodity = commodity.name
            stock.save(skip_sync=True)

            Stock.recalculate_totals_for_customer(customer.id)

        return commodity


    def __str__(self):        
        return f"{self.name} - {self.timestamp} - {self.number_of_commodity} - {self.buying_price} - {self.selling_price} - {self.amount} - {self.total_amount}"
class Stock(models.Model):
    # each stock row is tied to both a customer and a commodity
    # when the commodity is deleted we cascade; if the customer is removed
    # all their stock goes with them.
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="stocks")
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="stocks")

    # most of the data is redundant with the commodity but stored here
    # so that the customer can have a per‑commodity copy (price, amount etc.)
    name_commodity = models.CharField(max_length=200)
    number_of_commodity = models.IntegerField(default=0)
    buying_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_selling_price= models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expected_sales= models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "commodity"],
                name="unique_stock_per_customer_commodity",
            ),
            models.CheckConstraint(
                condition=models.Q(number_of_commodity__gte=0),
                name="stock_quantity_gte_0",
            ),
        ]

    def save(self, *args, skip_sync=False, **kwargs):
        # whenever a stock row is saved, copy the current commodity values
        if self.commodity:
            self.name_commodity = self.commodity.name
            self.buying_price = self.commodity.buying_price
            self.expected_selling_price = self.commodity.selling_price
            # keep amount + expected sales in sync with the current quantity
            self.amount = (self.buying_price or 0) * Decimal(self.number_of_commodity or 0)
            selling_price = self.expected_selling_price or Decimal("0")
            self.expected_sales = selling_price * Decimal(self.number_of_commodity or 0)
            # number_of_commodity left to be managed by whatever view/form creates stocks
        if skip_sync:
            super().save(*args, **kwargs)
            return

        if self.number_of_commodity < 0:
            raise ValidationError("Stock quantity cannot be negative.")

        with transaction.atomic():
            commodity = Commodity.objects.select_for_update().get(pk=self.commodity_id)
            previous_quantity = 0
            if self.pk:
                previous_quantity = (
                    Stock.objects.select_for_update()
                    .get(pk=self.pk)
                    .number_of_commodity
                )

            quantity_delta = self.number_of_commodity - previous_quantity
            updated_commodity_quantity = commodity.number_of_commodity + quantity_delta
            if updated_commodity_quantity < 0:
                raise ValidationError("Commodity quantity cannot be negative.")

            super().save(*args, **kwargs)

            if quantity_delta:
                commodity.number_of_commodity = updated_commodity_quantity
                commodity.total_amount = commodity.amount
                commodity.expected_sales = commodity.selling_price * Decimal(commodity.number_of_commodity or 0)
                commodity.save(update_fields=["number_of_commodity", "total_amount"])

        if self.customer_id:
            Stock.recalculate_totals_for_customer(self.customer_id)

    def reduce_quantity(self, quantity):
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        with transaction.atomic():
            self.number_of_commodity -= quantity
            self.save(update_fields=["number_of_commodity", "expected_sales"])

        if self.customer_id:
            Stock.recalculate_totals_for_customer(self.customer_id)

    @classmethod
    def recalculate_totals_for_customer(cls, customer_id):
        rows = list(
            cls.objects.filter(customer_id=customer_id)
            .select_related("commodity")
            .order_by("timestamp", "id")
        )

        running_expected = Decimal("0")
        running_total_amount = Decimal("0")
        for row in rows:
            buying_price = row.commodity.buying_price if row.commodity else Decimal("0")
            selling_price = row.commodity.selling_price if row.commodity else Decimal("0")
            row.buying_price = buying_price
            row.expected_selling_price = selling_price
            row.amount = buying_price * Decimal(row.number_of_commodity or 0)
            row.expected_sales = selling_price * Decimal(row.number_of_commodity or 0)
            running_expected += row.expected_sales
            row.expected_total = running_expected
            running_total_amount += row.amount
            row.total_amount = running_total_amount

        if rows:
            cls.objects.bulk_update(
                rows,
                [
                    "buying_price",
                    "expected_selling_price",
                    "amount",
                    "expected_sales",
                    "expected_total",
                    "total_amount",
                ],
            )

    def __str__(self):        
        return f"{self.name_commodity} - {self.customer.business_name} - {self.timestamp}- {self.number_of_commodity} - {self.buying_price} - {self.amount} - {self.total_amount}"
    
class Sales(models.Model):
    class PaymentType(models.TextChoices):
        CASH = "Cash", "Cash"
        CREDIT = "Credit", "Credit"

    commodity = models.ForeignKey(Commodity,on_delete=models.CASCADE,related_name="sales")
    buyer_name= models.CharField(max_length=200,default="Unknown Buyer")
    payment_type = models.CharField(
        max_length=10,
        choices=PaymentType.choices,
        default=PaymentType.CASH,
    )
    name=models.CharField(max_length=200)
    buying_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp=models.DateTimeField(auto_now_add=True)


    def __str__(self):        
        return f"{self.name} - {self.timestamp} - {self.number_of_commodity} - {self.buying_price} - {self.selling_price} - {self.amount} - {self.total_amount}"
class Debtors(models.Model):
    name=models.CharField(max_length=200)
    sale = models.OneToOneField(Sales,on_delete=models.CASCADE,related_name="debt")
    customer_name = models.CharField(max_length=200, default="")
    commodity_name = models.CharField(max_length=200, default="")
    number_of_commodity=models.IntegerField(default=0)
    amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    is_cleared = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    timestamp=models.DateTimeField(auto_now_add=True)

    @property
    def total_credit(self):
        return self.total_amount or Decimal("0")

    @total_credit.setter
    def total_credit(self, value):
        self.total_amount = value

    @property
    def is_overdue(self):
        if not self.due_date:
            return False
        return self.due_date < timezone.localdate() and (self.total_amount or 0) > 0


    def __str__(self):        
        return f"{self.customer_name or self.name} - {self.commodity_name} - {self.timestamp}"


class DebtorLedger(models.Model):
    debtor = models.ForeignKey(
        Debtors,
        on_delete=models.CASCADE,
        related_name="ledger_entries",
    )
    date = models.DateTimeField(default=timezone.now, db_index=True)
    description = models.CharField(max_length=255)
    debit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["date", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0),
                name="debtor_ledger_debit_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(credit__gte=0),
                name="debtor_ledger_credit_gte_0",
            ),
        ]

    def __str__(self):
        return f"{self.debtor.customer_name or self.debtor.name} - {self.description} - {self.balance}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"

    debtor = models.ForeignKey(
        Debtors,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date = models.DateTimeField(default=timezone.now, db_index=True)
    method = models.CharField(
        max_length=10,
        choices=Method.choices,
        default=Method.CASH,
    )
    reference = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paid__gt=0),
                name="payment_amount_gt_0",
            ),
        ]

    def __str__(self):
        return f"{self.debtor.customer_name or self.debtor.name} - {self.amount_paid} - {self.method}"


class ReturnEntry(models.Model):
    class ReturnType(models.TextChoices):
        RETURN_IN = "IN", "Return In"
        RETURN_OUT = "OUT", "Return Out"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="returns",
    )
    return_type = models.CharField(
        max_length=3,
        choices=ReturnType.choices,
        default=ReturnType.RETURN_IN,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.CharField(max_length=200, blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.business_name} - {self.return_type} - {self.amount} - {self.timestamp}"


class Expense(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.business_name} - {self.description} - {self.amount} - {self.timestamp}"
