import re
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

from .models import Customer


def _make_unique_business_name(base_name):
    base = re.sub(r"[^a-zA-Z0-9 ]+", "", (base_name or "").strip()) or "Google User"
    candidate = base[:200]
    suffix = 1
    while Customer.objects.filter(business_name__iexact=candidate).exists():
        extra = f" {suffix}"
        candidate = f"{base[: max(1, 200 - len(extra))]}{extra}"
        suffix += 1
    return candidate


def _make_unique_phone_number():
    while True:
        number = f"07{secrets.randbelow(10**8):08d}"
        if not Customer.objects.filter(phone_number=number).exists():
            return number


def _make_unique_username(user_model, preferred):
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", (preferred or "").strip()).strip("_") or "user"
    candidate = base[:150]
    suffix = 1
    while user_model._default_manager.filter(username__iexact=candidate).exists():
        suffix_part = f"_{suffix}"
        candidate = f"{base[: max(1, 150 - len(suffix_part))]}{suffix_part}"
        suffix += 1
    return candidate


def ensure_customer_for_user(user):
    if not user or not user.is_authenticated:
        return None

    email = (user.email or "").strip().lower()
    if not email:
        return None

    customer = Customer.objects.filter(email__iexact=email).first()
    if not customer:
        display_name = (
            user.get_full_name().strip()
            or user.get_username().strip()
            or email.split("@")[0]
        )
        customer = Customer.objects.create(
            business_name=_make_unique_business_name(display_name),
            email=email,
            phone_number=_make_unique_phone_number(),
            password=make_password(None),
            confirm_password=make_password(None),
            is_verified=True,
        )
    else:
        update_fields = []
        if not customer.is_verified:
            customer.is_verified = True
            update_fields.append("is_verified")
        if update_fields:
            customer.save(update_fields=update_fields)

    return customer


def sync_customer_session(request, customer, *, session_expiry=10800):
    if not request or not customer:
        return
    request.session["customer_id"] = customer.id
    request.session["customer_business_name"] = customer.business_name
    request.session.set_expiry(session_expiry)


def sync_customer_from_request(request):
    user = getattr(request, "user", None)
    customer = ensure_customer_for_user(user)
    if customer:
        sync_customer_session(request, customer)
    return customer


def ensure_allauth_email_address(user, *, email=None, verified=False):
    if not user:
        return None

    try:
        from allauth.account.models import EmailAddress
    except Exception:
        return None

    resolved_email = (email or user.email or "").strip().lower()
    if not resolved_email:
        return None

    email_address, _ = EmailAddress.objects.get_or_create(
        user=user,
        email=resolved_email,
        defaults={
            "primary": True,
            "verified": bool(verified),
        },
    )

    update_fields = []
    if not email_address.primary:
        email_address.primary = True
        update_fields.append("primary")
    if bool(verified) and not email_address.verified:
        email_address.verified = True
        update_fields.append("verified")
    if update_fields:
        email_address.save(update_fields=update_fields)

    # Keep any other email rows for this user non-primary.
    EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)
    return email_address


def ensure_auth_user_for_customer(customer, raw_password=None, is_active=None):
    if not customer:
        return None

    email = (customer.email or "").strip().lower()
    if not email:
        return None

    user_model = get_user_model()
    user = user_model._default_manager.filter(email__iexact=email).first()
    if not user:
        preferred_username = customer.business_name or email.split("@")[0]
        username = _make_unique_username(user_model, preferred_username)
        user = user_model._default_manager.create_user(
            username=username,
            email=email,
            password=raw_password,
        )
        if not raw_password:
            user.set_unusable_password()
            if is_active is None:
                user.save(update_fields=["password"])
            else:
                user.is_active = bool(is_active)
                user.save(update_fields=["password", "is_active"])
        elif is_active is not None and user.is_active != bool(is_active):
            user.is_active = bool(is_active)
            user.save(update_fields=["is_active"])
        ensure_allauth_email_address(
            user,
            email=email,
            verified=bool(getattr(customer, "is_verified", False)),
        )
        return user

    update_fields = []
    if (user.email or "").strip().lower() != email:
        user.email = email
        update_fields.append("email")
    if raw_password and not user.check_password(raw_password):
        user.set_password(raw_password)
        update_fields.append("password")
    if not raw_password:
        customer_password_hash = (customer.password or "").strip()
        has_usable_customer_hash = "$" in customer_password_hash and not customer_password_hash.startswith("!")
        if has_usable_customer_hash and user.password != customer_password_hash:
            user.password = customer_password_hash
            update_fields.append("password")
    if is_active is not None and user.is_active != bool(is_active):
        user.is_active = bool(is_active)
        update_fields.append("is_active")
    if update_fields:
        user.save(update_fields=update_fields)

    ensure_allauth_email_address(
        user,
        email=email,
        verified=bool(getattr(customer, "is_verified", False)),
    )
    return user
