from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory # For providing request context to serializers
from rest_framework.exceptions import ValidationError
from decimal import Decimal

# Import models and serializers from the courses app
from apps.courses.models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress, QuizAttempt
)
from apps.courses.serializers import (
    CategorySerializer,
    CourseListSerializer, CourseDetailSerializer,
    ModuleListSerializer, ModuleDetailSerializer,
    TopicListSerializer, TopicDetailSerializer,
    QuestionSerializer, ChoiceSerializer,
    EnrollmentSerializer, CourseReviewSerializer,
    QuizSubmissionSerializer, QuizAttemptResultSerializer,
    TopicProgressSerializer
)

# Import the test data mixin from test_models.py
# Assuming test_models.py is in the same directory or accessible via python path
# For this standalone example, we might need to redefine it or ensure it's importable.
# For now, let's redefine a simplified version for clarity if direct import isn't feasible in this context.

User = get_user_model()

# Re-defining a simplified version of the TestDataMixin for serializer tests.
# In a real project, you'd import this from your test_models.py or a common test utils file.
class SerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.instructor_user = User.objects.create_user(
            username='ser_instructor', email='ser_instructor@example.com', password='password123',
            full_name='Serializer Instructor', is_instructor=True
        )
        cls.student_user = User.objects.create_user(
            username='ser_student', email='ser_student@example.com', password='password123',
            full_name='Serializer Student'
        )
        cls.another_student = User.objects.create_user(
            username='ser_student2', email='ser_student2@example.com', password='password123',
            full_name='Another Student'
        )

        cls.category = Category.objects.create(name='Serializer Testing', slug='serializer-testing')
        cls.course = Course.objects.create(
            title='Course for Serializer Test', slug='course-serializer-test',
            instructor=cls.instructor_user, category=cls.category,
            short_description='Testing serializers.', price=Decimal('19.99'), currency='USD',
            is_published=True, supports_ai_tutor=True
        )
        cls.module = Module.objects.create(course=cls.course, title='Module 1 for Serializer', order=1)
        cls.topic1 = Topic.objects.create(
            module=cls.module, title='Topic 1 for Serializer', slug='topic-1-serializer', order=1,
            content={'type': 'text', 'text_content': 'Test content'}, estimated_duration_minutes=5
        )
        cls.topic2 = Topic.objects.create(
            module=cls.module, title='Topic 2 for Serializer', slug='topic-2-serializer', order=2,
            content={'type': 'text', 'text_content': 'More content'}, estimated_duration_minutes=10,
            is_previewable=True
        )
        cls.question1_t1 = Question.objects.create(topic=cls.topic1, text="Q1?", question_type='single-choice', order=1)
        cls.choice1_q1 = Choice.objects.create(question=cls.question1_t1, text="Correct", is_correct=True, order=1)
        cls.choice2_q1 = Choice.objects.create(question=cls.question1_t1, text="Incorrect", is_correct=False, order=2)

        cls.question2_t1 = Question.objects.create(topic=cls.topic1, text="Q2 Multi?", question_type='multiple-choice', order=2)
        cls.choice1_q2 = Choice.objects.create(question=cls.question2_t1, text="Correct A", is_correct=True, order=1)
        cls.choice2_q2 = Choice.objects.create(question=cls.question2_t1, text="Correct B", is_correct=True, order=2)
        cls.choice3_q2 = Choice.objects.create(question=cls.question2_t1, text="Incorrect C", is_correct=False, order=3)

        # For providing request context to serializers
        cls.factory = APIRequestFactory()


