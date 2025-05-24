from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
from django.db import IntegrityError
from decimal import Decimal

from apps.courses.models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress,
    QuizAttempt, UserTopicAttemptAnswer
)
# Ensure settings are configured for tests, especially AUTH_USER_MODEL and CURRENCY_CHOICES
from django.conf import settings

User = get_user_model()

class CourseModelTestDataMixin:
    """
    Mixin to provide common setup data for course-related model tests.
    """
    @classmethod
    def setUpTestData(cls):
        # Create a user (instructor)
        cls.instructor_user = User.objects.create_user(
            username='testinstructor',
            email='instructor@example.com',
            password='password123',
            full_name='Test Instructor',
            is_instructor=True # Assuming your custom User model has this
        )

        # Create another user (student)
        cls.student_user = User.objects.create_user(
            username='teststudent',
            email='student@example.com',
            password='password123',
            full_name='Test Student'
        )

        # Create a Category
        cls.category1 = Category.objects.create(
            name='Programming',
            slug='programming',
            description='Courses about programming languages and concepts.'
        )
        cls.category2 = Category.objects.create(
            name='Data Science',
            slug='data-science'
        )

        # Create a Course
        cls.course1 = Course.objects.create(
            title='Introduction to Python',
            slug='intro-to-python',
            instructor=cls.instructor_user,
            category=cls.category1,
            short_description='Learn the basics of Python programming.',
            long_description='A comprehensive course for beginners.',
            language='en',
            level='beginner',
            price=Decimal('49.99'),
            currency='USD',
            is_published=True,
            supports_ai_tutor=True
        )

        cls.course2_free = Course.objects.create(
            title='Basic Web Development',
            slug='basic-web-dev',
            instructor=cls.instructor_user,
            category=cls.category1,
            short_description='Learn HTML, CSS, JS.',
            price=Decimal('0.00'),
            is_free=True,
            is_published=True
        )

        # Create a Module for course1
        cls.module1_c1 = Module.objects.create(
            course=cls.course1,
            title='Getting Started',
            order=1,
            description='Introduction and setup.'
        )
        cls.module2_c1 = Module.objects.create(
            course=cls.course1,
            title='Variables and Data Types',
            order=2
        )

        # Create a Topic for module1_c1
        cls.topic1_m1_c1 = Topic.objects.create(
            module=cls.module1_c1,
            title='What is Python?',
            slug='what-is-python',
            content={'type': 'text', 'text_content': 'Python is a versatile language...'},
            estimated_duration_minutes=10,
            order=1,
            is_previewable=True
        )
        cls.topic2_m1_c1 = Topic.objects.create(
            module=cls.module1_c1,
            title='Setting up Your Environment',
            slug='setting-up-environment',
            content={'type': 'video', 'video_url': 'https://example.com/setup.mp4'},
            estimated_duration_minutes=15,
            order=2
        )
        # Topic with specific AI support settings
        cls.topic3_m2_c1 = Topic.objects.create(
            module=cls.module2_c1,
            title='Understanding Variables',
            slug='understanding-variables',
            content={'type': 'text', 'text_content': 'Variables store data...'},
            estimated_duration_minutes=20,
            order=1,
            supports_tts=False, # Override course setting
            supports_ttv=True
        )


class CategoryModelTests(CourseModelTestDataMixin, TestCase):
    def test_category_creation(self):
        self.assertEqual(self.category1.name, 'Programming')
        self.assertEqual(self.category1.slug, 'programming')
        self.assertEqual(str(self.category1), 'Programming')
        self.assertTrue(self.category1.created_at is not None)

    def test_category_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Category.objects.create(name='Another Programming', slug='programming')

    def test_category_ordering(self):
        categories = Category.objects.all()
        self.assertEqual(categories[0], self.category2) # 'Data Science' before 'Programming' alphabetically
        self.assertEqual(categories[1], self.category1)


