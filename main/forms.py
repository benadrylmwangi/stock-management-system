from django import forms
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Customer, Expense, ReturnEntry, Sales


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Password",
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        label="Confirm Password",
    )

    class Meta:
        model = Customer
        fields = ["business_name", "email", "phone_number"]
        widgets = {
            "business_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if Customer.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_business_name(self):
        value = (self.cleaned_data.get("business_name") or "").strip()
        if not value:
            raise forms.ValidationError("Business name is required.")
        return value

    def clean_phone_number(self):
        value = (self.cleaned_data.get("phone_number") or "").strip()
        if not value:
            raise forms.ValidationError("Phone number is required.")
        if Customer.objects.filter(phone_number=value).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return value

    def clean_password1(self):
        password = self.cleaned_data.get("password1") or ""
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        customer = super().save(commit=False)
        raw_password = self.cleaned_data["password1"]
        customer.password = make_password(raw_password)
        # Keep confirm_password non-plain and in sync with password storage.
        customer.confirm_password = customer.password
        customer.is_verified = False
        customer.otp_code = ""
        customer.otp_expiry = None
        customer.otp_attempts = 0
        if commit:
            customer.save()
        return customer


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))


class VerifyOTPForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "you@example.com"}
        )
    )
    otp_code = forms.CharField(
        max_length=6,
        min_length=6,
        label="OTP Code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "inputmode": "numeric",
                "placeholder": "Enter 6-digit code",
                "maxlength": "6",
            }
        ),
    )

    def clean_otp_code(self):
        value = (self.cleaned_data.get("otp_code") or "").strip()
        if not value.isdigit():
            raise forms.ValidationError("OTP must contain only numbers.")
        return value


class SaleForm(forms.Form):
    customer_name = forms.CharField(max_length=200, required=False)
    name = forms.CharField(max_length=200)
    number_of_commodity = forms.IntegerField(min_value=1)
    buying_price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    selling_price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.HiddenInput(),
    )
    payment_type = forms.ChoiceField(choices=Sales.PaymentType.choices, initial=Sales.PaymentType.CASH)

    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get("payment_type")
        customer_name = (cleaned_data.get("customer_name") or "").strip()
        self.number_of_commodity = cleaned_data.get("number_of_commodity")
        self.buying_price = cleaned_data.get("buying_price")
        self.selling_price = cleaned_data.get("selling_price")
        self.amount = cleaned_data.get("amount")

        if payment_type == Sales.PaymentType.CREDIT and not customer_name:
            self.add_error("customer_name", "Customer name is required for credit sales.")

        cleaned_data["customer_name"] = customer_name
        return cleaned_data


class CreditPaymentForm(forms.Form):
    customer_name = forms.CharField(max_length=200)
    payment_amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    def clean_customer_name(self):
        return (self.cleaned_data.get("customer_name") or "").strip()


class ReturnForm(forms.Form):
    return_type = forms.ChoiceField(choices=ReturnEntry.ReturnType.choices)
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    note = forms.CharField(max_length=200, required=False)

    def clean_note(self):
        return (self.cleaned_data.get("note") or "").strip()


class ExpenseForm(forms.Form):
    description = forms.CharField(max_length=200)
    amount = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    def clean_description(self):
        return (self.cleaned_data.get("description") or "").strip()
