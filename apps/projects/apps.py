from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProjectsConfig(AppConfig):
    """
    Application configuration for the 'projects' app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.projects'
    verbose_name = _('Projects, Submissions & Assessments')

    def ready(self):
        """
        Called when the application is ready.
        This is a good place to import signals if they were defined in a separate signals.py file.
        Since our signals are currently part of the models' save() methods,
        ensuring models are loaded is sufficient.
        """
        try:
            # Ensures models (and any model-level decorators/signals) are loaded.
            import apps.projects.models
            # If you had a dedicated signals.py for this app, you would import it here:
            # import apps.projects.signals
        except ImportError:
            pass
