from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.projects.models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment
)
# Import serializers to compare response data (optional, can also check specific fields)
from apps.projects.serializers import (
    ProjectTagSerializer, ProjectListSerializer, ProjectDetailSerializer,
    UserProjectListSerializer, UserProjectDetailSerializer,
    ProjectSubmissionSerializer, ProjectAssessmentSerializer
)

User = get_user_model()

# Test Data Setup Mixin (adapted for APITestCase)
class ProjectsViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='projview_admin', email='projview_admin@example.com', password='password123',
            full_name='ProjView Admin'
        )
        cls.instructor_user = User.objects.create_user(
            username='projview_instructor', email='projview_instructor@example.com', password='password123',
            full_name='ProjView Instructor', is_staff=True # Often instructors have staff-like permissions for content
        )
        cls.user1 = User.objects.create_user(
            username='projview_user1', email='projview_user1@example.com', password='password123',
            full_name='ProjView User One'
        )
        cls.user2 = User.objects.create_user(
            username='projview_user2', email='projview_user2@example.com', password='password123',
            full_name='ProjView User Two'
        )

        cls.tag_python = ProjectTag.objects.create(name='Python ViewTest', slug='python-viewtest')
        cls.tag_frontend = ProjectTag.objects.create(name='Frontend ViewTest', slug='frontend-viewtest')

        cls.project_def1_published = Project.objects.create(
            title='Published Project Alpha', slug='published-project-alpha',
            description='A great published project.', difficulty_level='intermediate',
            is_published=True, created_by=cls.instructor_user
        )
        cls.project_def1_published.technologies_used.add(cls.tag_python)

        cls.project_def2_unpublished = Project.objects.create(
            title='Unpublished Project Beta', slug='unpublished-project-beta',
            description='An internal project.', difficulty_level='advanced',
            is_published=False, created_by=cls.instructor_user
        )
        cls.project_def2_unpublished.technologies_used.add(cls.tag_frontend)
        
        cls.project_def3_other_instructor = Project.objects.create(
            title='Other Instructor Project', slug='other-instructor-project',
            description='A project by another instructor.', difficulty_level='beginner',
            is_published=True, created_by=cls.admin_user # Admin as another creator for variety
        )


        cls.user_project_user1 = UserProject.objects.create(
            user=cls.user1, project=cls.project_def1_published, status='in_progress',
            started_at=timezone.now()
        )
        cls.submission_user1 = ProjectSubmission.objects.create(
            user_project=cls.user_project_user1,
            submission_notes="User 1 first submission"
        )
        # user_project_user1 status becomes 'submitted'
        
        cls.assessment_user1 = ProjectAssessment.objects.create(
            submission=cls.submission_user1,
            assessed_by_ai=False, # Manual for this test
            manual_assessor=cls.instructor_user,
            score=80.0,
            passed=True,
            feedback_summary="Good effort!"
        )
        # user_project_user1 status becomes 'completed'

    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {'refresh': str(refresh), 'access': str(refresh.access_token)}

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

    def setUp(self):
        super().setUp() # Call parent setUp if it exists


