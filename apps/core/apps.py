from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    """
    Application configuration for the 'core' app.
    This app may contain base models, utilities, or other core functionalities.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = _('Core Application Utilities')

    def ready(self):
        """
        Called when the application is ready.
        If the 'core' app had its own signals (e.g., in a signals.py file),
        they would be imported here. Since BaseModel is abstract, signals related
        to its fields would be on the inheriting models in other apps.
        """
        try:
            # Ensures models (and any model-level decorators if any were added) are loaded.
            import apps.core.models
        except ImportError:
            pass
        # If you were to add concrete models to 'core' with their own signals:
        # import apps.core.signals