class CourseModelTests(CourseModelTestDataMixin, TestCase):
    def test_course_creation(self):
        self.assertEqual(self.course1.title, 'Introduction to Python')
        self.assertEqual(self.course1.instructor, self.instructor_user)
        self.assertEqual(self.course1.category, self.category1)
        self.assertEqual(str(self.course1), 'Introduction to Python')
        self.assertTrue(self.course1.is_published)
        self.assertIsNotNone(self.course1.published_at) # Set by save method

    def test_course_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Course.objects.create(title='Duplicate Slug Course', slug='intro-to-python', instructor=self.instructor_user, category=self.category1, short_description='test')

    def test_course_publish_unpublish_logic(self):
        course = Course.objects.create(title='Test Publish', slug='test-publish', instructor=self.instructor_user, category=self.category1, short_description='test')
        self.assertFalse(course.is_published)
        self.assertIsNone(course.published_at)

        course.is_published = True
        course.save()
        self.assertTrue(course.is_published)
        self.assertIsNotNone(course.published_at)
        first_published_at = course.published_at

        # Saving again while published should not change published_at
        course.title = "Test Publish Updated"
        course.save()
        self.assertEqual(course.published_at, first_published_at)

        course.is_published = False
        course.save()
        self.assertFalse(course.is_published)
        self.assertIsNone(course.published_at)

    def test_update_total_duration_signal_on_topic_save(self):
        initial_duration = self.course1.total_duration_minutes
        # Topic save signal should update this. Let's verify.
        # The signal is on Topic.save(), so creating/saving a topic for course1 should trigger it.
        # self.topic1_m1_c1 and self.topic2_m1_c1 were created in setUpTestData
        # Their durations are 10 and 15.
        self.course1.refresh_from_db() # Ensure we have the latest from db after setup
        expected_duration = self.topic1_m1_c1.estimated_duration_minutes + \
                              self.topic2_m1_c1.estimated_duration_minutes + \
                              self.topic3_m2_c1.estimated_duration_minutes
        self.assertEqual(self.course1.total_duration_minutes, expected_duration)

        # Add another topic to module1_c1
        new_topic = Topic.objects.create(
            module=self.module1_c1,
            title='New Topic Duration Test',
            slug='new-topic-duration',
            content={'type': 'text'},
            estimated_duration_minutes=5,
            order=3
        )
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_duration_minutes, expected_duration + 5)

        # Delete a topic
        new_topic.delete() # This should also trigger the update
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_duration_minutes, expected_duration)


class ModuleModelTests(CourseModelTestDataMixin, TestCase):
    def test_module_creation(self):
        self.assertEqual(self.module1_c1.title, 'Getting Started')
        self.assertEqual(self.module1_c1.course, self.course1)
        self.assertEqual(self.module1_c1.order, 1)
        self.assertEqual(str(self.module1_c1), f"{self.course1.title} - Module 1: Getting Started")

    def test_module_order_uniqueness_within_course(self):
        with self.assertRaises(IntegrityError):
            Module.objects.create(course=self.course1, title='Duplicate Order Module', order=1)

    def test_module_ordering(self):
        modules = Module.objects.filter(course=self.course1)
        self.assertEqual(modules[0], self.module1_c1)
        self.assertEqual(modules[1], self.module2_c1)


class TopicModelTests(CourseModelTestDataMixin, TestCase):
    def test_topic_creation(self):
        self.assertEqual(self.topic1_m1_c1.title, 'What is Python?')
        self.assertEqual(self.topic1_m1_c1.module, self.module1_c1)
        self.assertEqual(self.topic1_m1_c1.order, 1)
        self.assertTrue(self.topic1_m1_c1.is_previewable)
        self.assertEqual(str(self.topic1_m1_c1), f"{self.module1_c1.title} - Topic 1: What is Python?")

    def test_topic_slug_uniqueness(self):
        with self.assertRaises(IntegrityError): # Slug must be globally unique for Topic
            Topic.objects.create(module=self.module2_c1, title='Another What is Python', slug='what-is-python', order=2, content={})

    def test_topic_order_uniqueness_within_module(self):
        with self.assertRaises(IntegrityError):
            Topic.objects.create(module=self.module1_c1, title='Duplicate Order Topic', slug='duplicate-order-topic', order=1, content={})

    def test_topic_ai_support_inheritance(self):
        # course1.supports_ai_tutor = True
        # topic1_m1_c1.supports_ai_tutor = None (should inherit True)
        self.assertTrue(self.topic1_m1_c1.get_supports_ai_tutor())

        # topic3_m2_c1.supports_tts = False (should override course setting if any)
        self.assertFalse(self.topic3_m2_c1.get_supports_tts())
        # topic3_m2_c1.supports_ttv = True
        self.assertTrue(self.topic3_m2_c1.get_supports_ttv())

        # Test a topic where course has False and topic has None
        self.course1.supports_tts = False
        self.course1.save()
        self.topic1_m1_c1.supports_tts = None # Explicitly set to None for test clarity
        self.topic1_m1_c1.save()
        self.assertFalse(self.topic1_m1_c1.get_supports_tts())