class CategorySerializerTests(SerializerTestDataMixin, TestCase):
    def test_category_serialization(self):
        serializer = CategorySerializer(instance=self.category)
        data = serializer.data
        self.assertEqual(data['name'], self.category.name)
        self.assertEqual(data['slug'], self.category.slug)
        self.assertIn('id', data)

    def test_category_deserialization_create(self):
        data = {'name': 'New Category', 'slug': 'new-category', 'description': 'A new one'}
        serializer = CategorySerializer(data=data)
        self.assertTrue(serializer.is_valid())
        category = serializer.save()
        self.assertEqual(category.name, 'New Category')

    def test_category_deserialization_update(self):
        data = {'name': 'Updated Category Name', 'slug': self.category.slug} # Slug must be unique
        serializer = CategorySerializer(instance=self.category, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        category = serializer.save()
        self.assertEqual(category.name, 'Updated Category Name')


class CourseSerializersTests(SerializerTestDataMixin, TestCase):
    def test_course_list_serializer(self):
        # Mock request for context
        request = self.factory.get('/fake-url/')
        request.user = self.student_user # Simulate a logged-in student

        Enrollment.objects.create(user=self.student_user, course=self.course) # Enroll student

        serializer = CourseListSerializer(instance=self.course, context={'request': request})
        data = serializer.data

        self.assertEqual(data['title'], self.course.title)
        self.assertEqual(data['instructor_name'], self.instructor_user.full_name)
        self.assertTrue(data['is_enrolled']) # Student is enrolled
        self.assertIn('total_duration_minutes', data)

    def test_course_detail_serializer_read(self):
        request = self.factory.get('/fake-url/')
        request.user = self.student_user
        Enrollment.objects.create(user=self.student_user, course=self.course)
        TopicProgress.objects.create(user=self.student_user, topic=self.topic1, is_completed=True)

        serializer = CourseDetailSerializer(instance=self.course, context={'request': request})
        data = serializer.data

        self.assertEqual(data['title'], self.course.title)
        self.assertTrue(data['is_enrolled'])
        self.assertTrue(data['user_progress_percentage'] > 0) # Student has made some progress
        self.assertIsNotNone(data['last_accessed_topic_id']) # Updated by TopicProgress save
        self.assertEqual(len(data['modules']), 1)
        self.assertEqual(data['modules'][0]['title'], self.module.title)

    def test_course_detail_serializer_create(self):
        request = self.factory.post('/fake-url/')
        request.user = self.instructor_user # Instructor creates course

        data = {
            'title': 'New Advanced Course',
            'slug': 'new-advanced-course',
            'category_id': self.category.id,
            'short_description': 'An advanced topic.',
            'price': '99.99',
            'currency': 'USD',
            'level': 'advanced',
            'language': 'en',
            'is_published': False
        }
        serializer = CourseDetailSerializer(data=data, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        course = serializer.save() # instructor is set in serializer.create
        self.assertEqual(course.title, 'New Advanced Course')
        self.assertEqual(course.instructor, self.instructor_user)

    def test_course_detail_serializer_update_by_instructor(self):
        request = self.factory.patch('/fake-url/')
        request.user = self.instructor_user

        data = {'title': 'Updated Course Title by Instructor', 'is_published': True}
        serializer = CourseDetailSerializer(instance=self.course, data=data, partial=True, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        course = serializer.save()
        self.assertEqual(course.title, 'Updated Course Title by Instructor')
        self.assertTrue(course.is_published)


class ModuleSerializersTests(SerializerTestDataMixin, TestCase):
    def test_module_detail_serializer_read(self):
        request = self.factory.get('/fake-url/')
        request.user = self.student_user
        Enrollment.objects.create(user=self.student_user, course=self.course)
        TopicProgress.objects.create(user=self.student_user, topic=self.topic1, is_completed=True)

        serializer = ModuleDetailSerializer(instance=self.module, context={'request': request})
        data = serializer.data
        self.assertEqual(data['title'], self.module.title)
        self.assertEqual(len(data['topics']), 2) # topic1 and topic2
        self.assertTrue(data['user_progress_percentage'] > 0) # Progress on topic1

class TopicSerializersTests(SerializerTestDataMixin, TestCase):
    def test_topic_detail_serializer_read(self):
        request = self.factory.get('/fake-url/')
        request.user = self.student_user
        Enrollment.objects.create(user=self.student_user, course=self.course)
        TopicProgress.objects.create(user=self.student_user, topic=self.topic1, is_completed=True)

        serializer = TopicDetailSerializer(instance=self.topic1, context={'request': request})
        data = serializer.data
        self.assertEqual(data['title'], self.topic1.title)
        self.assertTrue(data['is_completed_by_user'])
        self.assertEqual(len(data['questions']), 2) # q1 and q2 for topic1
        self.assertTrue(data['supports_ai_tutor']) # Inherited from course

class QuestionSerializerTests(SerializerTestDataMixin, TestCase):
    def test_question_serializer_with_choices_create(self):
        data = {
            'topic_id': self.topic2.id,
            'text': 'A new question for topic 2?',
            'question_type': 'single-choice',
            'order': 1,
            'choices': [
                {'text': 'Choice A', 'is_correct': True, 'order': 1},
                {'text': 'Choice B', 'is_correct': False, 'order': 2},
            ]
        }
        serializer = QuestionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        question = serializer.save()
        self.assertEqual(question.text, 'A new question for topic 2?')
        self.assertEqual(question.choices.count(), 2)
        self.assertTrue(question.choices.filter(text='Choice A', is_correct=True).exists())

    def test_question_serializer_update_choices(self):
        data = {
            'text': 'Updated Q1 Text',
            'choices': [
                {'text': 'New Correct Choice', 'is_correct': True, 'order': 1},
                {'text': 'New Incorrect Choice', 'is_correct': False, 'order': 2},
            ]
        }
        serializer = QuestionSerializer(instance=self.question1_t1, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        question = serializer.save()
        self.assertEqual(question.text, 'Updated Q1 Text')
        self.assertEqual(question.choices.count(), 2)
        self.assertTrue(question.choices.filter(text='New Correct Choice', is_correct=True).exists())
        self.assertFalse(Choice.objects.filter(text="Correct", question=question).exists()) # Old choices deleted


class EnrollmentSerializerTests(SerializerTestDataMixin, TestCase):
    def test_enrollment_serializer_create(self):
        request = self.factory.post('/fake-url/') # Mock request
        request.user = self.another_student # A student not yet enrolled

        data = {'course_id': self.course.id}
        serializer = EnrollmentSerializer(data=data, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        enrollment = serializer.save() # user is set from context
        self.assertEqual(enrollment.user, self.another_student)
        self.assertEqual(enrollment.course, self.course)
        self.assertTrue(CourseProgress.objects.filter(user=self.another_student, course=self.course).exists())

    def test_enrollment_serializer_duplicate_enrollment(self):
        Enrollment.objects.create(user=self.student_user, course=self.course)
        request = self.factory.post('/fake-url/')
        request.user = self.student_user

        data = {'course_id': self.course.id}
        serializer = EnrollmentSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors) # Or specific field if validation is on course/user
        self.assertIn("You are already enrolled in this course.", str(serializer.errors))


class CourseReviewSerializerTests(SerializerTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData()
        # Student needs to be enrolled to review
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course)

    def test_course_review_create_valid(self):
        request = self.factory.post('/fake-url/')
        request.user = self.student_user

        data = {
            'course_id': self.course.id, # write_only
            'rating': 5,
            'comment': 'Loved this course!'
        }
        # user_id is also write_only, but we'll rely on context for user
        serializer = CourseReviewSerializer(data=data, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        review = serializer.save() # user is set from context
        self.assertEqual(review.user, self.student_user)
        self.assertEqual(review.course, self.course)
        self.assertEqual(review.rating, 5)

    def test_course_review_create_not_enrolled_fails(self):
        request = self.factory.post('/fake-url/')
        request.user = self.another_student # This student is not enrolled

        data = {'course_id': self.course.id, 'rating': 4}
        serializer = CourseReviewSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn("You must be enrolled in this course to submit a review.", str(serializer.errors))

    def test_course_review_create_duplicate_review_fails(self):
        CourseReview.objects.create(user=self.student_user, course=self.course, rating=3)
        request = self.factory.post('/fake-url/')
        request.user = self.student_user

        data = {'course_id': self.course.id, 'rating': 5}
        serializer = CourseReviewSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn("You have already reviewed this course.", str(serializer.errors))


class QuizSubmissionSerializerTests(SerializerTestDataMixin, TestCase):
    def setUp(self):
        super().setUpTestData()
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course)
        # CourseProgress should be created by enrollment signal
        self.course_progress = CourseProgress.objects.get(user=self.student_user, course=self.course)

    def test_quiz_submission_valid(self):
        request = self.factory.post('/fake-url/')
        request.user = self.student_user

        data = {
            'topic_id': self.topic1.id,
            'answers': [
                {'question_id': self.question1_t1.id, 'selected_choice_ids': [self.choice1_q1.id]}, # Correct
                {'question_id': self.question2_t1.id, 'selected_choice_ids': [self.choice1_q2.id, self.choice3_q2.id]} # Incorrect (c3 is wrong)
            ]
        }
        serializer = QuizSubmissionSerializer(data=data, context={'request': request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        quiz_attempt = serializer.save() # user is set from context

        self.assertEqual(quiz_attempt.user, self.student_user)
        self.assertEqual(quiz_attempt.topic, self.topic1)
        self.assertEqual(quiz_attempt.correct_answers, 1) # Only Q1 was fully correct
        self.assertEqual(quiz_attempt.total_questions_in_topic, 2)
        self.assertAlmostEqual(quiz_attempt.score, 50.0)
        self.assertIsNotNone(quiz_attempt.topic_progress)

        # Check that TopicProgress was updated (or created if it wasn't)
        topic_progress = TopicProgress.objects.get(user=self.student_user, topic=self.topic1)
        self.assertIsNotNone(topic_progress)
        # Depending on QUIZ_PASS_THRESHOLD, topic_progress.is_completed might change.
        # The serializer's create method doesn't currently set is_completed based on score.

    def test_quiz_submission_invalid_topic_id(self):
        request = self.factory.post('/fake-url/')
        request.user = self.student_user
        invalid_uuid = '123e4567-e89b-12d3-a456-426614174000'
        data = {'topic_id': invalid_uuid, 'answers': []}
        serializer = QuizSubmissionSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('topic_id', serializer.errors)

    def test_quiz_submission_not_enrolled(self):
        request = self.factory.post('/fake-url/')
        request.user = self.another_student # Not enrolled in self.course

        data = {
            'topic_id': self.topic1.id,
            'answers': [{'question_id': self.question1_t1.id, 'selected_choice_ids': [self.choice1_q1.id]}]
        }
        serializer = QuizSubmissionSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('topic_id', serializer.errors) # Validation is on topic_id field
        self.assertIn("You must be enrolled in the course to submit this quiz.", str(serializer.errors['topic_id']))

    def test_quiz_submission_answer_for_wrong_topic_question(self):
        request = self.factory.post('/fake-url/')
        request.user = self.student_user
        
        # Create a question belonging to another topic
        other_topic = Topic.objects.create(module=self.module, title="Other Topic", slug="other-topic", order=3, content={})
        other_question = Question.objects.create(topic=other_topic, text="Other Q", order=1)

        data = {
            'topic_id': self.topic1.id,
            'answers': [
                {'question_id': other_question.id, 'selected_choice_ids': []} 
            ]
        }
        serializer = QuizSubmissionSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('answers', serializer.errors)
        self.assertIn("One or more submitted question IDs do not belong to this topic.", str(serializer.errors['answers']))

    def test_quiz_submission_choice_for_wrong_question(self):
        request = self.factory.post('/fake-url/')
        request.user = self.student_user
        
        data = {
            'topic_id': self.topic1.id,
            'answers': [
                {'question_id': self.question1_t1.id, 'selected_choice_ids': [self.choice1_q2.id]} # choice1_q2 belongs to question2_t1
            ]
        }
        serializer = QuizSubmissionSerializer(data=data, context={'request': request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('answers', serializer.errors)
        self.assertIn("Choice does not belong to the specified question.", str(serializer.errors['answers']))

# Add more tests for other serializers:
# - TopicProgressSerializer
# - QuizAttemptResultSerializer
# - etc.
