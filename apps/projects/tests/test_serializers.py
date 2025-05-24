from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from uuid import uuid4

from rest_framework.test import APIRequestFactory # For providing request context
from rest_framework.exceptions import ValidationError

from apps.projects.models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment
)
from apps.projects.serializers import (
    ProjectTagSerializer,
    ProjectListSerializer, ProjectDetailSerializer,
    UserProjectListSerializer, UserProjectDetailSerializer,
    ProjectSubmissionSerializer,
    ProjectAssessmentSerializer,
    SimpleUserSerializer # Assuming this is defined in projects.serializers or imported
)

User = get_user_model()

# Test Data Setup Mixin (adapted for serializer tests)
class ProjectsSerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(
            username='projser_user1', email='projser_user1@example.com',
            password='password123', full_name='ProjSer User One'
        )
        cls.instructor_user = User.objects.create_user(
            username='projser_instructor', email='projser_instructor@example.com',
            password='password123', full_name='ProjSer Instructor', is_staff=True
        )

        cls.tag_react = ProjectTag.objects.create(name='React', slug='react')
        cls.tag_nodejs = ProjectTag.objects.create(name='Node.js', slug='nodejs')

        cls.project_def_published = Project.objects.create(
            title='E-commerce Frontend', slug='ecommerce-frontend',
            description='Build a responsive frontend for an e-commerce site.',
            difficulty_level='intermediate',
            estimated_duration_hours=20,
            learning_outcomes={'features': ['Product display', 'Shopping cart']},
            is_published=True,
            created_by=cls.instructor_user
        )
        cls.project_def_published.technologies_used.add(cls.tag_react)

        cls.project_def_unpublished = Project.objects.create(
            title='Internal Dashboard API', slug='internal-dashboard-api',
            description='API for an internal dashboard.',
            difficulty_level='advanced',
            is_published=False, # Unpublished
            created_by=cls.instructor_user
        )
        cls.project_def_unpublished.technologies_used.add(cls.tag_nodejs)


        cls.user_project1 = UserProject.objects.create(
            user=cls.user1,
            project=cls.project_def_published,
            status='in_progress',
            started_at=timezone.now(),
            repository_url='https://github.com/user1/ecomm-frontend'
        )

        cls.submission1_user_project1 = ProjectSubmission.objects.create(
            user_project=cls.user_project1,
            submission_notes="Initial submission with basic layout.",
            submission_artifacts={'repository_url': cls.user_project1.repository_url, 'commit_hash': 'abc1234'}
        )
        # user_project1 status should be 'submitted' now

        cls.assessment1_sub1 = ProjectAssessment.objects.create(
            submission=cls.submission1_user_project1,
            assessed_by_ai=True,
            assessor_ai_agent_name="AI Assessor v2.0",
            score=75.0,
            passed=False, # Let's say it failed initially
            feedback_summary="Good start, but cart functionality is missing.",
            detailed_feedback={'missing_features': ['shopping_cart_add']}
        )
        # user_project1 status should be 'failed' now


        # For providing request context to serializers
        cls.factory = APIRequestFactory()
        cls.request_user1 = cls.factory.get('/fake-endpoint')
        cls.request_user1.user = cls.user1

        cls.request_instructor = cls.factory.get('/fake-endpoint')
        cls.request_instructor.user = cls.instructor_user


