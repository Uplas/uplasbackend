from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from django.utils.text import slugify
from decimal import Decimal # Though not directly used in project models, good practice if prices were involved

from apps.projects.models import (
    ProjectTag, Project, UserProject, ProjectSubmission, ProjectAssessment,
    PROJECT_DIFFICULTY_CHOICES, USER_PROJECT_STATUS_CHOICES
)
# Ensure settings are configured for tests, especially AUTH_USER_MODEL
from django.conf import settings

User = get_user_model()

class ProjectsModelTestDataMixin:
    """
    Mixin to provide common setup data for project-related model tests.
    """
    @classmethod
    def setUpTestData(cls):
        # Create users
        cls.user1 = User.objects.create_user(
            username='project_user1',
            email='projectuser1@example.com',
            password='password123',
            full_name='Project User One'
        )
        cls.user2 = User.objects.create_user(
            username='project_user2',
            email='projectuser2@example.com',
            password='password123',
            full_name='Project User Two'
        )
        cls.instructor_user = User.objects.create_user(
            username='project_instructor',
            email='projectinstructor@example.com',
            password='password123',
            full_name='Project Instructor',
            is_staff=True # Assuming instructors might be staff, or have a specific role
        )

        # Create Project Tags
        cls.tag_python = ProjectTag.objects.create(name='Python', slug='python')
        cls.tag_django = ProjectTag.objects.create(name='Django', slug='django')
        cls.tag_api = ProjectTag.objects.create(name='API Development', slug='api-development')

        # Create a Project Definition
        cls.project_def1 = Project.objects.create(
            title='Build a To-Do List API',
            slug='todo-list-api',
            description='A project to build a simple RESTful API for managing tasks.',
            difficulty_level='intermediate',
            estimated_duration_hours=10,
            learning_outcomes={'skills': ['REST API design', 'CRUD operations', 'Django REST framework']},
            prerequisites={'knowledge': ['Basic Python', 'Django fundamentals']},
            guidelines={'requirements': ['User authentication', 'Task creation, listing, update, deletion']},
            resources=[{'title': 'DRF Docs', 'url': 'https://www.django-rest-framework.org/'}],
            is_published=True,
            created_by=cls.instructor_user,
            ai_generated=False
        )
        cls.project_def1.technologies_used.add(cls.tag_python, cls.tag_django, cls.tag_api)

        cls.project_def_unpublished = Project.objects.create(
            title='Advanced Data Analysis with Pandas',
            slug='advanced-pandas',
            description='Explore complex data manipulations.',
            difficulty_level='advanced',
            is_published=False, # Unpublished
            created_by=cls.instructor_user
        )

        # Create a UserProject instance for user1
        cls.user_project1 = UserProject.objects.create(
            user=cls.user1,
            project=cls.project_def1,
            status='not_started'
        )


class ProjectTagModelTests(ProjectsModelTestDataMixin, TestCase):
    def test_project_tag_creation(self):
        self.assertEqual(self.tag_python.name, 'Python')
        self.assertEqual(self.tag_python.slug, 'python')
        self.assertEqual(str(self.tag_python), 'Python')
        self.assertIsNotNone(self.tag_python.created_at)

    def test_project_tag_name_uniqueness(self):
        with self.assertRaises(IntegrityError):
            ProjectTag.objects.create(name='Python', slug='python-new')

    def test_project_tag_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            ProjectTag.objects.create(name='Python New', slug='python')


class ProjectModelTests(ProjectsModelTestDataMixin, TestCase):
    def test_project_definition_creation(self):
        self.assertEqual(self.project_def1.title, 'Build a To-Do List API')
        self.assertEqual(self.project_def1.created_by, self.instructor_user)
        self.assertTrue(self.project_def1.is_published)
        self.assertEqual(self.project_def1.technologies_used.count(), 3)
        self.assertIn(self.tag_django, self.project_def1.technologies_used.all())
        self.assertEqual(str(self.project_def1), 'Build a To-Do List API')

    def test_project_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Project.objects.create(title='Another To-Do API', slug='todo-list-api', description='test')


class UserProjectModelTests(ProjectsModelTestDataMixin, TestCase):
    def test_user_project_creation(self):
        self.assertEqual(self.user_project1.user, self.user1)
        self.assertEqual(self.user_project1.project, self.project_def1)
        self.assertEqual(self.user_project1.status, 'not_started')
        self.assertIsNone(self.user_project1.started_at)
        expected_str = f"{self.user1.email}'s work on '{self.project_def1.title}' (Not Started)"
        self.assertEqual(str(self.user_project1), expected_str)

    def test_user_project_uniqueness_user_project_definition(self):
        with self.assertRaises(IntegrityError):
            UserProject.objects.create(user=self.user1, project=self.project_def1)

    def test_user_project_save_sets_started_at(self):
        self.user_project1.status = 'in_progress'
        self.user_project1.save()
        self.user_project1.refresh_from_db()
        self.assertIsNotNone(self.user_project1.started_at)
        first_started_at = self.user_project1.started_at

        # Saving again without changing status should not change started_at
        self.user_project1.repository_url = "https://github.com/test/repo"
        self.user_project1.save()
        self.user_project1.refresh_from_db()
        self.assertEqual(self.user_project1.started_at, first_started_at)

    def test_user_project_status_choices(self):
        self.user_project1.status = 'completed'
        self.user_project1.save()
        self.assertEqual(self.user_project1.get_status_display(), 'Completed Successfully')


