from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    """
    Application configuration for the 'users' app.
    This app handles user authentication, profiles, and related functionalities.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users' # Full Python path to the application
    verbose_name = _('User Management & Authentication')

    def ready(self):
        """
        Called when the Django application registry is fully populated.
        This is the recommended place to import signals to ensure they are connected.
        """
        try:
            # Import the models module where signals are defined (e.g., using @receiver)
            # to ensure they are registered.
            import apps.users.models
            # If you had a separate signals.py file, you would import it here:
            # import apps.users.signals
        except ImportError:
            # Handle the case where models (or signals) might not be ready or importable,
            # though this is unlikely in a standard setup.
            pass

