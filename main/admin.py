from django.contrib import admin

from .models import (
    Commodity,
    Customer,
    Debtor,
    DebtorLedger,
    Debtors,
    Expense,
    Payment,
    ReturnEntry,
    Sales,
    Stock,
)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "business_name",
        "email",
        "phone_number",
        "is_verified",
        "otp_expiry",
        "timestamp",
    )


@admin.register(Debtor)
class DebtorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "current_balance",
        "credit_limit",
        "timestamp",
    )
    list_select_related = ("customer",)


@admin.register(Commodity)
class CommodityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_grouped",
        "name",
        "number_of_commodity",
        "buying_price",
        "selling_price",
        "amount",
        "total_amount",
        "expected_sales",
        "expected_total",
        "timestamp",
    )
    list_select_related = ("customer",)
    ordering = ("customer", "timestamp", "id")

    @admin.display(description="Customer", ordering="customer")
    def customer_grouped(self, obj):
        if getattr(self, "_last_customer_id", None) != obj.customer_id:
            self._last_customer_id = obj.customer_id
            return obj.customer
        return ""

    def changelist_view(self, request, extra_context=None):
        self._last_customer_id = None
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Sales)
class SalesAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "commodity",
        "buyer_name",
        "payment_type",
        "name",
        "number_of_commodity",
        "buying_price",
        "selling_price",
        "amount",
        "total_amount",
        "timestamp",
    )
    list_select_related = ("commodity",)


@admin.register(Debtors)
class DebtorsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "customer_name",
        "commodity_name",
        "number_of_commodity",
        "amount",
        "total_amount",
        "due_date",
        "is_cleared",
        "last_updated",
        "timestamp",
    )
    list_select_related = ("sale",)


@admin.register(DebtorLedger)
class DebtorLedgerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "debtor",
        "date",
        "description",
        "debit",
        "credit",
        "balance",
    )
    list_select_related = ("debtor",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "debtor",
        "amount_paid",
        "date",
        "method",
        "reference",
    )
    list_select_related = ("debtor",)


@admin.register(ReturnEntry)
class ReturnEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "return_type",
        "amount",
        "note",
        "timestamp",
    )
    list_select_related = ("customer",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "description",
        "amount",
        "timestamp",
    )
    list_select_related = ("customer",)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_grouped",
        "name_commodity",
        "number_of_commodity",
        "buying_price",
        "cost_amount",
        "total_amount",
        "expected_selling_price",
        "expected_sales",
        "expected_total",
        "timestamp",
    )
    list_select_related = ("customer", "commodity")
    ordering = ("customer", "timestamp", "id")

    @admin.display(description="Cost Amount")
    def cost_amount(self, obj):
        return obj.amount

    @admin.display(description="Customer", ordering="customer")
    def customer_grouped(self, obj):
        if getattr(self, "_last_customer_id", None) != obj.customer_id:
            self._last_customer_id = obj.customer_id
            return obj.customer
        return ""

    def changelist_view(self, request, extra_context=None):
        # Reset per-request grouping state so only the first row of each
        # customer group shows the customer value.
        self._last_customer_id = None
        return super().changelist_view(request, extra_context=extra_context)
