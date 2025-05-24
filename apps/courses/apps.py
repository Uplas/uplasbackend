from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoursesConfig(AppConfig):
    """
    Application configuration for the 'courses' app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.courses'
    verbose_name = _('Courses Management')

    def ready(self):
        """
        Called when the application is ready.
        This is a good place to import signals if they are defined in a separate signals.py file.
        Since our signals are in models.py, Django's default mechanism usually handles their connection.
        However, explicitly importing the models module here can ensure all model-level
        decorators (like @receiver) are processed.
        """
        try:
            import apps.courses.models # Ensures models (and thus signals) are loaded
        except ImportError:
            pass
        # If you had a dedicated signals.py, you would import it like so:
        # import apps.courses.signals

