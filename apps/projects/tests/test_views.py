from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, MagicMock # For mocking AI agent calls
import uuid

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import ProjectCategory, ProjectTag, Project, UserProject
from apps.courses.models import Course # For associated_courses

User = get_user_model()

# Dummy AI Agent responses for mocking
MOCK_AI_PROJECT_SUGGESTION = {
    "title": "AI Suggested: Sentiment Analyzer",
    "description_html": "<p>Build an AI to analyze sentiment of text.</p>",
    "difficulty_level": "intermediate",
    "estimated_duration": "25 hours",
    "learning_objectives_html": "<ul><li>Learn NLP</li></ul>",
    "tasks_html": "<ol><li>Collect data</li></ol>",
    "suggested_technologies": ["Python", "NLTK"],
}

MOCK_AI_ASSESSMENT_RESULT_PASS = {
    "assessment_score": 85.0,
    "assessment_feedback_html": "<p>Great job! Solid understanding shown.</p>",
}

MOCK_AI_ASSESSMENT_RESULT_FAIL = {
    "assessment_score": 60.0,
    "assessment_feedback_html": "<p>Good effort, but consider improving X and Y.</p>",
}


class ProjectMetaViewTests(APITestCase): # For Category and Tag
    def setUp(self):
        self.category1 = ProjectCategory.objects.create(name="Web Development Projects")
        self.tag1 = ProjectTag.objects.create(name="Python")
        self.tag2 = ProjectTag.objects.create(name="Django")

        self.category_list_url = reverse('projects:projectcategory-list')
        self.tag_list_url = reverse('projects:projecttag-list')

    def test_list_project_categories(self):
        response = self.client.get(self.category_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], self.category1.name)

    def test_list_project_tags(self):
        response = self.client.get(self.tag_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        tag_names = {item['name'] for item in response.data['results']}
        self.assertIn(self.tag1.name, tag_names)
        self.assertIn(self.tag2.name, tag_names)


class ProjectViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="projectuser@example.com", password="password")
        self.staff_user = User.objects.create_user(email="projectstaff@example.com", password="password", is_staff=True)
        self.category = ProjectCategory.objects.create(name="Data Science")
        self.tag_python = ProjectTag.objects.create(name="Python")
        self.tag_ml = ProjectTag.objects.create(name="Machine Learning")

        self.project1_published = Project.objects.create(
            title="Customer Churn Prediction", slug="customer-churn-prediction",
            subtitle="Predict churn using ML", description_html="<p>Detailed desc.</p>",
            category=self.category, difficulty_level='intermediate',
            is_published=True, created_by=self.staff_user
        )
        self.project1_published.tags.add(self.tag_python, self.tag_ml)

        self.project2_draft = Project.objects.create(
            title="Image Classifier", slug="image-classifier",
            subtitle="Classify images", description_html="<p>CNN based.</p>",
            category=self.category, difficulty_level='advanced',
            is_published=False, created_by=self.staff_user
        )
        self.project2_draft.tags.add(self.tag_python)
        
        self.list_url = reverse('projects:project-list')
        self.suggestions_url = reverse('projects:project-suggestions')
        self.detail_url_p1 = reverse('projects:project-detail', kwargs={'slug': self.project1_published.slug})
        self.detail_url_p2_draft = reverse('projects:project-detail', kwargs={'slug': self.project2_draft.slug})


    def test_list_projects_unauthenticated(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # Only published
        self.assertEqual(response.data['results'][0]['title'], self.project1_published.title)

    def test_list_projects_filtering_by_category(self):
        other_cat = ProjectCategory.objects.create(name="Other Cat")
        Project.objects.create(title="Other Cat Project", category=other_cat, is_published=True, description_html="d")
        response = self.client.get(self.list_url, {'category': self.category.slug})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], self.project1_published.title)

    def test_list_projects_filtering_by_tag(self):
        Project.objects.create(title="No ML Tag Project", category=self.category, is_published=True, description_html="d").tags.add(self.tag_python)
        response = self.client.get(self.list_url, {'tag': self.tag_ml.slug}) # Should be 'tag' not 'tags' for single tag filter based on common patterns, or 'tags__slug'
        # Current view filtering uses 'tag', so this is correct for the view.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], self.project1_published.title)

    def test_retrieve_published_project(self):
        response = self.client.get(self.detail_url_p1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.project1_published.title)
        self.assertEqual(len(response.data['tags']), 2)

    def test_retrieve_draft_project_unauthenticated_fails(self):
        response = self.client.get(self.detail_url_p2_draft)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # ReadOnlyModelViewSet default

    def test_retrieve_draft_project_staff_succeeds(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.detail_url_p2_draft) # Staff can see drafts
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.project2_draft.title)

    @patch('apps.projects.views.ProjectViewSet.get_serializer') # Mock serializer if AI call is complex
    @patch('apps.projects.views.Project.objects.filter') # Mock DB call for simplicity of suggestion logic test
    def test_project_suggestions_authenticated(self, mock_project_filter, mock_get_serializer):
        self.client.force_authenticate(user=self.user)
        # Simulate the AI agent call or direct DB query for suggestions
        # Current view placeholder logic returns featured or recent.
        mock_project_filter.return_value.order_by.return_value.exists.return_value = True
        mock_project_filter.return_value.order_by.return_value = [self.project1_published]
        
        # Mock the serializer instance
        mock_serializer_instance = MagicMock()
        mock_serializer_instance.data = [ProjectSerializer(self.project1_published, context={'request': self.client.request}).data]
        mock_get_serializer.return_value = mock_serializer_instance

        response = self.client.get(self.suggestions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0) # Check if some data is returned
        mock_project_filter.assert_called() # Check that our DB query for placeholder was attempted

    def test_project_suggestions_unauthenticated(self):
        response = self.client.get(self.suggestions_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserProjectViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email="userproj1@example.com", password="password")
        self.user2 = User.objects.create_user(email="userproj2@example.com", password="password")
        self.project1 = Project.objects.create(title="P1", slug="p1", description_html="d1", is_published=True)
        self.project2 = Project.objects.create(title="P2", slug="p2", description_html="d2", is_published=True)

        # User1 starts project1
        self.user_project1_user1 = UserProject.objects.create(user=self.user1, project=self.project1, status='active', started_at=timezone.now())

        self.my_projects_url = reverse('projects:userproject-list')
        self.start_project_action_url = reverse('projects:userproject-start-project')
        self.detail_user_project1_url = reverse('projects:userproject-detail', kwargs={'pk': self.user_project1_user1.pk})
        self.submit_action_url = reverse('projects:userproject-submit-project', kwargs={'pk': self.user_project1_user1.pk})
        self.update_assessment_url = reverse('projects:userproject-update-assessment-results', kwargs={'pk': self.user_project1_user1.pk})

        self.client = APIClient()


    def test_list_my_projects_authenticated(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.my_projects_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['project']['title'], self.project1.title)
        self.assertEqual(response.data['results'][0]['status'], 'active')

    def test_list_my_projects_no_projects_started(self):
        self.client.force_authenticate(user=self.user2) # user2 has no projects
        response = self.client.get(self.my_projects_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)

    def test_list_my_projects_unauthenticated(self):
        response = self.client.get(self.my_projects_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_start_project_action_success(self):
        self.client.force_authenticate(user=self.user1)
        # User1 tries to start project2 (has not started it yet)
        data = {"project_id": str(self.project2.id)}
        response = self.client.post(self.start_project_action_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(UserProject.objects.filter(user=self.user1, project=self.project2, status='active').exists())

    def test_start_project_action_already_started(self):
        self.client.force_authenticate(user=self.user1)
        # User1 tries to start project1 again (already started)
        data = {"project_id": str(self.project1.id)}
        response = self.client.post(self.start_project_action_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Or 200 with a message, depends on desired UX

    def test_start_project_action_invalid_project_id(self):
        self.client.force_authenticate(user=self.user1)
        data = {"project_id": str(uuid.uuid4())} # Non-existent project
        response = self.client.post(self.start_project_action_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # get_object_or_404 in view

    def test_retrieve_user_project_detail_owner(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get(self.detail_user_project1_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['project']['title'], self.project1.title)

    def test_retrieve_user_project_detail_not_owner_fails(self):
        self.client.force_authenticate(user=self.user2) # user2 tries to access user1's project
        response = self.client.get(self.detail_user_project1_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # get_queryset filters by user

    # For submit_project, we need to mock the AI Assessment Agent trigger
    @patch('apps.projects.views.transaction.atomic') # Mock transaction to simplify if AI call is complex
    # @patch('apps.projects.views.request_project_assessment') # If this function is directly in views
    def test_submit_project_success(self, mock_transaction_atomic): # mock_request_assessment
        self.client.force_authenticate(user=self.user1)
        # mock_request_assessment.return_value = {"assessment_job_id": "job123", "status": "assessment_pending"}
        submission_payload = {
            "submission_type": "repo_url",
            "repository_url": "https://github.com/my/project_repo"
        }
        response = self.client.post(self.submit_action_url, submission_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user_project1_user1.refresh_from_db()
        self.assertEqual(self.user_project1_user1.status, 'submitted')
        self.assertEqual(self.user_project1_user1.submission_type, 'repo_url')
        self.assertEqual(self.user_project1_user1.submission_data_json['repository_url'], "https://github.com/my/project_repo")
        self.assertIsNotNone(self.user_project1_user1.submitted_at)
        # mock_request_assessment.assert_called_once() # Verify AI trigger

    def test_submit_project_invalid_status(self):
        self.client.force_authenticate(user=self.user1)
        self.user_project1_user1.status = 'completed_passed' # Cannot submit if already completed
        self.user_project1_user1.save()
        submission_payload = {"submission_type": "text_input", "submission_content": "Done."}
        response = self.client.post(self.submit_action_url, submission_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # For update_assessment_results, this is called by the AI agent
    # @patch('apps.projects.views.trigger_ai_tutor') # If this function exists
    def test_update_assessment_results_pass(self): #, mock_trigger_ai_tutor
        # This endpoint is typically not authenticated by user session, but by service key / IP
        # For test simplicity, we'll assume it's accessible or use a way to bypass auth for this specific call.
        # Or, create a dedicated service user for AI agent and authenticate as that.
        # For now, let's assume the permission is AllowAny or a specific service permission.
        
        self.user_project1_user1.status = 'submitted' # Prerequisite
        self.user_project1_user1.save()

        payload = MOCK_AI_ASSESSMENT_RESULT_PASS
        # No client authentication needed if permission is AllowAny for this specific action
        response = self.client.post(self.update_assessment_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user_project1_user1.refresh_from_db()
        self.assertEqual(self.user_project1_user1.status, 'completed_passed')
        self.assertEqual(self.user_project1_user1.assessment_score, payload['assessment_score'])
        self.assertEqual(self.user_project1_user1.assessment_feedback_html, payload['assessment_feedback_html'])
        self.assertIsNotNone(self.user_project1_user1.completed_at)
        # mock_trigger_ai_tutor.assert_not_called()

    @patch('apps.projects.views.print') # Mock the print statement that simulates AI Tutor trigger
    def test_update_assessment_results_fail_triggers_tutor_mock(self, mock_print_trigger_tutor):
        self.user_project1_user1.status = 'submitted'
        self.user_project1_user1.save()
        payload = MOCK_AI_ASSESSMENT_RESULT_FAIL
        response = self.client.post(self.update_assessment_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_project1_user1.refresh_from_db()
        self.assertEqual(self.user_project1_user1.status, 'completed_failed')
        mock_print_trigger_tutor.assert_called_with(f"AI Tutor should be triggered for UserProject {self.user_project1_user1.id} due to score {payload['assessment_score']}")
