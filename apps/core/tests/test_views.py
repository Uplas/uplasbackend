from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class APIRootViewTests(APITestCase):

    def test_api_root_view_exists_and_returns_links(self):
        """
        Ensure the API root view exists and returns a list of top-level endpoints.
        """
        # Create a dummy user for authentication if any endpoints require it for reversing
        # For simplicity, assuming most list endpoints are accessible to reverse.
        # user = User.objects.create_user(username='testapirt', password='password')
        # self.client.force_authenticate(user=user) # Or use JWT if that's your default

        url = reverse('core:api-root') # Assuming 'core' namespace and 'api-root' name
        response = self.client.get(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check for the presence of keys you expect in your api_root response
        # These keys depend on what you've defined in your core.views.api_root
        # and the URL names in other apps.
        self.assertIn('users_auth', response.data) # Example key
        self.assertIn('courses', response.data)   # Example key
        # Add more assertions for other keys you expect
        # For example:
        # self.assertTrue(response.data['courses'].endswith('/api/courses/'))

    # If you add concrete models and ViewSets to the core app,
    # you would add more test classes here for those views, similar to other apps.
    # For example:
    # class FAQViewSetTests(APITestCase):
    #     @classmethod
    #     def setUpTestData(cls):
    #         # from ..models import FAQ # Adjust import
    #         # FAQ.objects.create(question="What is UPLAS?", answer="An online learning platform.")
    #         pass

    #     def test_list_faqs(self):
    #         # url = reverse('core:faq-list') # Assuming URL name
    #         # response = self.client.get(url)
    #         # self.assertEqual(response.status_code, status.HTTP_200_OK)
    #         pass
