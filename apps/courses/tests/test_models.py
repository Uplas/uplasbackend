from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.db.utils import IntegrityError
from decimal import Decimal

from ..models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
# Assuming currency choices might be needed for direct Course creation,
# though they are primarily for the serializer and views.
# from apps.users.models import CURRENCY_CHOICES (if defined there and not settings)
from django.conf import settings


User = get_user_model()

class CourseCategoryModelTests(TestCase):

    def test_create_course_category(self):
        """Test creating a CourseCategory successfully."""
        category = CourseCategory.objects.create(name="AI Fundamentals")
        self.assertEqual(category.name, "AI Fundamentals")
        self.assertEqual(category.slug, slugify("AI Fundamentals"))
        self.assertIsNotNone(category.created_at)
        self.assertIsNotNone(category.updated_at)
        self.assertEqual(str(category), "AI Fundamentals")

    def test_course_category_slug_uniqueness(self):
        """Test slug uniqueness for CourseCategory."""
        CourseCategory.objects.create(name="Data Science")
        with self.assertRaises(IntegrityError):
            CourseCategory.objects.create(name="Data Science", slug=slugify("Data Science")) # Manual slug to test DB constraint
        # Test automatic slug generation if name is same (should fail on name unique constraint first)
        with self.assertRaises(IntegrityError):
             CourseCategory.objects.create(name="Data Science")


class CourseModelTests(TestCase):

    def setUp(self):
        self.category = CourseCategory.objects.create(name="Web Development")
        self.instructor = User.objects.create_user(email="instructor@example.com", password="password")

    def test_create_course(self):
        """Test creating a Course successfully."""
        course_data = {
            "title": "Advanced Django Web Apps",
            "description_html": "<p>Learn Django deeply.</p>",
            "category": self.category,
            "instructor": self.instructor,
            "price": Decimal("99.99"),
            "currency": "USD", # Assuming USD is a valid choice from settings.CURRENCY_CHOICES
            "difficulty_level": Course.DIFFICULTY_CHOICES[1][0], # intermediate
            "learning_objectives": ["Objective 1", "Objective 2"],
        }
        course = Course.objects.create(**course_data)
        self.assertEqual(course.title, course_data["title"])
        self.assertEqual(course.slug, slugify(course_data["title"]))
        self.assertEqual(course.category, self.category)
        self.assertEqual(course.instructor, self.instructor)
        self.assertEqual(course.price, course_data["price"])
        self.assertEqual(course.average_rating, 0.0)
        self.assertEqual(course.total_enrollments, 0)
        self.assertFalse(course.is_published)
        self.assertIsNone(course.published_date)
        self.assertEqual(str(course), course_data["title"])

    def test_course_publish_date_logic(self):
        """Test published_date is set when is_published is True."""
        course = Course.objects.create(title="Test Course", description_html="Desc")
        self.assertFalse(course.is_published)
        self.assertIsNone(course.published_date)

        course.is_published = True
        course.save()
        self.assertIsNotNone(course.published_date)
        self.assertTrue(timezone.now() - course.published_date < timezone.timedelta(seconds=5))

        # Test if unpublishing clears the date (as per current save logic)
        # Current save logic does not clear it, which might be intended.
        # If it should clear:
        # course.is_published = False
        # course.save()
        # self.assertIsNone(course.published_date)

    def test_course_slug_uniqueness_on_create(self):
        """Test unique slug generation on Course creation if titles are similar."""
        Course.objects.create(title="My Test Course", description_html="Desc1")
        course2 = Course.objects.create(title="My Test Course", description_html="Desc2")
        self.assertNotEqual(course2.slug, slugify("My Test Course"))
        self.assertTrue(course2.slug.startswith(slugify("My Test Course") + "-"))

    def test_course_slug_uniqueness_on_update(self):
        """Test unique slug generation on Course update if titles are similar."""
        course1 = Course.objects.create(title="Original Title", description_html="Desc1")
        course2 = Course.objects.create(title="Another Title", description_html="Desc2")
        
        course2.title = "Original Title" # Try to make title same as course1
        course2.slug = "" # Clear slug to trigger regeneration
        course2.save()
        
        self.assertNotEqual(course2.slug, course1.slug)
        self.assertTrue(course2.slug.startswith(slugify("Original Title") + "-"))

class ModuleModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title="Main Course", description_html="...")

    def test_create_module(self):
        """Test creating a Module successfully."""
        module = Module.objects.create(course=self.course, title="Module 1: Basics", order=1)
        self.assertEqual(module.course, self.course)
        self.assertEqual(module.title, "Module 1: Basics")
        self.assertEqual(module.order, 1)
        self.assertEqual(str(module), f"{self.course.title} - Module 1: Module 1: Basics")

    def test_module_order_unique_per_course(self):
        """Test that module order is unique within a course."""
        Module.objects.create(course=self.course, title="Module A", order=1)
        with self.assertRaises(IntegrityError):
            Module.objects.create(course=self.course, title="Module B", order=1)

        # Different course, same order should be fine
        other_course = Course.objects.create(title="Other Course", description_html="...")
        Module.objects.create(course=other_course, title="Module C", order=1)
        self.assertEqual(Module.objects.filter(order=1).count(), 2)


class TopicModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title="Topic Course", description_html="...")
        self.module = Module.objects.create(course=self.course, title="Topic Module", order=1)

    def test_create_topic(self):
        """Test creating a Topic successfully."""
        topic = Topic.objects.create(
            module=self.module,
            title="First Topic",
            order=1,
            content_type='text',
            text_content_html="<p>Content here.</p>"
        )
        self.assertEqual(topic.module, self.module)
        self.assertEqual(topic.title, "First Topic")
        self.assertTrue(topic.slug.endswith(slugify("First Topic")))
        self.assertTrue(topic.supports_ai_tutor) # Default value

    def test_topic_order_unique_per_module(self):
        """Test that topic order is unique within a module."""
        Topic.objects.create(module=self.module, title="Topic A", order=1, content_type='text')
        with self.assertRaises(IntegrityError):
            Topic.objects.create(module=self.module, title="Topic B", order=1, content_type='text')

        # Different module, same order should be fine
        other_module = Module.objects.create(course=self.course, title="Other Module", order=2)
        Topic.objects.create(module=other_module, title="Topic C", order=1, content_type='text')
        self.assertEqual(Topic.objects.filter(order=1).count(), 2)


class QuizModelsTests(TestCase):
    def setUp(self):
        course = Course.objects.create(title="Quiz Course", description_html="...")
        module = Module.objects.create(course=course, title="Quiz Module", order=1)
        self.topic = Topic.objects.create(module=module, title="Quiz Topic", order=1, content_type='quiz')
        self.quiz = Quiz.objects.create(topic=self.topic, pass_mark_percentage=75)

    def test_create_quiz(self):
        """Test Quiz creation and title auto-population."""
        self.assertEqual(self.quiz.topic, self.topic)
        self.assertEqual(self.quiz.title, f"Quiz for: {self.topic.title}")
        self.assertEqual(self.quiz.pass_mark_percentage, 75)
        self.assertEqual(str(self.quiz), f"Quiz for: {self.topic.title}")

    def test_create_question(self):
        """Test Question creation."""
        question = Question.objects.create(
            quiz=self.quiz,
            text="What is 1+1?",
            question_type='single_choice',
            order=1,
            points=5
        )
        self.assertEqual(question.quiz, self.quiz)
        self.assertEqual(question.text, "What is 1+1?")
        self.assertEqual(question.points, 5)
        self.assertTrue(str(question).startswith("Q1: What is 1+1?"))

    def test_create_answer_option(self):
        """Test AnswerOption creation."""
        question = Question.objects.create(quiz=self.quiz, text="Is Python cool?")
        option = AnswerOption.objects.create(question=question, text="Yes", is_correct=True)
        self.assertEqual(option.question, question)
        self.assertEqual(option.text, "Yes")
        self.assertTrue(option.is_correct)
        self.assertEqual(str(option), "Yes (Correct: True)")


class UserCourseInteractionModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="student@example.com", password="password")
        self.course1 = Course.objects.create(title="Course One", description_html="Desc1")
        self.module1_c1 = Module.objects.create(course=self.course1, title="M1C1", order=1)
        self.topic1_m1_c1 = Topic.objects.create(module=self.module1_c1, title="T1M1C1", order=1, content_type='text')
        self.topic2_m1_c1 = Topic.objects.create(module=self.module1_c1, title="T2M1C1", order=2, content_type='text')

        self.course2_no_topics = Course.objects.create(title="Course Two No Topics", description_html="Desc2")


    def test_user_course_enrollment(self):
        """Test UserCourseEnrollment creation and uniqueness."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        self.assertEqual(enrollment.user, self.user)
        self.assertEqual(enrollment.course, self.course1)
        self.assertEqual(enrollment.progress_percentage, 0) # Initially 0
        self.assertIsNotNone(enrollment.enrolled_at)
        self.assertEqual(str(enrollment), f"{self.user.username} enrolled in {self.course1.title}")

        with self.assertRaises(IntegrityError): # Test unique_together
            UserCourseEnrollment.objects.create(user=self.user, course=self.course1)

    def test_user_topic_attempt(self):
        """Test UserTopicAttempt creation and uniqueness."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        attempt = UserTopicAttempt.objects.create(
            enrollment=enrollment,
            topic=self.topic1_m1_c1,
            user=self.user # Ensure user consistency
        )
        self.assertEqual(attempt.enrollment, enrollment)
        self.assertEqual(attempt.topic, self.topic1_m1_c1)
        self.assertEqual(attempt.user, self.user)
        self.assertFalse(attempt.is_completed)

        with self.assertRaises(IntegrityError): # Test unique_together
            UserTopicAttempt.objects.create(enrollment=enrollment, topic=self.topic1_m1_c1, user=self.user)

    def test_user_topic_attempt_user_mismatch_raises_error(self):
        """Test UserTopicAttempt save method raises error if user mismatches enrollment user."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        other_user = User.objects.create_user(email="other@example.com", password="password")
        with self.assertRaises(ValueError):
            UserTopicAttempt.objects.create(
                enrollment=enrollment,
                topic=self.topic1_m1_c1,
                user=other_user # Mismatching user
            )

    def test_enrollment_update_progress_no_topics(self):
        """Test progress update for a course with no topics."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course2_no_topics)
        enrollment.update_progress() # Explicit call, though signal should handle it
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 100) # Course with no topics is 100% complete
        self.assertIsNotNone(enrollment.completed_at)


    def test_enrollment_update_progress_with_topic_attempts(self):
        """Test UserCourseEnrollment.update_progress logic."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        self.assertEqual(enrollment.progress_percentage, 0)

        # Complete first topic
        attempt1 = UserTopicAttempt.objects.create(enrollment=enrollment, topic=self.topic1_m1_c1, user=self.user, is_completed=True)
        attempt1.save() # Trigger signal if not already, or rely on create
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 50) # 1 out of 2 topics completed
        self.assertIsNone(enrollment.completed_at)

        # Complete second topic
        attempt2 = UserTopicAttempt.objects.create(enrollment=enrollment, topic=self.topic2_m1_c1, user=self.user, is_completed=True)
        attempt2.save()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 100)
        self.assertIsNotNone(enrollment.completed_at)

        # Un-complete a topic
        attempt1.is_completed = False
        attempt1.save()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 50)
        # completed_at might remain if logic is to only set it once, or clear it.
        # Current logic in update_progress will keep completed_at if progress < 100, which is fine.

    def test_user_topic_attempt_save_triggers_progress_update(self):
        """Test that saving UserTopicAttempt triggers enrollment progress update."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        
        # Create an attempt (not completed)
        attempt = UserTopicAttempt(enrollment=enrollment, topic=self.topic1_m1_c1, user=self.user)
        attempt.save() # Initial save
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 0)

        # Now mark as completed and save
        attempt.is_completed = True
        attempt.save()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.progress_percentage, 50)


class ReviewModelSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reviewer@example.com", password="password")
        self.course = Course.objects.create(title="Reviewable Course", description_html="Content")

    def test_review_creation_updates_course_rating(self):
        """Test creating a Review updates Course.average_rating."""
        self.assertEqual(self.course.average_rating, 0.0)
        Review.objects.create(course=self.course, user=self.user, rating=5, comment="Great!")
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 5.0)

        Review.objects.create(course=self.course, user=User.objects.create_user(email="rev2@ex.com",password="p"), rating=3)
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 4.0) # (5+3)/2

    def test_review_deletion_updates_course_rating(self):
        """Test deleting a Review updates Course.average_rating."""
        review1 = Review.objects.create(course=self.course, user=self.user, rating=5)
        user2 = User.objects.create_user(email="rev2@example.com", password="password")
        Review.objects.create(course=self.course, user=user2, rating=3)
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 4.0)

        review1.delete()
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 3.0)
        
        # Delete last review
        Review.objects.filter(course=self.course).delete()
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 0.0)


    def test_review_update_updates_course_rating(self):
        """Test updating a Review updates Course.average_rating."""
        review = Review.objects.create(course=self.course, user=self.user, rating=2)
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 2.0)

        review.rating = 4
        review.save() # This triggers post_save signal
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 4.0)


class CourseEnrollmentSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="enroll_user@example.com", password="password")
        self.course = Course.objects.create(title="Enrollable Course", description_html="Content")

    def test_enrollment_creation_updates_total_enrollments(self):
        self.assertEqual(self.course.total_enrollments, 0)
        UserCourseEnrollment.objects.create(user=self.user, course=self.course)
        self.course.refresh_from_db()
        self.assertEqual(self.course.total_enrollments, 1)

    def test_enrollment_deletion_updates_total_enrollments(self):
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course)
        self.course.refresh_from_db()
        self.assertEqual(self.course.total_enrollments, 1)
        enrollment.delete()
        self.course.refresh_from_db()
        self.assertEqual(self.course.total_enrollments, 0)
