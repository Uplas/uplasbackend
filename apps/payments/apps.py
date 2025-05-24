from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymentsConfig(AppConfig):
    """
    Application configuration for the 'payments' app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payments'
    verbose_name = _('Payments & Subscriptions Management')

    def ready(self):
        """
        Called when the application is ready.
        This is a good place to import signals if they are defined in a separate signals.py file
        for this app. For the payments app, most logic related to model updates based on
        external events (like Stripe) will be handled in views (webhook handlers) rather than
        direct model signals within this app.
        """
        try:
            # Import models to ensure any model-level decorators are processed if any were added.
            import apps.payments.models
            # If you had a dedicated signals.py for this app:
            # import apps.payments.signals
        except ImportError:
            pass