class ProjectSubmissionModelTests(ProjectsModelTestDataMixin, TestCase):
    def setUp(self):
        # Start the project first
        self.user_project1.status = 'in_progress'
        self.user_project1.save()

    def test_project_submission_creation(self):
        submission = ProjectSubmission.objects.create(
            user_project=self.user_project1,
            submission_notes="My first attempt at the To-Do API.",
            submission_artifacts={'repository_url': 'https://github.com/user1/todo-api-v1'}
        )
        self.assertEqual(submission.user_project, self.user_project1)
        self.assertEqual(submission.submission_version, 1) # First submission
        self.assertIn('My first attempt', submission.submission_notes)
        self.assertIsNotNone(submission.submitted_at)
        expected_str_part = f"Submission for '{self.project_def1.title}' by {self.user1.email}"
        self.assertIn(expected_str_part, str(submission))

        # Test UserProject status update
        self.user_project1.refresh_from_db()
        self.assertEqual(self.user_project1.status, 'submitted')

    def test_project_submission_versioning(self):
        ProjectSubmission.objects.create(user_project=self.user_project1, submission_version=1) # Simulate first one
        
        # To correctly test the auto-increment, we need the model's save method to run
        # without explicitly setting submission_version in the create call here if it's auto-set
        # The model's save method sets version based on latest. Let's ensure user_project is 'submitted'
        self.user_project1.status = 'submitted' # Or 'failed' to allow resubmission
        self.user_project1.save()

        submission2 = ProjectSubmission.objects.create(
            user_project=self.user_project1,
            submission_notes="Second version with updates."
        )
        self.assertEqual(submission2.submission_version, 2) # Assuming first was 1

        submission3 = ProjectSubmission.objects.create(
            user_project=self.user_project1,
            submission_notes="Third version."
        )
        self.assertEqual(submission3.submission_version, 3)


class ProjectAssessmentModelTests(ProjectsModelTestDataMixin, TestCase):
    def setUp(self):
        self.user_project1.status = 'in_progress' # Start project
        self.user_project1.save()
        self.submission1 = ProjectSubmission.objects.create(
            user_project=self.user_project1,
            submission_notes="Ready for assessment."
        )
        # UserProject status should now be 'submitted' due to submission save method

    def test_project_assessment_creation_passed(self):
        assessment = ProjectAssessment.objects.create(
            submission=self.submission1,
            assessed_by_ai=True,
            assessor_ai_agent_name='AI Assessor v1.0',
            score=85.0,
            passed=True,
            feedback_summary="Good work, all core requirements met.",
            detailed_feedback={'criteria': {'auth': 'passed', 'crud': 'passed'}, 'notes': 'Well done.'}
        )
        self.assertEqual(assessment.submission, self.submission1)
        self.assertTrue(assessment.assessed_by_ai)
        self.assertEqual(assessment.score, 85.0)
        self.assertTrue(assessment.passed)
        self.assertIsNotNone(assessment.assessed_at)
        expected_str_part = f"Assessment for '{self.project_def1.title}' (Score: 85.0 - Passed)"
        self.assertIn(expected_str_part, str(assessment))

        # Test UserProject status update to 'completed'
        self.user_project1.refresh_from_db()
        self.assertEqual(self.user_project1.status, 'completed')
        self.assertIsNotNone(self.user_project1.completed_at)

    def test_project_assessment_creation_failed(self):
        assessment = ProjectAssessment.objects.create(
            submission=self.submission1,
            assessed_by_ai=True,
            score=60.0,
            passed=False,
            feedback_summary="Needs improvement in API security.",
            detailed_feedback={'criteria': {'auth': 'failed'}, 'improvement_points': ['Review token handling.']}
        )
        self.assertFalse(assessment.passed)

        # Test UserProject status update to 'failed'
        self.user_project1.refresh_from_db()
        self.assertEqual(self.user_project1.status, 'failed')
        self.assertIsNone(self.user_project1.completed_at) # Should not be set if failed

    def test_project_assessment_manual_assessor(self):
        assessment = ProjectAssessment.objects.create(
            submission=self.submission1,
            assessed_by_ai=False,
            manual_assessor=self.instructor_user,
            score=90.0,
            passed=True
        )
        self.assertFalse(assessment.assessed_by_ai)
        self.assertEqual(assessment.manual_assessor, self.instructor_user)

# Add more tests for:
# - Constraints like JSONField schema validation (if enforced outside model, e.g. in serializers).
# - More complex interactions between model save methods if any.
# - Behavior of on_delete for ForeignKey and ManyToManyField relationships.
