from functools import wraps
import re

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import redirect, render

from .models import Commodity, Customer


# Create your views here.
def customer_logged_in(request):
    return bool(request.session.get("customer_id"))


def login_required_customer(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not customer_logged_in(request):
            messages.error(request, "Please login or register to continue.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return _wrapped


def index(request):
    if customer_logged_in(request):
        return redirect("home")
    return redirect("login")


@login_required_customer
def home(request):
    if request.method == "POST":
        name = request.POST.get("name")

        Commodity.objects.create(
            name=name,
        )
        return redirect("home")

    return render(request, "main/home.html")


@login_required_customer
def pricing(request):
    return render(request, "main/pricing.html", {})


@login_required_customer
def sales(request):
    return render(request, "main/sales.html", {})


@login_required_customer
def stock(request):
    if request.method == "POST":
        commodity_name = request.POST.get("commodity_name", "").strip()
        quantity = request.POST.get("quantity")
        buying_price = request.POST.get("buying_price")
        selling_price = request.POST.get("selling_price")
        amount = request.POST.get("amount")
        total_amount = request.POST.get("total_amount")

        if commodity_name:
            Commodity.objects.update_or_create(
                name=commodity_name,
                defaults={
                    "number_of_commodity": quantity,
                    "buying_price": buying_price,
                    "selling_price": selling_price,
                    "amount": amount,
                    "total_amount": total_amount,
                },
            )

    return render(request, "main/stock.html", {})


@login_required_customer
def aboutus(request):
    return render(request, "main/aboutus.html", {})


@login_required_customer
def resources(request):
    return render(request, "main/resources.html", {})


@login_required_customer
def features(request):
    return render(request, "main/features.html", {})


def register(request):
    if customer_logged_in(request):
        messages.error(request, "You are already logged in.")
        return redirect("home")

    if request.method == "POST":
        business_name = request.POST.get("business_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "main/register.html", locals())

        pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"
        if not re.match(pattern, password):
            messages.error(
                request,
                "Password must be at least 8 characters long and contain:<br>"
                "- At least one uppercase letter<br>"
                "- At least one lowercase letter<br>"
                "- At least one number<br>"
                "- At least one special character (@$!%*?&)",
            )
            return render(request, "main/register.html", locals())

        Customer.objects.create(
            business_name=business_name,
            email=email,
            phone_number=phone_number,
            password=make_password(password),
        )

        messages.success(request, "Registration successful! You can now log in.")
        return redirect("login")

    return render(request, "main/register.html")


def login_view(request):
    if customer_logged_in(request):
        messages.error(request, "You are already logged in.")
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        customer = Customer.objects.filter(email=email).first()
        if customer and check_password(password, customer.password):
            request.session["customer_id"] = customer.id
            request.session["customer_business_name"] = customer.business_name
            messages.success(request, "Login successful.")
            return redirect("home")

        messages.error(request, "Invalid email or password.")

    return render(request, "main/login.html")


def logout_view(request):
    request.session.flush()
    messages.success(request, "You have been logged out.")
    return redirect("login")