class ProjectTagSerializerTests(ProjectsSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = ProjectTagSerializer(instance=self.tag_react)
        data = serializer.data
        self.assertEqual(data['name'], self.tag_react.name)
        self.assertEqual(data['slug'], self.tag_react.slug)
        self.assertIn('id', data)

    def test_deserialization_create_valid(self):
        data = {'name': 'New Tag Vue', 'slug': 'vue'}
        serializer = ProjectTagSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        tag = serializer.save()
        self.assertEqual(tag.name, 'New Tag Vue')

class ProjectSerializersTests(ProjectsSerializerTestDataMixin, TestCase):
    def test_project_list_serializer_output(self):
        # Note: ProjectListSerializer in projects_serializers_py_refined does not have short_description directly
        # It uses get_short_description or assumes a field. Let's assume description for now.
        serializer = ProjectListSerializer(instance=self.project_def_published)
        data = serializer.data
        self.assertEqual(data['title'], self.project_def_published.title)
        self.assertEqual(data['difficulty_level_display'], self.project_def_published.get_difficulty_level_display())
        self.assertEqual(len(data['technologies_used']), 1)
        self.assertEqual(data['technologies_used'][0]['name'], self.tag_react.name)

    def test_project_detail_serializer_read(self):
        serializer = ProjectDetailSerializer(instance=self.project_def_published, context={'request': self.request_instructor})
        data = serializer.data
        self.assertEqual(data['title'], self.project_def_published.title)
        self.assertEqual(data['description'], self.project_def_published.description)
        self.assertEqual(data['learning_outcomes']['features'][0], 'Product display')
        self.assertEqual(data['created_by']['username'], self.instructor_user.username)
        self.assertEqual(len(data['technologies_used']), 1)

    def test_project_detail_serializer_create(self):
        data = {
            "title": "New Microservice Project",
            # "slug": "new-microservice", # Test auto-slug generation
            "description": "Build a scalable microservice.",
            "difficulty_level": "advanced",
            "estimated_duration_hours": 30,
            "learning_outcomes": {"apis": ["gRPC", "REST"]},
            "prerequisites": {"languages": ["Go", "Python"]},
            "guidelines": {"deployment": "Kubernetes"},
            "resources": [{"link": "example.com/grpc"}],
            "is_published": False,
            "ai_generated": True,
            "ai_generation_prompt": "Create an advanced microservice project.",
            "technology_tag_ids": [self.tag_api.id, self.tag_python.id]
        }
        serializer = ProjectDetailSerializer(data=data, context={'request': self.request_instructor})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        project = serializer.save() # created_by is set from context
        self.assertEqual(project.title, "New Microservice Project")
        self.assertEqual(project.created_by, self.instructor_user)
        self.assertTrue(project.ai_generated)
        self.assertEqual(project.technologies_used.count(), 2)
        self.assertIn(self.tag_api, project.technologies_used.all())
        self.assertTrue(Project.objects.filter(slug=slugify("New Microservice Project")).exists())

    def test_project_detail_serializer_update_with_tags(self):
        data = {
            "title": "Updated E-commerce Frontend Advanced",
            "difficulty_level": "advanced",
            "technology_tag_ids": [self.tag_nodejs.id] # Change tags
        }
        serializer = ProjectDetailSerializer(instance=self.project_def_published, data=data, partial=True, context={'request': self.request_instructor})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        project = serializer.save()
        self.assertEqual(project.title, "Updated E-commerce Frontend Advanced")
        self.assertEqual(project.technologies_used.count(), 1)
        self.assertIn(self.tag_nodejs, project.technologies_used.all())
        self.assertNotIn(self.tag_react, project.technologies_used.all())


class UserProjectSerializersTests(ProjectsSerializerTestDataMixin, TestCase):
    def test_user_project_list_serializer_output(self):
        serializer = UserProjectListSerializer(instance=self.user_project1)
        data = serializer.data
        self.assertEqual(data['project_title'], self.project_def_published.title)
        self.assertEqual(data['status_display'], self.user_project1.get_status_display())
        self.assertEqual(data['user_email'], self.user1.email)

    def test_user_project_detail_serializer_read(self):
        serializer = UserProjectDetailSerializer(instance=self.user_project1, context={'request': self.request_user1})
        data = serializer.data
        self.assertEqual(data['user']['email'], self.user1.email)
        self.assertEqual(data['project']['title'], self.project_def_published.title)
        self.assertEqual(data['status'], self.user_project1.status)
        self.assertEqual(data['repository_url'], self.user_project1.repository_url)

    def test_user_project_detail_serializer_create_valid(self):
        # User1 tries to start the unpublished project (should fail project_id validation)
        data_unpublished = {"project_id": str(self.project_def_unpublished.id)}
        serializer_unpublished = UserProjectDetailSerializer(data=data_unpublished, context={'request': self.request_user1})
        self.assertFalse(serializer_unpublished.is_valid())
        self.assertIn('project_id', serializer_unpublished.errors)
        self.assertIn("Cannot start a project that is not published.", str(serializer_unpublished.errors['project_id']))

        # User2 starts a new project (project_def_published)
        data_new = {"project_id": str(self.project_def_published.id), "status": "in_progress"}
        request_user2 = self.factory.get('/fake-endpoint')
        request_user2.user = self.user2
        serializer_new = UserProjectDetailSerializer(data=data_new, context={'request': request_user2})
        self.assertTrue(serializer_new.is_valid(), serializer_new.errors)
        user_project = serializer_new.save() # user is set from context
        self.assertEqual(user_project.user, self.user2)
        self.assertEqual(user_project.project, self.project_def_published)
        self.assertEqual(user_project.status, 'in_progress')
        self.assertIsNotNone(user_project.started_at)

    def test_user_project_detail_serializer_create_duplicate_fails(self):
        # user1 already has user_project1 for project_def_published
        data = {"project_id": str(self.project_def_published.id)}
        serializer = UserProjectDetailSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn("You have already started this project.", str(serializer.errors['non_field_errors']))

    def test_user_project_detail_serializer_update_urls(self):
        data = {
            "repository_url": "https://gitlab.com/user1/new-repo",
            "live_url": "https://user1-project.dev"
        }
        serializer = UserProjectDetailSerializer(instance=self.user_project1, data=data, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user_project = serializer.save()
        self.assertEqual(user_project.repository_url, "https://gitlab.com/user1/new-repo")
        self.assertEqual(user_project.live_url, "https://user1-project.dev")


class ProjectSubmissionSerializerTests(ProjectsSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = ProjectSubmissionSerializer(instance=self.submission1_user_project1)
        data = serializer.data
        self.assertEqual(data['id'], str(self.submission1_user_project1.id))
        self.assertEqual(data['user_project_title'], self.user_project1.project.title)
        self.assertEqual(data['user_email'], self.user1.email)
        self.assertEqual(data['submission_version'], 1)
        self.assertEqual(data['submission_artifacts']['commit_hash'], 'abc1234')

    def test_deserialization_create_valid(self):
        # UserProject1 status is 'failed' after initial assessment, allowing re-submission
        self.user_project1.status = 'failed'
        self.user_project1.save()

        data = {
            "user_project_id": str(self.user_project1.id),
            "submission_notes": "Second attempt with fixes.",
            "submission_artifacts": {"repository_url": "https://github.com/user1/ecomm-v2", "live_demo_url": "live.app/v2"}
        }
        serializer = ProjectSubmissionSerializer(data=data, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        submission = serializer.save() # user_project is set from validated_data
        self.assertEqual(submission.user_project, self.user_project1)
        self.assertEqual(submission.submission_notes, "Second attempt with fixes.")
        self.assertEqual(submission.submission_version, 2) # Should be version 2
        self.user_project1.refresh_from_db()
        self.assertEqual(self.user_project1.status, 'submitted') # Status updated by model save

    def test_deserialization_create_invalid_user_project_owner(self):
        request_user2 = self.factory.get('/fake-endpoint')
        request_user2.user = self.user2 # user2 trying to submit for user1's project
        data = {"user_project_id": str(self.user_project1.id), "submission_notes": "Trying to submit."}
        serializer = ProjectSubmissionSerializer(data=data, context={'request': request_user2})
        self.assertFalse(serializer.is_valid())
        self.assertIn('user_project_id', serializer.errors) # Validation is on user_project_id field
        self.assertIn("You can only submit to your own projects.", str(serializer.errors['user_project_id']))

    def test_deserialization_create_invalid_user_project_status(self):
        self.user_project1.status = 'completed' # Cannot submit to a completed project
        self.user_project1.save()
        data = {"user_project_id": str(self.user_project1.id), "submission_notes": "Late submission."}
        serializer = ProjectSubmissionSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('user_project_id', serializer.errors)
        self.assertIn("Project is not in a submittable state.", str(serializer.errors['user_project_id']))


class ProjectAssessmentSerializerTests(ProjectsSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = ProjectAssessmentSerializer(instance=self.assessment1_sub1)
        data = serializer.data
        self.assertEqual(data['id'], str(self.assessment1_sub1.id))
        self.assertTrue(data['assessed_by_ai'])
        self.assertEqual(data['assessor_ai_agent_name'], "AI Assessor v2.0")
        self.assertEqual(data['score'], 75.0)
        self.assertFalse(data['passed'])
        self.assertEqual(data['submission_details']['submission_id'], str(self.submission1_user_project1.id))
        self.assertEqual(data['assessed_by_display'], "AI: AI Assessor v2.0")

    def test_deserialization_create_valid_ai(self):
        # Create a new submission for user2
        user_project2 = UserProject.objects.create(user=self.user2, project=self.project_def_published, status='in_progress')
        user_project2.status = 'submitted' # Manually set for test, submission create would do this
        user_project2.save()
        submission2_user_project2 = ProjectSubmission.objects.create(user_project=user_project2, submission_notes="User 2 submission")

        data = {
            "submission_id": str(submission2_user_project2.id),
            "assessed_by_ai": True,
            "assessor_ai_agent_name": "GraderBot3000",
            "score": 92.5,
            "passed": True,
            "feedback_summary": "Excellent work!",
            "detailed_feedback": {"strengths": ["Code clarity", "Functionality"]}
        }
        serializer = ProjectAssessmentSerializer(data=data, context={'request': self.request_instructor}) # Admin/Instructor context
        self.assertTrue(serializer.is_valid(), serializer.errors)
        assessment = serializer.save()
        self.assertEqual(assessment.submission, submission2_user_project2)
        self.assertTrue(assessment.passed)
        self.assertEqual(assessment.score, 92.5)
        user_project2.refresh_from_db()
        self.assertEqual(user_project2.status, 'completed') # Updated by model save

    def test_deserialization_create_manual_assessor_from_context(self):
        data = { # Assessed by instructor_user from context
            "submission_id": str(self.submission1_user_project1.id), # submission1 already assessed, let's make a new one
            "assessed_by_ai": False, # Manual assessment
            "score": 88.0,
            "passed": True,
            "feedback_summary": "Manually reviewed, looks good."
        }
        # Create a new submission to assess
        self.user_project1.status = 'failed' # Allow re-submission
        self.user_project1.save()
        new_submission = ProjectSubmission.objects.create(user_project=self.user_project1, submission_notes="Resubmission")
        data["submission_id"] = str(new_submission.id)


        serializer = ProjectAssessmentSerializer(data=data, context={'request': self.request_instructor})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        assessment = serializer.save()
        self.assertEqual(assessment.manual_assessor, self.instructor_user)
        self.assertFalse(assessment.assessed_by_ai)