class ProjectTagViewSetTests(ProjectsViewTestDataMixin, APITestCase):
    def test_list_tags_anonymous(self):
        url = reverse('projects:project-tag-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 2)

    def test_retrieve_tag_anonymous(self):
        url = reverse('projects:project-tag-detail', kwargs={'slug': self.tag_python.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.tag_python.name)

    def test_create_tag_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('projects:project-tag-list')
        data = {'name': 'New Tag by Admin', 'slug': 'new-tag-admin'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ProjectTag.objects.filter(slug='new-tag-admin').exists())

    def test_create_tag_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.user1) # Authenticated non-admin
        url = reverse('projects:project-tag-list')
        data = {'name': 'Forbidden Tag', 'slug': 'forbidden-tag'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectViewSetTests(ProjectsViewTestDataMixin, APITestCase):
    def test_list_project_definitions_anonymous(self):
        """ Anonymous users should only see published project definitions. """
        url = reverse('projects:project-definition-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # project_def1_published and project_def3_other_instructor are published
        self.assertEqual(len(response.data['results']), 2)
        slugs_in_response = [item['slug'] for item in response.data['results']]
        self.assertIn(self.project_def1_published.slug, slugs_in_response)
        self.assertIn(self.project_def3_other_instructor.slug, slugs_in_response)
        self.assertNotIn(self.project_def2_unpublished.slug, slugs_in_response)

    def test_retrieve_published_project_definition_anonymous(self):
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def1_published.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.project_def1_published.title)

    def test_retrieve_unpublished_project_definition_anonymous_forbidden(self):
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def2_unpublished.slug})
        response = self.client.get(url)
        # IsProjectCreatorOrAdminOrReadOnly denies access to unpublished for anonymous
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # Or 404 if queryset filters it out first

    def test_retrieve_unpublished_project_definition_by_creator(self):
        self.authenticate_client_with_jwt(self.instructor_user) # Creator of project_def2_unpublished
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.project_def2_unpublished.title)

    def test_retrieve_unpublished_project_definition_by_admin(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.project_def2_unpublished.title)

    def test_create_project_definition_by_instructor_success(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('projects:project-definition-list')
        data = {
            "title": "Instructor's New Project Def", "slug": "instr-new-proj-def",
            "description": "Details here.", "difficulty_level": "beginner", "is_published": True,
            "technology_tag_ids": [self.tag_python.id]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_project = Project.objects.get(slug="instr-new-proj-def")
        self.assertEqual(new_project.created_by, self.instructor_user)
        self.assertIn(self.tag_python, new_project.technologies_used.all())

    def test_create_project_definition_by_regular_user_as_creator(self):
        # Based on current IsProjectCreatorOrAdminOrReadOnly, authenticated users can create.
        # The serializer sets created_by=request.user.
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('projects:project-definition-list')
        data = {"title": "User1 New Project Def", "description": "User1 proj.", "difficulty_level": "beginner"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_project = Project.objects.get(slug=slugify("User1 New Project Def"))
        self.assertEqual(new_project.created_by, self.user1)


    def test_update_own_project_definition_by_creator_success(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def1_published.slug})
        data = {"title": "Published Project Alpha (Updated by Creator)"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project_def1_published.refresh_from_db()
        self.assertEqual(self.project_def1_published.title, "Published Project Alpha (Updated by Creator)")

    def test_update_other_creator_project_definition_forbidden(self):
        self.authenticate_client_with_jwt(self.user1) # user1 is not creator of project_def1_published
        url = reverse('projects:project-definition-detail', kwargs={'slug': self.project_def1_published.slug})
        data = {"title": "Attempted Update by Non-Creator"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_start_project_action_success(self):
        self.authenticate_client_with_jwt(self.user2) # user2 has not started project_def1_published yet
        url = reverse('projects:project-definition-start-project', kwargs={'slug': self.project_def1_published.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(UserProject.objects.filter(user=self.user2, project=self.project_def1_published, status='in_progress').exists())
        self.assertIsNotNone(response.data.get('id')) # Should return the created UserProject data

    def test_start_project_action_already_started_fails(self):
        self.authenticate_client_with_jwt(self.user1) # user1 has already started project_def1_published
        url = reverse('projects:project-definition-start-project', kwargs={'slug': self.project_def1_published.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You have already started this project", str(response.data))

    def test_start_project_action_unpublished_project_fails(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('projects:project-definition-start-project', kwargs={'slug': self.project_def2_unpublished.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not published", str(response.data))


class UserProjectViewSetTests(ProjectsViewTestDataMixin, APITestCase):
    def test_list_my_user_projects(self):
        self.authenticate_client_with_jwt(self.user1)
        # Create another UserProject for user1
        project_def_temp = Project.objects.create(title="Temp Proj", slug="temp-proj", description="d", is_published=True, created_by=self.instructor_user)
        UserProject.objects.create(user=self.user1, project=project_def_temp)

        url = reverse('projects:user-project-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # user_project_user1 and the new temp one

    def test_list_user_projects_admin_sees_all(self):
        self.authenticate_client_with_jwt(self.admin_user)
        UserProject.objects.create(user=self.user2, project=self.project_def1_published) # User2 also has a project
        url = reverse('projects:user-project-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 2) # At least user1's and user2's

    def test_retrieve_own_user_project(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('projects:user-project-detail', kwargs={'pk': self.user_project_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['project']['slug'], self.project_def1_published.slug)

    def test_retrieve_other_user_project_forbidden(self):
        self.authenticate_client_with_jwt(self.user2) # user2 trying to access user1's project
        url = reverse('projects:user-project-detail', kwargs={'pk': self.user_project_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # IsUserProjectOwner filters queryset

    def test_update_own_user_project_urls(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('projects:user-project-detail', kwargs={'pk': self.user_project_user1.pk})
        data = {"repository_url": "https://new.github.com/repo", "live_url": "https://new.live.app"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user_project_user1.refresh_from_db()
        self.assertEqual(self.user_project_user1.repository_url, data["repository_url"])

    def test_update_user_project_status_to_inprogress(self):
        # Create a new UserProject that is 'not_started'
        up_not_started = UserProject.objects.create(user=self.user2, project=self.project_def3_other_instructor, status='not_started')
        self.assertIsNone(up_not_started.started_at)

        self.authenticate_client_with_jwt(self.user2)
        url = reverse('projects:user-project-detail', kwargs={'pk': up_not_started.pk})
        data = {"status": "in_progress"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        up_not_started.refresh_from_db()
        self.assertEqual(up_not_started.status, "in_progress")
        self.assertIsNotNone(up_not_started.started_at) # Check if perform_update logic sets it


class ProjectSubmissionViewSetTests(ProjectsViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUpTestData()
        # Ensure user_project_user1 is in a submittable state for some tests
        self.user_project_user1.status = 'in_progress'
        self.user_project_user1.save()

    def test_list_my_submissions_for_user_project(self):
        self.authenticate_client_with_jwt(self.user1)
        # submission_user1 was created for user_project_user1 in setUpTestData
        # After that submission, user_project_user1 status became 'submitted'
        # And after assessment, it became 'completed'. Let's reset for this test.
        self.user_project_user1.status = 'submitted' # Simulate it's just submitted
        self.user_project_user1.save()
        # Re-create submission to ensure it's linked to the current state
        ProjectSubmission.objects.filter(user_project=self.user_project_user1).delete() # Clear old
        submission = ProjectSubmission.objects.create(user_project=self.user_project_user1, submission_notes="Test list")


        url = reverse('projects:userproject-submission-list', kwargs={'user_project_pk': self.user_project_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(submission.id))

    def test_create_submission_success(self):
        self.authenticate_client_with_jwt(self.user1)
        self.user_project_user1.status = 'in_progress' # Ensure it's submittable
        self.user_project_user1.save()

        url = reverse('projects:userproject-submission-list', kwargs={'user_project_pk': self.user_project_user1.pk})
        data = {
            # user_project_id is inferred from URL or should be passed if not nested create
            # The serializer expects user_project_id in data if not a nested create
            # For nested create, view's perform_create handles linking.
            # Let's assume the view handles linking, so we don't pass user_project_id in data here.
            # However, our ProjectSubmissionSerializer has user_project_id as write_only=True
            # So, we should provide it, or the view should inject it.
            # The ViewSet's perform_create is designed for non-nested, so we need to test the nested behavior.
            # The current perform_create in ProjectSubmissionViewSet expects user_project in validated_data
            # which means the serializer must provide it.
            "user_project_id": str(self.user_project_user1.id), # Required by serializer
            "submission_notes": "My awesome new submission",
            "submission_artifacts": {"repo": "github.com/mynewsub"}
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(ProjectSubmission.objects.filter(user_project=self.user_project_user1, submission_notes="My awesome new submission").exists())
        self.user_project_user1.refresh_from_db()
        self.assertEqual(self.user_project_user1.status, 'submitted') # Model's save() updates this

    def test_create_submission_for_other_user_project_forbidden(self):
        self.authenticate_client_with_jwt(self.user2) # user2
        url = reverse('projects:userproject-submission-list', kwargs={'user_project_pk': self.user_project_user1.pk}) # user1's project
        data = {"user_project_id": str(self.user_project_user1.id), "submission_notes": "Trying to hack"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanSubmitToUserProject

    def test_create_submission_project_not_in_submittable_state(self):
        self.user_project_user1.status = 'completed' # Not submittable
        self.user_project_user1.save()
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('projects:userproject-submission-list', kwargs={'user_project_pk': self.user_project_user1.pk})
        data = {"user_project_id": str(self.user_project_user1.id), "submission_notes": "Too late"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Serializer validation
        self.assertIn("not in a submittable state", str(response.data))


class ProjectAssessmentViewSetTests(ProjectsViewTestDataMixin, APITestCase):
    def test_retrieve_own_assessment(self):
        self.authenticate_client_with_jwt(self.user1)
        # URL: /api/projects/user-projects/{user_project_pk}/submissions/{submission_pk}/assessment/{assessment_pk}/
        # Or if accessing directly via /api/projects/project-assessments/{pk}/
        url = reverse('projects:project-assessment-detail', kwargs={'pk': self.assessment_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], float(self.assessment_user1.score))

    def test_retrieve_other_user_assessment_forbidden(self):
        self.authenticate_client_with_jwt(self.user2) # User2 trying to access User1's assessment
        url = reverse('projects:project-assessment-detail', kwargs={'pk': self.assessment_user1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAssessmentViewerOrAdmin

    def test_create_assessment_by_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user) # Admin can assess
        # Create a new submission for assessment
        up_new = UserProject.objects.create(user=self.user2, project=self.project_def1_published, status='submitted')
        sub_new = ProjectSubmission.objects.create(user_project=up_new, submission_notes="Needs admin assessment")

        url = reverse('projects:project-assessment-list') # Using top-level for create
        data = {
            "submission_id": str(sub_new.id),
            "assessed_by_ai": False,
            # "manual_assessor_id": self.admin_user.id, # Serializer sets this from context if staff
            "score": 95.0,
            "passed": True,
            "feedback_summary": "Admin assessed: Excellent!"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        assessment = ProjectAssessment.objects.get(submission=sub_new)
        self.assertEqual(assessment.manual_assessor, self.admin_user)
        self.assertTrue(assessment.passed)
        up_new.refresh_from_db()
        self.assertEqual(up_new.status, 'completed')

    def test_create_assessment_by_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.user1) # Regular user cannot create assessment
        url = reverse('projects:project-assessment-list')
        data = {"submission_id": str(self.submission_user1.id), "score": 100, "passed": True}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanManageProjectAssessment

    def test_submit_ai_assessment_action_success(self):
        self.authenticate_client_with_jwt(self.admin_user) # Action requires CanManageProjectAssessment (staff)
        
        # Create a submission that needs AI assessment
        up_for_ai = UserProject.objects.create(user=self.user2, project=self.project_def3_other_instructor, status='submitted')
        sub_for_ai = ProjectSubmission.objects.create(user_project=up_for_ai, submission_notes="Ready for AI")

        url = reverse('projects:project-assessment-submit-ai-assessment')
        data = {
            "submission_id": str(sub_for_ai.id),
            # assessed_by_ai and assessor_ai_agent_name can be set by view/serializer if not in payload
            "assessor_ai_agent_name": "TestAI v1",
            "score": 70.0,
            "passed": True, # AI determines this
            "feedback_summary": "AI: Meets minimum criteria.",
            "detailed_feedback": {"checks": {"style": "ok", "logic": "basic_pass"}}
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        assessment = ProjectAssessment.objects.get(submission=sub_for_ai)
        self.assertTrue(assessment.assessed_by_ai)
        self.assertEqual(assessment.assessor_ai_agent_name, "TestAI v1")
        self.assertTrue(assessment.passed)
        up_for_ai.refresh_from_db()
        self.assertEqual(up_for_ai.status, 'completed')

# TODO:
# - Test nested routes for submissions and assessments more thoroughly.
# - Test all update/delete operations for all ViewSets with correct permissions.
# - Test filtering, searching, ordering for ProjectViewSet.
# - Test error responses for invalid data in POST/PUT/PATCH.
