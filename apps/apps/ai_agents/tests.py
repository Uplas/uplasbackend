# apps/ai_agents/tests.py
import uuid
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User, UserProfile # Need user for authentication
from apps.projects.models import Project, UserProject, ProjectSubmission # For assessment test setup

class AIAgentsViewsTests(APITestCase):

    def setUp(self):
        """Set up a test user and necessary data for tests."""
        self.password = 'StrongTestP@ssw0rd'
        self.user = User.objects.create_user(
            email='testuser@uplas.me',
            first_name='Test',
            last_name='User',
            password=self.password,
            profession='Developer',
            city='Nairobi',
            country='Kenya',
            industry='Technology'
        )
        # Ensure UserProfile exists
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.learning_goals = "Master Django and AI"
        self.profile.save()

        # Log the user in to get an auth token (or use force_authenticate)
        # For simplicity, we'll use force_authenticate in tests.
        self.client.force_authenticate(user=self.user)

        # Define AI service URLs (even if None, for patching targets)
        self.tutor_url = settings.AI_NLP_TUTOR_SERVICE_URL + "/ask"
        self.tts_url = settings.AI_TTS_SERVICE_URL + "/generate"
        self.assessment_url = settings.AI_PROJECT_ASSESSMENT_SERVICE_URL + "/assess"

    @patch('apps.ai_agents.views.requests.post') # Patch where 'requests' is *used*
    def test_ask_ai_tutor_success(self, mock_post):
        """Test the AskAITutorView successfully gets a response."""
        url = reverse('ai_agents:tutor-ask')
        question_data = {'question_text': 'What is Django ORM?'}
        
        # Configure the mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'answer_text': 'Django ORM is a powerful tool...'}
        mock_post.return_value = mock_response

        # Make the API call
        response = self.client.post(url, question_data, format='json')

        # Assertions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['answer_text'], 'Django ORM is a powerful tool...')
        
        # Verify that requests.post was called correctly
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], self.tutor_url) # Check URL
        self.assertIn('user_id', kwargs['json']) # Check payload structure
        self.assertEqual(kwargs['json']['user_profile_data']['career'], 'Developer')
        self.assertEqual(kwargs['json']['question_text'], 'What is Django ORM?')

    @patch('apps.ai_agents.views.requests.post')
    def test_ask_ai_tutor_service_error(self, mock_post):
        """Test how the view handles an error from the AI service."""
        url = reverse('ai_agents:tutor-ask')
        question_data = {'question_text': 'Explain quantum physics.'}

        # Configure the mock to raise an HTTPError
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {'error': 'Internal AI Service Error'}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        response = self.client.post(url, question_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('error', response.data)
        self.assertIn('Internal AI Service Error', response.data['error'])

    def test_ask_ai_tutor_unauthenticated(self):
        """Test unauthenticated access is denied."""
        self.client.force_authenticate(user=None) # Log out
        url = reverse('ai_agents:tutor-ask')
        response = self.client.post(url, {'question_text': 'Hi'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- TODO: Add similar tests for ---
    # - test_generate_tts_success()
    # - test_generate_tts_failure()
    # - test_generate_ttv_success()
    # - test_generate_ttv_failure()
    # - test_generate_project_idea_success()
    # - test_generate_project_idea_failure()
    # - test_assess_project_success() (Requires more setup for ProjectSubmission)
    # - test_assess_project_failure()
    # - test_views_with_invalid_serializer_data()
