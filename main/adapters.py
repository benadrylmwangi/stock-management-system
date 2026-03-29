from django.contrib.auth import get_user_model
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to streamline Google login flow:
    - Auto-link social login to existing local user by email.
    - Allow auto-signup for first-time Google users.
    """

    def pre_social_login(self, request, sociallogin):
        # If already connected to a social account, or user is already logged in,
        # let allauth continue with default behavior.
        if request.user.is_authenticated or sociallogin.is_existing:
            return

        # Try to find a local user with the same email as the social account.
        email = (sociallogin.user.email or "").strip().lower()
        if not email:
            return

        user_model = get_user_model()
        existing_user = user_model._default_manager.filter(email__iexact=email).first()
        if existing_user:
            # Link Google account to existing user and continue login flow.
            sociallogin.connect(request, existing_user)

    def is_auto_signup_allowed(self, request, sociallogin):
        # Ensures first-time Google users are created automatically
        # (no intermediate social signup form).
        return True
