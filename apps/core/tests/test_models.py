from django.test import TestCase
# from ..models import SystemSetting, FAQ # Example if you add these models

# Abstract base models like BaseModel are not tested directly here.
# Their functionality (UUIDs, timestamps) is tested when testing
# the concrete models that inherit from them in other apps.

# If you add concrete models to apps.core.models, write their tests here.
# Example:
# class SystemSettingModelTests(TestCase):
#     def test_system_setting_creation(self):
#         # setting = SystemSetting.objects.create(key="site_name", value={"name": "UPLAS Platform"})
#         # self.assertEqual(setting.key, "site_name")
#         pass

# class FAQModelTests(TestCase):
#     def test_faq_creation(self):
#         # faq = FAQ.objects.create(question="How to enroll?", answer="Go to courses page...")
#         # self.assertIn("How to enroll", faq.question)
#         pass
