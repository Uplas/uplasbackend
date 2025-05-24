import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class BaseModel(models.Model):
    """
    An abstract base class model that provides self-updating
    `created_at` and `updated_at` fields, and a UUID primary key.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('ID')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        verbose_name=_('Created At'),
        help_text=_('The date and time this object was first created.')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        verbose_name=_('Last Updated At'),
        help_text=_('The date and time this object was last updated.')
    )

    class Meta:
        abstract = True # Specifies that this model will be an abstract base class.
        ordering = ['-created_at'] # Default ordering for models inheriting this

    def __str__(self):
        # A default string representation, can be overridden in child models.
        return f"{self.__class__.__name__} object ({self.pk})"

# You can add other core models here if needed in the future, for example:
# class SystemSetting(BaseModel):
#     key = models.CharField(max_length=100, unique=True)
#     value = models.JSONField(default=dict)
#     description = models.TextField(blank=True, null=True)

#     class Meta:
#         verbose_name = _('System Setting')
#         verbose_name_plural = _('System Settings')

#     def __str__(self):
#         return self.key

# class FAQ(BaseModel):
#     question = models.CharField(max_length=255, unique=True)
#     answer = models.TextField()
#     category = models.CharField(max_length=100, blank=True, null=True) # e.g., "General", "Payments", "Courses"
#     is_active = models.BooleanField(default=True)
#     display_order = models.PositiveIntegerField(default=0)

#     class Meta:
#         verbose_name = _('FAQ')
#         verbose_name_plural = _('FAQs')
#         ordering = ['display_order', 'question']

#     def __str__(self):
#         return self.question

