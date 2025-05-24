from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CommunityConfig(AppConfig):
    """
    Application configuration for the 'community' app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.community'
    verbose_name = _('Community Forums & Interactions')

    def ready(self):
        """
        Called when the application is ready.
        This is a good place to import signals if they are defined in a separate signals.py file.
        Since our signals (for like counts, reply counts, etc.) are defined within the
        community app's models.py using @receiver, Django's default mechanism
        usually handles their connection well. Explicitly importing the models module here
        can serve as an additional measure to ensure all model-level decorators are processed.
        """
        try:
            # Ensures models (and thus any signals defined with decorators in models.py) are loaded.
            import apps.community.models
            # If you had a dedicated signals.py for this app, you would import it:
            # import apps.community.signals
        except ImportError:
            pass


