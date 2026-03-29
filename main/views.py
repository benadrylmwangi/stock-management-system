import json
from functools import wraps
import secrets
from calendar import month_abbr
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from .forms import (
    CreditPaymentForm,
    ExpenseForm,
    LoginForm,
    RegisterForm,
    ReturnForm,
    SaleForm,
    VerifyOTPForm,
)
from django.db import transaction
from .customer_sync import (
    ensure_auth_user_for_customer,
    sync_customer_from_request,
)
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
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 5


# Create your views here.
def customer_logged_in(request):
    if request.session.get("customer_id"):
        return True
    return bool(_sync_customer_from_authenticated_user(request))


def login_required_customer(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not customer_logged_in(request):
            messages.error(request, "Please login or register to continue.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return _wrapped


def get_current_customer(request):
    customer_id = request.session.get("customer_id")
    customer = Customer.objects.filter(id=customer_id).first() if customer_id else None
    if customer:
        return customer
    return _sync_customer_from_authenticated_user(request)


def _normalize_debtor_name(name):
    return (name or "").strip()


def _find_debtor_record(customer, debtor_name, *, for_update=False):
    normalized_name = _normalize_debtor_name(debtor_name)
    if not normalized_name:
        return None

    queryset = (
        Debtors.objects.filter(sale__commodity__customer=customer)
        .filter(Q(customer_name__iexact=normalized_name) | Q(name__iexact=normalized_name))
        .order_by("-timestamp", "-id")
    )
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def _ensure_opening_ledger_entry(debtor):
    if DebtorLedger.objects.filter(debtor=debtor).exists():
        return

    opening_balance = Decimal(debtor.total_amount or 0)
    if opening_balance <= 0:
        return

    DebtorLedger.objects.create(
        debtor=debtor,
        date=debtor.timestamp or timezone.now(),
        description="Opening balance",
        debit=opening_balance,
        credit=Decimal("0"),
        balance=opening_balance,
    )


def _append_ledger_entry(*, debtor, description, debit=Decimal("0"), credit=Decimal("0"), entry_date=None):
    debit_amount = Decimal(debit or 0)
    credit_amount = Decimal(credit or 0)

    _ensure_opening_ledger_entry(debtor)
    latest_entry = (
        DebtorLedger.objects.select_for_update()
        .filter(debtor=debtor)
        .order_by("-date", "-id")
        .first()
    )
    previous_balance = Decimal(latest_entry.balance or 0) if latest_entry else Decimal("0")
    running_balance = previous_balance + debit_amount - credit_amount
    if running_balance < 0:
        running_balance = Decimal("0")

    DebtorLedger.objects.create(
        debtor=debtor,
        date=entry_date or timezone.now(),
        description=description,
        debit=debit_amount,
        credit=credit_amount,
        balance=running_balance,
    )
    return running_balance


def _record_credit_sale_ledger(*, debtor, sale, credit_total):
    sale_amount = Decimal(credit_total or 0)
    if sale_amount <= 0:
        return Decimal(debtor.total_amount or 0)

    running_balance = _append_ledger_entry(
        debtor=debtor,
        description=f"Credit sale #{sale.id} - {sale.name}",
        debit=sale_amount,
        credit=Decimal("0"),
        entry_date=sale.timestamp,
    )
    debtor.total_amount = running_balance
    debtor.is_cleared = running_balance <= 0
    debtor.save(update_fields=["total_amount", "is_cleared", "last_updated"])
    return running_balance


def _apply_debt_payment(*, debtor, amount_paid, method=Payment.Method.CASH, reference=""):
    payment_amount = Decimal(amount_paid or 0)
    current_credit = Decimal(debtor.total_amount or 0)
    if payment_amount <= 0 or current_credit <= 0:
        return {
            "applied_amount": Decimal("0"),
            "remaining_credit": current_credit if current_credit > 0 else Decimal("0"),
            "cleared": current_credit <= 0,
        }

    applied_amount = payment_amount if payment_amount <= current_credit else current_credit
    payment = Payment.objects.create(
        debtor=debtor,
        amount_paid=applied_amount,
        date=timezone.now(),
        method=method,
        reference=reference,
    )
    running_balance = _append_ledger_entry(
        debtor=debtor,
        description=f"Payment received #{payment.id}",
        debit=Decimal("0"),
        credit=applied_amount,
        entry_date=payment.date,
    )

    debtor.total_amount = running_balance
    debtor.is_cleared = running_balance <= 0
    debtor.save(update_fields=["total_amount", "is_cleared", "last_updated"])

    return {
        "applied_amount": applied_amount,
        "remaining_credit": running_balance,
        "cleared": debtor.is_cleared,
    }


def _sync_customer_from_authenticated_user(request):
    return sync_customer_from_request(request)


def _generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def _set_customer_otp(customer):
    otp_code = _generate_otp()
    customer.otp_code = make_password(otp_code)
    customer.otp_expiry = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    customer.otp_attempts = 0
    customer.save(update_fields=["otp_code", "otp_expiry", "otp_attempts"])
    return otp_code


def _send_otp_email(customer, otp_code):
    subject = "LedgerPro Email Verification OTP"
    message = (
        f"Hello {customer.business_name},\n\n"
        f"Your OTP code is: {otp_code}\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
        "If you did not request this, you can ignore this email."
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [customer.email],
        fail_silently=False,
    )


def index(request):
    return redirect("home")


@ensure_csrf_cookie
def home(request):
    customer = get_current_customer(request)

    if request.method == "POST":
        if not customer:
            messages.error(request, "Please login or register to manage inventory.")
            return redirect("login")

        name = request.POST.get("name", "").strip()

        if name:
            Commodity.objects.get_or_create(
                customer=customer,
                name=name,
                defaults={
                    "buying_price": 0,
                    "selling_price": 0,
                    "number_of_commodity": 0,
                    "amount": 0,
                    "total_amount": 0,
                },
            )
        return redirect("home")

    commodities = (
        Commodity.objects.filter(customer=customer).order_by("-timestamp")
        if customer
        else Commodity.objects.none()
    )
    return render(
        request,
        "main/home.html",
        {
            "commodities": commodities,
            "is_public_visitor": customer is None,
        },
    )


@login_required_customer
def pricing(request):
    return render(request, "main/pricing.html", {})


@login_required_customer
@ensure_csrf_cookie
def sales(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    if request.method == "POST":
        form_data = request.POST.copy()
        if not form_data.get("customer_name") and form_data.get("buyer_name"):
            form_data["customer_name"] = form_data.get("buyer_name", "")
        if not form_data.get("payment_type"):
            form_data["payment_type"] = Sales.PaymentType.CASH

        form = SaleForm(form_data)
        if not form.is_valid():
            return render(request, "main/sales.html", {"form": form})

        commodity_name = form.cleaned_data["name"]
        buyer_name = form.cleaned_data["customer_name"]
        requested_quantity = form.cleaned_data["number_of_commodity"]
        unit_buying_price = form.cleaned_data.get("buying_price")
        unit_selling_price = form.cleaned_data["selling_price"]
        amount= form.cleaned_data["amount"]
        payment_type = form.cleaned_data["payment_type"]

        with transaction.atomic():
            stock_item = (
                Stock.objects.select_for_update()
                .select_related("commodity")
                .filter(customer=customer, name_commodity=commodity_name)
                .first()
            )

            if not stock_item:
                messages.error(request, "Product is currently unavailable in stock.")
                return redirect("sales")

            if stock_item.number_of_commodity < requested_quantity:
                messages.error(request, "Not enough stock available.")
                return redirect("sales")

            commodity = stock_item.commodity
            if unit_buying_price in (None, ""):
                unit_buying_price = commodity.buying_price
            current_total = Sales.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0")
            sale_amount = requested_quantity * unit_selling_price
            sale = Sales.objects.create(
                buyer_name=buyer_name or "Unknown Buyer",
                payment_type=payment_type,
                commodity=commodity,
                name=commodity.name,
                buying_price=unit_buying_price,
                selling_price=unit_selling_price,
                number_of_commodity=requested_quantity,
                amount=sale_amount,
                total_amount=current_total + sale_amount,
            )

            if payment_type == Sales.PaymentType.CREDIT:
                credit_total = requested_quantity * unit_selling_price
                debtor = _find_debtor_record(customer, buyer_name, for_update=True)
                if debtor:
                    debtor.number_of_commodity = (debtor.number_of_commodity or 0) + requested_quantity
                    debtor.commodity_name = commodity.name
                    debtor.amount = commodity.amount
                    debtor.is_cleared = False
                    debtor.save(
                        update_fields=[
                            "number_of_commodity",
                            "commodity_name",
                            "amount",
                            "is_cleared",
                            "last_updated",
                        ]
                    )
                else:
                    debtor = Debtors.objects.create(
                        name=buyer_name,
                        sale=sale,
                        customer_name=buyer_name,
                        commodity_name=commodity.name,
                        number_of_commodity=requested_quantity,
                        amount=commodity.amount,
                        total_amount=Decimal("0"),
                        is_cleared=False,
                    )

                _record_credit_sale_ledger(
                    debtor=debtor,
                    sale=sale,
                    credit_total=credit_total,
                )

            try:
                stock_item.reduce_quantity(requested_quantity)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect("sales")

        messages.success(request, "Sale completed successfully.")
        return redirect("sales")

    form = SaleForm()
    return render(request, "main/sales.html", {"form": form})


@login_required_customer
@ensure_csrf_cookie
def stock(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    if request.method == "POST":
        commodity_name = request.POST.get("commodity_name", "").strip()
        quantity = request.POST.get("quantity")
        buying_price = request.POST.get("buying_price")
        expected_selling_price = request.POST.get("expected_selling_price")
        amount = request.POST.get("amount")
        expected_sales = request.POST.get("expected_sales")

        if commodity_name:
            try:
                quantity = int(quantity or 0)
            except (TypeError, ValueError):
                messages.error(request, "Invalid quantity supplied.")
                return redirect("stock")

            try:
                Commodity.add_stock(
                    customer=customer,
                    name=commodity_name,
                    quantity=quantity,
                    buying_price=buying_price,
                    selling_price=expected_selling_price,
                    amount=amount,
                    #total_amount=Decimal(expected_sales) if expected_sales not in ("", None) else None,
                )
            except (ValidationError, InvalidOperation) as exc:
                error_message = exc.messages[0] if isinstance(exc, ValidationError) else "Invalid amount supplied."
                messages.error(request, error_message)
                return redirect("stock")

            return redirect("stock")

    stocks = Stock.objects.filter(customer=customer).select_related("commodity").order_by("-timestamp")
    return render(request, "main/stock.html", {"stocks": stocks})


def aboutus(request):
    return render(request, "main/aboutus.html", {})


@login_required_customer
def resources(request):
    return render(request, "main/resources.html", {})


def _format_decimal_for_chart(value):
    return f"{Decimal(value or 0):.2f}"


def _roll_back_month(year, month, count):
    for _ in range(count):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return year, month


@login_required_customer
def sales_analysis_data(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Session expired. Please login again."}, status=401)

    analysis_type = (request.GET.get("type") or "monthly").strip().lower()
    if analysis_type not in {"monthly", "six_months", "yearly"}:
        return JsonResponse(
            {"error": "Invalid type. Use monthly, six_months, or yearly."},
            status=400,
        )

    sales_qs = Sales.objects.filter(commodity__customer=customer)
    today = timezone.localdate()

    if analysis_type == "monthly":
        monthly_totals = (
            sales_qs.filter(timestamp__year=today.year)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        totals_by_month = {
            row["period"].month: Decimal(row["total"] or 0)
            for row in monthly_totals
        }
        labels = [month_abbr[month] for month in range(1, 13)]
        data = [
            _format_decimal_for_chart(totals_by_month.get(month, Decimal("0")))
            for month in range(1, 13)
        ]

    elif analysis_type == "six_months":
        start_year, start_month = _roll_back_month(today.year, today.month, 5)
        start_date = date(start_year, start_month, 1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1)
        else:
            end_date = date(today.year, today.month + 1, 1)

        six_month_totals = (
            sales_qs.filter(timestamp__date__gte=start_date, timestamp__date__lt=end_date)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        totals_by_month = {
            (row["period"].year, row["period"].month): Decimal(row["total"] or 0)
            for row in six_month_totals
        }

        rolling_months = []
        for offset in range(5, -1, -1):
            year, month = _roll_back_month(today.year, today.month, offset)
            rolling_months.append((year, month))

        labels = [f"{month_abbr[month]} {str(year)[-2:]}" for year, month in rolling_months]
        data = [
            _format_decimal_for_chart(totals_by_month.get((year, month), Decimal("0")))
            for year, month in rolling_months
        ]

    else:
        yearly_totals = (
            sales_qs.annotate(period=TruncYear("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        labels = [str(row["period"].year) for row in yearly_totals]
        data = [_format_decimal_for_chart(row["total"]) for row in yearly_totals]

    return JsonResponse({"labels": labels, "data": data})


@login_required_customer
def sales_expense_profit_analysis(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Session expired. Please login again."}, status=401)

    analysis_type = (request.GET.get("type") or "monthly").strip().lower()
    if analysis_type not in {"monthly", "six_months", "yearly"}:
        return JsonResponse(
            {"error": "Invalid type. Use monthly, six_months, or yearly."},
            status=400,
        )

    sales_qs = Sales.objects.filter(commodity__customer=customer)
    expenses_qs = Expense.objects.filter(customer=customer)
    today = timezone.localdate()

    if analysis_type == "monthly":
        sales_totals = (
            sales_qs.filter(timestamp__year=today.year)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )
        expense_totals = (
            expenses_qs.filter(timestamp__year=today.year)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        sales_by_month = {
            row["period"].month: Decimal(row["total"] or 0)
            for row in sales_totals
        }
        expenses_by_month = {
            row["period"].month: Decimal(row["total"] or 0)
            for row in expense_totals
        }

        labels = [month_abbr[month] for month in range(1, 13)]
        sales_data = []
        expenses_data = []
        profit_data = []
        for month in range(1, 13):
            sales_value = sales_by_month.get(month, Decimal("0"))
            expense_value = expenses_by_month.get(month, Decimal("0"))
            profit_value = sales_value - expense_value
            sales_data.append(_format_decimal_for_chart(sales_value))
            expenses_data.append(_format_decimal_for_chart(expense_value))
            profit_data.append(_format_decimal_for_chart(profit_value))

    elif analysis_type == "six_months":
        start_year, start_month = _roll_back_month(today.year, today.month, 5)
        start_date = date(start_year, start_month, 1)
        if today.month == 12:
            end_date = date(today.year + 1, 1, 1)
        else:
            end_date = date(today.year, today.month + 1, 1)

        sales_totals = (
            sales_qs.filter(timestamp__date__gte=start_date, timestamp__date__lt=end_date)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )
        expense_totals = (
            expenses_qs.filter(timestamp__date__gte=start_date, timestamp__date__lt=end_date)
            .annotate(period=TruncMonth("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        sales_by_month = {
            (row["period"].year, row["period"].month): Decimal(row["total"] or 0)
            for row in sales_totals
        }
        expenses_by_month = {
            (row["period"].year, row["period"].month): Decimal(row["total"] or 0)
            for row in expense_totals
        }

        rolling_months = []
        for offset in range(5, -1, -1):
            year, month = _roll_back_month(today.year, today.month, offset)
            rolling_months.append((year, month))

        labels = [f"{month_abbr[month]} {str(year)[-2:]}" for year, month in rolling_months]
        sales_data = []
        expenses_data = []
        profit_data = []
        for year, month in rolling_months:
            sales_value = sales_by_month.get((year, month), Decimal("0"))
            expense_value = expenses_by_month.get((year, month), Decimal("0"))
            profit_value = sales_value - expense_value
            sales_data.append(_format_decimal_for_chart(sales_value))
            expenses_data.append(_format_decimal_for_chart(expense_value))
            profit_data.append(_format_decimal_for_chart(profit_value))

    else:
        sales_totals = (
            sales_qs.annotate(period=TruncYear("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )
        expense_totals = (
            expenses_qs.annotate(period=TruncYear("timestamp"))
            .values("period")
            .annotate(total=Sum("amount"))
            .order_by("period")
        )

        sales_by_year = {
            row["period"].year: Decimal(row["total"] or 0)
            for row in sales_totals
        }
        expenses_by_year = {
            row["period"].year: Decimal(row["total"] or 0)
            for row in expense_totals
        }
        years = sorted(set(sales_by_year.keys()) | set(expenses_by_year.keys()))

        labels = [str(year) for year in years]
        sales_data = []
        expenses_data = []
        profit_data = []
        for year in years:
            sales_value = sales_by_year.get(year, Decimal("0"))
            expense_value = expenses_by_year.get(year, Decimal("0"))
            profit_value = sales_value - expense_value
            sales_data.append(_format_decimal_for_chart(sales_value))
            expenses_data.append(_format_decimal_for_chart(expense_value))
            profit_data.append(_format_decimal_for_chart(profit_value))

    return JsonResponse(
        {
            "labels": labels,
            "sales": sales_data,
            "expenses": expenses_data,
            "profit": profit_data,
        }
    )


@login_required_customer
@ensure_csrf_cookie
def features(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    stocks = (
        Stock.objects.filter(customer=customer)
        .select_related("commodity")
        .order_by("timestamp", "id")
    )
    sales = (
        Sales.objects.filter(commodity__customer=customer)
        .select_related("commodity")
        .order_by("timestamp", "id")
    )
    for sale in sales:
        sale.cost_amount = (sale.buying_price or Decimal("0")) * Decimal(sale.number_of_commodity or 0)

    returns = (
        ReturnEntry.objects.filter(customer=customer)
        .order_by("timestamp", "id")
    )
    expenses = (
        Expense.objects.filter(customer=customer)
        .order_by("timestamp", "id")
    )

    return render(
        request,
        "main/features.html",
        {
            "stocks": stocks,
            "sales": sales,
            "returns": returns,
            "expenses": expenses,
        },
    )


@login_required_customer
@ensure_csrf_cookie
def credit_payment(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "return":
            return_form = ReturnForm(request.POST)
            credit_form = CreditPaymentForm()
            expense_form = ExpenseForm()
            if not return_form.is_valid():
                return render(
                    request,
                    "main/credit_payment.html",
                    {
                        "form": credit_form,
                        "return_form": return_form,
                        "expense_form": expense_form,
                    },
                )

            amount = return_form.cleaned_data["amount"]
            if amount <= 0:
                messages.error(request, "Return amount must be greater than zero.")
                return render(
                    request,
                    "main/credit_payment.html",
                    {
                        "form": credit_form,
                        "return_form": return_form,
                        "expense_form": expense_form,
                    },
                )

            ReturnEntry.objects.create(
                customer=customer,
                return_type=return_form.cleaned_data["return_type"],
                amount=amount,
                note=return_form.cleaned_data["note"],
            )
            messages.success(request, "Return saved successfully.")
            return redirect("credit_payment")

        if form_type == "expense":
            expense_form = ExpenseForm(request.POST)
            credit_form = CreditPaymentForm()
            return_form = ReturnForm()
            if not expense_form.is_valid():
                return render(
                    request,
                    "main/credit_payment.html",
                    {
                        "form": credit_form,
                        "return_form": return_form,
                        "expense_form": expense_form,
                    },
                )

            amount = expense_form.cleaned_data["amount"]
            if amount <= 0:
                messages.error(request, "Expense amount must be greater than zero.")
                return render(
                    request,
                    "main/credit_payment.html",
                    {
                        "form": credit_form,
                        "return_form": return_form,
                        "expense_form": expense_form,
                    },
                )

            Expense.objects.create(
                customer=customer,
                description=expense_form.cleaned_data["description"],
                amount=amount,
            )
            messages.success(request, "Expense saved successfully.")
            return redirect("credit_payment")

        credit_form = CreditPaymentForm(request.POST)
        return_form = ReturnForm()
        expense_form = ExpenseForm()
        if not credit_form.is_valid():
            return render(
                request,
                "main/credit_payment.html",
                {
                    "form": credit_form,
                    "return_form": return_form,
                    "expense_form": expense_form,
                },
            )

        customer_name = credit_form.cleaned_data["customer_name"]
        payment_amount = credit_form.cleaned_data["payment_amount"]

        if payment_amount <= 0:
            messages.error(request, "Payment amount must be greater than zero.")
            return render(
                request,
                "main/credit_payment.html",
                {
                    "form": credit_form,
                    "return_form": return_form,
                    "expense_form": expense_form,
                },
            )

        with transaction.atomic():
            debtor = _find_debtor_record(customer, customer_name, for_update=True)
            if not debtor or debtor.total_amount <= 0:
                messages.error(
                    request,
                    "Customer has no debt.",
                )
                return render(
                    request,
                    "main/credit_payment.html",
                    {
                        "form": credit_form,
                        "return_form": return_form,
                        "expense_form": expense_form,
                    },
                )

            payment_result = _apply_debt_payment(
                debtor=debtor,
                amount_paid=payment_amount,
                method=Payment.Method.CASH,
                reference="Manual credit payment form",
            )

        if payment_result["cleared"]:
            messages.success(request, "Payment applied successfully. Debt cleared.")
        else:
            messages.success(request, "Payment applied successfully.")
        return redirect("credit_payment")

    credit_form = CreditPaymentForm()
    return_form = ReturnForm()
    expense_form = ExpenseForm()
    return render(
        request,
        "main/credit_payment.html",
        {
            "form": credit_form,
            "return_form": return_form,
            "expense_form": expense_form,
        },
    )


@login_required_customer
@require_GET
def debtor_credit_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"message": "Session expired. Please login again."}, status=401)

    debtor_name = (request.GET.get("name") or "").strip()
    if not debtor_name:
        return JsonResponse({"exists": False, "message": "Debtor name is required."}, status=400)

    debtor = _find_debtor_record(customer, debtor_name)
    if not debtor:
        return JsonResponse({"exists": False, "message": "Customer has no debt"})

    _ensure_opening_ledger_entry(debtor)
    credit = Decimal(debtor.total_amount or 0)
    if credit < 0:
        credit = Decimal("0")

    response = {
        "exists": True,
        "credit": float(credit),
        "due_date": debtor.due_date.isoformat() if debtor.due_date else None,
        "overdue": debtor.is_overdue,
    }
    if credit == 0:
        response["message"] = "Credit amount is 0"
    return JsonResponse(response)


@login_required_customer
@require_POST
def pay_debt_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"message": "Session expired. Please login again."}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"message": "Invalid request payload."}, status=400)

    debtor_name = str(payload.get("name", "")).strip()
    amount_raw = payload.get("amount_paid")
    method_raw = str(payload.get("method", Payment.Method.CASH)).strip().lower()
    reference = str(payload.get("reference", "")).strip()[:200]

    if not debtor_name:
        return JsonResponse({"message": "Debtor name is required."}, status=400)

    try:
        amount_paid = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"message": "Payment amount must be a valid number."}, status=400)

    if amount_paid <= 0:
        return JsonResponse({"message": "Payment amount must be greater than 0."}, status=400)

    if method_raw not in {Payment.Method.CASH, Payment.Method.BANK}:
        return JsonResponse({"message": "Payment method must be cash or bank."}, status=400)

    with transaction.atomic():
        debtor = _find_debtor_record(customer, debtor_name, for_update=True)
        if not debtor or Decimal(debtor.total_amount or 0) <= 0:
            return JsonResponse({"message": "Customer has no debt"}, status=404)

        payment_result = _apply_debt_payment(
            debtor=debtor,
            amount_paid=amount_paid,
            method=method_raw,
            reference=reference or "API debt payment",
        )

    message = "Payment successful"
    if payment_result["cleared"]:
        message = "Payment successful. Debt cleared"

    return JsonResponse(
        {
            "message": message,
            "remaining_credit": float(payment_result["remaining_credit"]),
            "applied_amount": float(payment_result["applied_amount"]),
            "cleared": payment_result["cleared"],
        }
    )


@login_required_customer
def debtor_ledger_page(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    debtor_names = list(
        Debtors.objects.filter(sale__commodity__customer=customer)
        .order_by("customer_name")
        .values_list("customer_name", flat=True)
        .distinct()
    )
    return render(
        request,
        "main/debtor_ledger.html",
        {"debtor_names": [name for name in debtor_names if name]},
    )


@login_required_customer
@require_GET
def debtor_ledger_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"message": "Session expired. Please login again."}, status=401)

    debtor_name = _normalize_debtor_name(request.GET.get("name"))
    if not debtor_name:
        return JsonResponse({"message": "Debtor name is required."}, status=400)

    debtor = _find_debtor_record(customer, debtor_name)
    if not debtor:
        return JsonResponse({"exists": False, "message": "Customer has no debt"})

    _ensure_opening_ledger_entry(debtor)
    ledger_entries = list(
        DebtorLedger.objects.filter(debtor=debtor).order_by("date", "id")
    )

    response = {
        "exists": True,
        "debtor": {
            "name": debtor.customer_name or debtor.name,
            "total_credit": float(Decimal(debtor.total_amount or 0)),
            "due_date": debtor.due_date.isoformat() if debtor.due_date else None,
            "overdue": debtor.is_overdue,
            "is_cleared": debtor.is_cleared,
        },
        "entries": [
            {
                "date": entry.date.isoformat(),
                "description": entry.description,
                "debit": float(Decimal(entry.debit or 0)),
                "credit": float(Decimal(entry.credit or 0)),
                "balance": float(Decimal(entry.balance or 0)),
            }
            for entry in ledger_entries
        ],
        "total_balance": float(
            Decimal(ledger_entries[-1].balance if ledger_entries else (debtor.total_amount or 0))
        ),
    }
    if not ledger_entries:
        response["message"] = "No transactions found"
    return JsonResponse(response)


@login_required_customer
@require_GET
def payment_history_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"message": "Session expired. Please login again."}, status=401)

    debtor_name = _normalize_debtor_name(request.GET.get("name"))
    if not debtor_name:
        return JsonResponse({"message": "Debtor name is required."}, status=400)

    debtor = _find_debtor_record(customer, debtor_name)
    if not debtor:
        return JsonResponse({"exists": False, "message": "Customer has no debt"})

    payments = list(debtor.payments.all().order_by("-date", "-id"))
    return JsonResponse(
        {
            "exists": True,
            "payments": [
                {
                    "date": payment.date.isoformat(),
                    "amount_paid": float(Decimal(payment.amount_paid or 0)),
                    "method": payment.method,
                    "reference": payment.reference,
                }
                for payment in payments
            ],
            "message": "No transactions found" if not payments else "",
        }
    )


@login_required_customer
@require_GET
def overdue_debtors_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"message": "Session expired. Please login again."}, status=401)

    today = timezone.localdate()
    overdue_rows = (
        Debtors.objects.filter(sale__commodity__customer=customer)
        .filter(due_date__lt=today, total_amount__gt=0, is_cleared=False)
        .order_by("due_date", "customer_name", "name")
    )

    return JsonResponse(
        {
            "count": overdue_rows.count(),
            "items": [
                {
                    "name": row.customer_name or row.name,
                    "total_credit": float(Decimal(row.total_amount or 0)),
                    "due_date": row.due_date.isoformat() if row.due_date else None,
                    "status": "overdue",
                }
                for row in overdue_rows
            ],
        }
    )


def _format_amount(value):
    value = Decimal(value or 0)
    if value < 0:
        return f"({abs(value):.2f})"
    return f"{value:.2f}"


def _build_trading_pdf(*, title, lines):
    # Minimal PDF generator using a single page and Helvetica font.
    def escape(text):
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = []
    for text, x, y, size in lines:
        content_lines.append(f"BT /F1 {size} Tf {x} {y} Td ({escape(text)}) Tj ET")
    content_stream = "\n".join(content_lines).encode("utf-8")

    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(
        f"<< /Length {len(content_stream)} >>\nstream\n".encode("utf-8")
        + content_stream
        + b"\nendstream"
    )

    xref_positions = []
    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    for idx, obj in enumerate(objects, start=1):
        xref_positions.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("utf-8"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    pdf.extend(b"0000000000 65535 f \n")
    for pos in xref_positions:
        pdf.extend(f"{pos:010d} 00000 n \n".encode("utf-8"))
    pdf.extend(b"trailer\n")
    pdf.extend(
        f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("utf-8")
    )
    pdf.extend(b"startxref\n")
    pdf.extend(f"{xref_start}\n".encode("utf-8"))
    pdf.extend(b"%%EOF")
    return bytes(pdf)


@login_required_customer
def trading_report(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    date_value = (request.GET.get("date") or "").strip()

    sales_qs = Sales.objects.filter(commodity__customer=customer)
    returns_qs = ReturnEntry.objects.filter(customer=customer)
    expenses_qs = Expense.objects.filter(customer=customer)

    if date_value:
        sales_qs = sales_qs.filter(timestamp__date=date_value)
        returns_qs = returns_qs.filter(timestamp__date=date_value)
        expenses_qs = expenses_qs.filter(timestamp__date=date_value)

    sales_total = sum((sale.amount or Decimal("0")) for sale in sales_qs)
    cost_total = sum(
        (sale.buying_price or Decimal("0")) * Decimal(sale.number_of_commodity or 0)
        for sale in sales_qs
    )
    return_in_total = sum(
        (row.amount or Decimal("0"))
        for row in returns_qs
        if row.return_type == ReturnEntry.ReturnType.RETURN_IN
    )
    return_out_total = sum(
        (row.amount or Decimal("0"))
        for row in returns_qs
        if row.return_type == ReturnEntry.ReturnType.RETURN_OUT
    )
    expense_total = sum((row.amount or Decimal("0")) for row in expenses_qs)

    net_sales = sales_total - return_in_total
    cost_of_sales = cost_total - return_out_total
    gross_profit = net_sales - cost_of_sales
    net_profit = gross_profit - expense_total

    title = "Trading profit and loss account"
    lines = []
    y = 760
    lines.append((title, 180, y, 14))
    y -= 30
    lines.append(("Sales", 50, y, 12))
    lines.append((_format_amount(sales_total), 450, y, 12))
    y -= 22
    lines.append(("less return in", 50, y, 12))
    lines.append((_format_amount(-return_in_total), 450, y, 12))
    y -= 22
    lines.append(("Net sales", 50, y, 12))
    lines.append((_format_amount(net_sales), 450, y, 12))
    y -= 22
    lines.append(("less cost of sale", 50, y, 12))
    lines.append((_format_amount(-cost_of_sales), 450, y, 12))
    y -= 22
    lines.append(("Gross profit / Gross loss if negative", 50, y, 12))
    lines.append((_format_amount(gross_profit), 450, y, 12))
    y -= 22
    lines.append(("less expenses", 50, y, 12))
    y -= 18

    for expense in expenses_qs:
        lines.append((expense.description, 70, y, 11))
        lines.append((_format_amount(-expense.amount), 450, y, 11))
        y -= 18

    lines.append(("Total expenses", 50, y, 12))
    lines.append((_format_amount(-expense_total), 450, y, 12))
    y -= 24
    lines.append(("Net profit", 50, y, 12))
    lines.append((_format_amount(net_profit), 450, y, 12))

    pdf_bytes = _build_trading_pdf(title=title, lines=lines)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = "trading_profit_loss.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required_customer
def income_statement_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Session expired. Please login again."}, status=401)

    start_date = (request.GET.get("start_date") or "").strip()
    end_date = (request.GET.get("end_date") or "").strip()
    if not start_date or not end_date:
        return JsonResponse({"error": "start_date and end_date are required."}, status=400)

    try:
        from datetime import date
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    sales_qs = Sales.objects.filter(
        commodity__customer=customer,
        timestamp__date__range=(start, end),
    )
    returns_qs = ReturnEntry.objects.filter(
        customer=customer,
        timestamp__date__range=(start, end),
    )
    expenses_qs = Expense.objects.filter(
        customer=customer,
        timestamp__date__range=(start, end),
    )

    sales_total = sum((row.amount or Decimal("0")) for row in sales_qs)
    sales_returns = sum(
        (row.amount or Decimal("0"))
        for row in returns_qs
        if row.return_type == ReturnEntry.ReturnType.RETURN_IN
    )
    return_inwards = sum(
        (row.amount or Decimal("0"))
        for row in returns_qs
        if row.return_type == ReturnEntry.ReturnType.RETURN_OUT
    )

    purchases = sum(
        (row.total_amount or Decimal("0"))
        for row in Stock.objects.filter(
            customer=customer,
            timestamp__date__range=(start, end),
        )
    )

    opening_inventory = sum(
        (row.amount or Decimal("0"))
        for row in Stock.objects.filter(
            customer=customer,
            timestamp__date__lt=start,
        )
    )
    closing_inventory = sum(
        (row.amount or Decimal("0"))
        for row in Stock.objects.filter(
            customer=customer,
            timestamp__date__lte=end,
        )
    )

    def normalize(text):
        return (text or "").strip().lower()

    expenses = {
        "wages": Decimal("0"),
        "lighting": Decimal("0"),
        "rent": Decimal("0"),
        "general": Decimal("0"),
        "carriage_outwards": Decimal("0"),
    }

    for expense in expenses_qs:
        desc = normalize(expense.description)
        amount = Decimal(expense.amount or 0)
        if "wage" in desc or "salary" in desc:
            expenses["wages"] += amount
        elif "light" in desc or "electric" in desc or "power" in desc:
            expenses["lighting"] += amount
        elif "rent" in desc:
            expenses["rent"] += amount
        elif "carriage" in desc or "transport" in desc or "delivery" in desc:
            expenses["carriage_outwards"] += amount
        else:
            expenses["general"] += amount

    discount_received = Decimal("0")

    return JsonResponse(
        {
            "sales": float(sales_total),
            "sales_returns": float(sales_returns),
            "opening_inventory": float(opening_inventory),
            "purchases": float(purchases),
            "return_inwards": float(return_inwards),
            "closing_inventory": float(closing_inventory),
            "discount_received": float(discount_received),
            "expenses": {
                "wages": float(expenses["wages"]),
                "lighting": float(expenses["lighting"]),
                "rent": float(expenses["rent"]),
                "general": float(expenses["general"]),
                "carriage_outwards": float(expenses["carriage_outwards"]),
            },
        }
    )


@login_required_customer
def cashbook_page(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")
    return render(request, "main/cashbook.html", {})


@login_required_customer
def cashbook_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Session expired. Please login again."}, status=401)

    start_date = (request.GET.get("start_date") or "").strip()
    end_date = (request.GET.get("end_date") or "").strip()
    if not start_date or not end_date:
        return JsonResponse({"error": "start_date and end_date are required."}, status=400)

    try:
        # datetime.date.fromisoformat raises ValueError on bad input
        from datetime import date
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status=400)

    sales_qs = (
        Sales.objects.filter(commodity__customer=customer, timestamp__date__range=(start, end))
        .order_by("timestamp", "id")
    )
    stocks_qs = (
        Stock.objects.filter(customer=customer, timestamp__date__range=(start, end))
        .select_related("commodity")
        .order_by("timestamp", "id")
    )
    expenses_qs = (
        Expense.objects.filter(customer=customer, timestamp__date__range=(start, end))
        .order_by("timestamp", "id")
    )

    receipts = []
    payments = []

    for sale in sales_qs:
        cash = Decimal("0")
        bank = Decimal("0")
        if sale.payment_type == Sales.PaymentType.CASH:
            cash = Decimal(sale.amount or 0)
        else:
            # Treat non-cash sales as bank for cashbook reporting.
            bank = Decimal(sale.amount or 0)

        receipts.append(
            {
                "date": sale.timestamp.date().isoformat(),
                "description": f"Sales - {sale.name}",
                "ref": sale.id,
                "cash": float(cash),
                "bank": float(bank),
                "discount": 0.0,
            }
        )

    for stock in stocks_qs:
        amount = Decimal(stock.amount or 0)
        payments.append(
            {
                "date": stock.timestamp.date().isoformat(),
                "description": f"Purchase - {stock.name_commodity}",
                "ref": stock.id,
                "cash": float(amount),
                "bank": 0.0,
                "discount": 0.0,
            }
        )

    for expense in expenses_qs:
        amount = Decimal(expense.amount or 0)
        payments.append(
            {
                "date": expense.timestamp.date().isoformat(),
                "description": expense.description,
                "ref": expense.id,
                "cash": float(amount),
                "bank": 0.0,
                "discount": 0.0,
            }
        )

    return JsonResponse({"receipts": receipts, "payments": payments})


@login_required_customer
def global_search(request):
    customer = get_current_customer(request)
    if not customer:
        messages.error(request, "Session expired. Please login again.")
        return redirect("login")

    query = (request.GET.get("q") or "").strip()

    commodities = []
    stocks = []
    sales = []
    debtors = []
    expenses = []
    returns = []
    pages = []

    if query:
        commodities = list(
            Commodity.objects.filter(
                customer=customer,
                name__icontains=query,
            )
            .order_by("-timestamp", "-id")[:20]
        )

        stocks = list(
            Stock.objects.filter(
                customer=customer,
                name_commodity__icontains=query,
            )
            .order_by("-timestamp", "-id")[:20]
        )

        sales = list(
            Sales.objects.filter(commodity__customer=customer)
            .filter(
                Q(name__icontains=query)
                | Q(buyer_name__icontains=query)
                | Q(payment_type__icontains=query)
            )
            .select_related("commodity")
            .order_by("-timestamp", "-id")[:20]
        )

        debtors = list(
            Debtors.objects.filter(sale__commodity__customer=customer)
            .filter(
                Q(customer_name__icontains=query)
                | Q(commodity_name__icontains=query)
                | Q(name__icontains=query)
            )
            .order_by("-timestamp", "-id")[:20]
        )

        expenses = list(
            Expense.objects.filter(
                customer=customer,
                description__icontains=query,
            )
            .order_by("-timestamp", "-id")[:20]
        )

        returns = list(
            ReturnEntry.objects.filter(customer=customer).filter(
                Q(note__icontains=query)
                | Q(return_type__icontains=query)
            )
            .order_by("-timestamp", "-id")[:20]
        )

        query_lower = query.lower()
        searchable_pages = [
            {"title": "Reports", "path": "/features/", "keywords": "report reports income statement analytics"},
            {"title": "Sales", "path": "/sales/", "keywords": "sales sale revenue"},
            {"title": "Stock", "path": "/stock/", "keywords": "stock inventory product"},
            {"title": "Credit", "path": "/credit_payment/", "keywords": "credit debtors payment"},
            {"title": "Debtor Ledger", "path": "/debtor-ledger/", "keywords": "debtors ledger overdue payment history"},
            {"title": "Cash Book", "path": "/cashbook/", "keywords": "cashbook ledger receipts payments"},
            {"title": "Resources", "path": "/resources/", "keywords": "resources guide help"},
        ]
        pages = [
            page
            for page in searchable_pages
            if query_lower in page["title"].lower() or query_lower in page["keywords"]
        ]

    total_results = (
        len(commodities)
        + len(stocks)
        + len(sales)
        + len(debtors)
        + len(expenses)
        + len(returns)
        + len(pages)
    )

    return render(
        request,
        "main/search_results.html",
        {
            "query": query,
            "total_results": total_results,
            "commodities": commodities,
            "stocks": stocks,
            "sales": sales,
            "debtors": debtors,
            "expenses": expenses,
            "returns": returns,
            "pages": pages,
        },
    )


def search_suggestions_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"suggestions": []}, status=401)

    query = (request.GET.get("q") or "").strip()
    if not query:
        return JsonResponse({"suggestions": []})

    max_results = 10
    query_lower = query.lower()
    suggestions = []
    seen = set()

    def add_suggestion(value, suggestion_type):
        value = (value or "").strip()
        if not value:
            return
        key = value.lower()
        if key in seen:
            return
        seen.add(key)
        suggestions.append(
            {
                "value": value,
                "label": value,
                "type": suggestion_type,
            }
        )

    for name in (
        Commodity.objects.filter(customer=customer, name__icontains=query)
        .order_by("name")
        .values_list("name", flat=True)[:6]
    ):
        add_suggestion(name, "Product")

    for stock_name in (
        Stock.objects.filter(customer=customer, name_commodity__icontains=query)
        .order_by("name_commodity")
        .values_list("name_commodity", flat=True)[:6]
    ):
        add_suggestion(stock_name, "Stock")

    for buyer_name in (
        Sales.objects.filter(commodity__customer=customer, buyer_name__icontains=query)
        .order_by("buyer_name")
        .values_list("buyer_name", flat=True)[:4]
    ):
        add_suggestion(buyer_name, "Customer")

    for category in ("Sales", "Stock", "Credit", "Debtor Ledger", "Cash Book", "Reports", "Resources"):
        if query_lower in category.lower():
            add_suggestion(category, "Category")

    return JsonResponse({"suggestions": suggestions[:max_results]})


@login_required_customer
def product_details_api(request):
    customer = get_current_customer(request)
    if not customer:
        return JsonResponse({"error": "Session expired. Please login again."}, status=401)

    product_name = (request.GET.get("name") or "").strip()
    if not product_name:
        return JsonResponse(
            {"product_name": None, "buying_price": None, "selling_price": None}
        )

    stock_item = (
        Stock.objects.filter(
            customer=customer,
            name_commodity__iexact=product_name,
        )
        .order_by("-timestamp", "-id")
        .first()
    )

    if not stock_item:
        return JsonResponse(
            {"product_name": None, "buying_price": None, "selling_price": None}
        )

    return JsonResponse(
        {
            "product_name": stock_item.name_commodity,
            "buying_price": float(stock_item.buying_price or 0),
            "selling_price": float(stock_item.expected_selling_price or 0),
        }
    )


@ensure_csrf_cookie
def register(request):
    if customer_logged_in(request):
        messages.error(request, "You are already logged in.")
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            customer = form.save()
            ensure_auth_user_for_customer(
                customer,
                raw_password=form.cleaned_data.get("password1"),
                is_active=customer.is_verified,
            )
            otp_code = _set_customer_otp(customer)
            try:
                _send_otp_email(customer, otp_code)
            except Exception:
                messages.error(
                    request,
                    "Account created, but OTP email could not be sent. "
                    "Please check SMTP settings and resend OTP.",
                )
            else:
                messages.success(
                    request,
                    "Registration successful. We sent an OTP to your email.",
                )

            request.session["pending_verification_email"] = customer.email
            return redirect(f"{reverse('verify_otp')}?email={customer.email}")
    else:
        form = RegisterForm()

    return render(request, "main/register.html", {"form": form})


@ensure_csrf_cookie
def verify_otp(request):
    if customer_logged_in(request):
        messages.info(request, "Your account is already active.")
        return redirect("home")

    pending_email = (
        request.GET.get("email")
        or request.POST.get("email")
        or request.session.get("pending_verification_email")
        or ""
    ).strip()

    if request.method == "POST":
        if request.POST.get("action") == "resend":
            email_value = pending_email.lower()
            customer = Customer.objects.filter(email__iexact=email_value).first()

            if not customer:
                messages.error(request, "No account found for that email.")
            elif customer.is_verified:
                messages.success(request, "This account is already verified. Please log in.")
                return redirect("login")
            else:
                otp_code = _set_customer_otp(customer)
                try:
                    _send_otp_email(customer, otp_code)
                    messages.success(request, "A new OTP has been sent to your email.")
                except Exception:
                    messages.error(request, "Unable to send OTP email right now. Try again later.")

            return render(
                request,
                "main/verify_otp.html",
                {
                    "form": VerifyOTPForm(initial={"email": pending_email}),
                    "pending_email": pending_email,
                },
            )

        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            email_value = form.cleaned_data["email"].lower()
            otp_value = form.cleaned_data["otp_code"].strip()

            customer = Customer.objects.filter(email__iexact=email_value).first()
            if not customer:
                messages.error(request, "No account found for that email.")
            elif customer.is_verified:
                messages.success(request, "Email is already verified. Please log in.")
                return redirect("login")
            elif customer.otp_attempts >= MAX_OTP_ATTEMPTS:
                messages.error(
                    request,
                    "Too many failed OTP attempts. Please resend a new OTP.",
                )
            elif not customer.otp_code or not customer.otp_expiry:
                messages.error(request, "No active OTP found. Please resend OTP.")
            elif timezone.now() > customer.otp_expiry:
                messages.error(request, "OTP has expired. Please resend OTP.")
            elif not check_password(otp_value, customer.otp_code):
                customer.otp_attempts += 1
                customer.save(update_fields=["otp_attempts"])
                remaining = max(MAX_OTP_ATTEMPTS - customer.otp_attempts, 0)
                messages.error(
                    request,
                    f"Invalid OTP. {remaining} attempt(s) remaining.",
                )
            else:
                customer.is_verified = True
                customer.otp_code = ""
                customer.otp_expiry = None
                customer.otp_attempts = 0
                customer.save(
                    update_fields=["is_verified", "otp_code", "otp_expiry", "otp_attempts"]
                )
                ensure_auth_user_for_customer(customer, is_active=True)
                request.session.pop("pending_verification_email", None)
                messages.success(request, "Email verified successfully. You can now log in.")
                return redirect("login")
    else:
        form = VerifyOTPForm(initial={"email": pending_email})

    return render(
        request,
        "main/verify_otp.html",
        {
            "form": form,
            "pending_email": pending_email,
        },
    )


@ensure_csrf_cookie
def login_view(request):
    if customer_logged_in(request):
        messages.error(request, "You are already logged in.")
        return redirect("home")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            password = form.cleaned_data["password"]

            customer = Customer.objects.filter(email__iexact=email).first()
            if not customer or not check_password(password, customer.password):
                messages.error(request, "Invalid email or password.")
            elif not customer.is_verified:
                request.session["pending_verification_email"] = customer.email
                messages.error(
                    request,
                    "Please verify your email with OTP before logging in.",
                )
                return redirect(f"{reverse('verify_otp')}?email={customer.email}")
            else:
                auth_user = ensure_auth_user_for_customer(
                    customer,
                    raw_password=password,
                    is_active=True,
                )
                authenticated_user = None
                if auth_user:
                    authenticated_user = authenticate(
                        request,
                        username=auth_user.get_username(),
                        password=password,
                    )
                    if authenticated_user:
                        auth_login(request, authenticated_user)
                    else:
                        auth_user.backend = "django.contrib.auth.backends.ModelBackend"
                        auth_login(request, auth_user)

                request.session["customer_id"] = customer.id
                request.session["customer_business_name"] = customer.business_name
                request.session.set_expiry(10800)
                messages.success(request, "Login successful.")
                return redirect("home")
    else:
        form = LoginForm()

    return render(request, "main/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect("login")