class QuestionAndChoiceModelTests(CourseModelTestDataMixin, TestCase):
    def setUp(self): # Specific setup for this test class
        self.question1_t1 = Question.objects.create(
            topic=self.topic1_m1_c1,
            text="What is the primary use of Python?",
            question_type='single-choice',
            order=1,
            explanation="Python is known for its general-purpose nature."
        )
        self.choice1_q1 = Choice.objects.create(question=self.question1_t1, text="Web Development", is_correct=False, order=1)
        self.choice2_q1 = Choice.objects.create(question=self.question1_t1, text="Data Analysis", is_correct=False, order=2)
        self.choice3_q1 = Choice.objects.create(question=self.question1_t1, text="General Purpose Programming", is_correct=True, order=3)

    def test_question_creation(self):
        self.assertEqual(self.question1_t1.topic, self.topic1_m1_c1)
        self.assertIn("primary use of Python", self.question1_t1.text)
        self.assertEqual(str(self.question1_t1), f"Q1: What is the primary use of Python?... ({self.topic1_m1_c1.title})")

    def test_choice_creation(self):
        self.assertEqual(self.choice3_q1.question, self.question1_t1)
        self.assertTrue(self.choice3_q1.is_correct)
        self.assertEqual(str(self.choice3_q1), f"{self.question1_t1.text[:30]}... - Choice: {self.choice3_q1.text[:30]}...")
        self.assertEqual(self.question1_t1.choices.count(), 3)


class EnrollmentModelTests(CourseModelTestDataMixin, TestCase):
    def test_enrollment_creation(self):
        enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.assertEqual(enrollment.user, self.student_user)
        self.assertEqual(enrollment.course, self.course1)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=self.course1).exists())
        self.assertEqual(str(enrollment), f"{self.student_user.full_name} enrolled in {self.course1.title}")

    def test_enrollment_uniqueness(self):
        Enrollment.objects.create(user=self.student_user, course=self.course1)
        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(user=self.student_user, course=self.course1)

    def test_enrollment_signal_updates_course_enrollments(self):
        initial_enrollments = self.course1.total_enrollments
        enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_enrollments, initial_enrollments + 1)

        enrollment.delete()
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_enrollments, initial_enrollments)

    def test_enrollment_creates_course_progress(self):
        self.assertFalse(CourseProgress.objects.filter(user=self.student_user, course=self.course1).exists())
        enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.assertTrue(CourseProgress.objects.filter(user=self.student_user, course=self.course1, enrollment=enrollment).exists())
        
        # Test deletion of CourseProgress when enrollment is deleted (if signal is set up for this)
        # The current signal in models.py handles this.
        enrollment.delete()
        self.assertFalse(CourseProgress.objects.filter(user=self.student_user, course=self.course1).exists())


class CourseReviewModelTests(CourseModelTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData() # Call mixin's setup
        # Ensure student is enrolled to be able to review
        self.enrollment_for_review = Enrollment.objects.create(user=self.student_user, course=self.course1)

    def test_review_creation(self):
        review = CourseReview.objects.create(
            user=self.student_user,
            course=self.course1,
            rating=5,
            comment="Excellent course!"
        )
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.course, self.course1)
        self.assertEqual(str(review), f"Review for {self.course1.title} by {self.student_user.full_name} - 5 stars")

    def test_review_uniqueness_user_course(self):
        CourseReview.objects.create(user=self.student_user, course=self.course1, rating=4)
        with self.assertRaises(IntegrityError):
            CourseReview.objects.create(user=self.student_user, course=self.course1, rating=5)

    def test_review_signal_updates_course_rating(self):
        initial_avg_rating = self.course1.average_rating
        initial_total_reviews = self.course1.total_reviews

        review1 = CourseReview.objects.create(user=self.student_user, course=self.course1, rating=5)
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_reviews, initial_total_reviews + 1)
        self.assertEqual(self.course1.average_rating, 5.0) # Only one review

        # Create another user for a second review
        student2 = User.objects.create_user(username='student2', email='s2@example.com', password='pw')
        Enrollment.objects.create(user=student2, course=self.course1)
        review2 = CourseReview.objects.create(user=student2, course=self.course1, rating=3)
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_reviews, initial_total_reviews + 2)
        self.assertEqual(self.course1.average_rating, (5.0 + 3.0) / 2)

        review1.delete()
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.total_reviews, initial_total_reviews + 1)
        self.assertEqual(self.course1.average_rating, 3.0)


class ProgressModelTests(CourseModelTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData()
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        # CourseProgress should be created by enrollment signal
        self.course_progress = CourseProgress.objects.get(user=self.student_user, course=self.course1)

    def test_course_progress_creation_on_enroll(self):
        self.assertIsNotNone(self.course_progress)
        self.assertEqual(self.course_progress.enrollment, self.enrollment)
        self.assertEqual(self.course_progress.progress_percentage, 0.0)
        # Check total topics count (course1 has 3 topics: topic1, topic2 from module1; topic3 from module2)
        self.assertEqual(self.course_progress.total_topics_count, 3)


    def test_topic_progress_creation_and_course_progress_update(self):
        # Mark topic1 as complete
        topic_progress1 = TopicProgress.objects.create(
            user=self.student_user,
            topic=self.topic1_m1_c1,
            is_completed=True
            # course_progress should be auto-linked by TopicProgress.save()
        )
        self.course_progress.refresh_from_db()
        self.assertEqual(topic_progress1.course_progress, self.course_progress)
        self.assertEqual(self.course_progress.completed_topics_count, 1)
        self.assertAlmostEqual(self.course_progress.progress_percentage, (1/3)*100)
        self.assertEqual(self.course_progress.last_accessed_topic, self.topic1_m1_c1)

        # Mark topic2 as complete
        TopicProgress.objects.create(
            user=self.student_user,
            topic=self.topic2_m1_c1,
            is_completed=True
        )
        self.course_progress.refresh_from_db()
        self.assertEqual(self.course_progress.completed_topics_count, 2)
        self.assertAlmostEqual(self.course_progress.progress_percentage, (2/3)*100)
        self.assertEqual(self.course_progress.last_accessed_topic, self.topic2_m1_c1)
        self.assertIsNone(self.course_progress.completed_at) # Not yet 100%

        # Mark topic3 as complete
        TopicProgress.objects.create(
            user=self.student_user,
            topic=self.topic3_m2_c1,
            is_completed=True
        )
        self.course_progress.refresh_from_db()
        self.assertEqual(self.course_progress.completed_topics_count, 3)
        self.assertAlmostEqual(self.course_progress.progress_percentage, 100.0)
        self.assertIsNotNone(self.course_progress.completed_at)


class QuizAttemptModelTests(CourseModelTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData()
        Enrollment.objects.create(user=self.student_user, course=self.course1)
        # Create some questions for topic1_m1_c1
        self.q1 = Question.objects.create(topic=self.topic1_m1_c1, text="Q1 Text", question_type='single-choice', order=1)
        self.c1_q1 = Choice.objects.create(question=self.q1, text="C1", is_correct=True, order=1)
        self.c2_q1 = Choice.objects.create(question=self.q1, text="C2", is_correct=False, order=2)
        self.q2 = Question.objects.create(topic=self.topic1_m1_c1, text="Q2 Text", question_type='multiple-choice', order=2)
        self.c1_q2 = Choice.objects.create(question=self.q2, text="C1-Q2", is_correct=True, order=1)
        self.c2_q2 = Choice.objects.create(question=self.q2, text="C2-Q2", is_correct=True, order=2)
        self.c3_q2 = Choice.objects.create(question=self.q2, text="C3-Q2", is_correct=False, order=3)


    def test_quiz_attempt_creation(self):
        attempt = QuizAttempt.objects.create(
            user=self.student_user,
            topic=self.topic1_m1_c1,
            score=75.0,
            correct_answers=1, # Assuming 1 out of some total
            total_questions_in_topic=self.topic1_m1_c1.questions.count()
        )
        self.assertEqual(attempt.user, self.student_user)
        self.assertEqual(attempt.topic, self.topic1_m1_c1)
        self.assertEqual(attempt.score, 75.0)
        self.assertEqual(attempt.total_questions_in_topic, 2)

    def test_user_topic_attempt_answer_creation(self):
        attempt = QuizAttempt.objects.create(
            user=self.student_user, topic=self.topic1_m1_c1, score=0, correct_answers=0, total_questions_in_topic=2
        )
        answer = UserTopicAttemptAnswer.objects.create(
            quiz_attempt=attempt,
            question=self.q1,
            is_correct=True
        )
        answer.selected_choices.add(self.c1_q1)

        self.assertEqual(answer.quiz_attempt, attempt)
        self.assertEqual(answer.question, self.q1)
        self.assertTrue(answer.is_correct)
        self.assertIn(self.c1_q1, answer.selected_choices.all())

# Add more tests for edge cases, other model methods, and more complex signal interactions.
