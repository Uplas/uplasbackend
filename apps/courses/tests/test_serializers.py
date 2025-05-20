from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.test import APIRequestFactory # To create mock request for context
from decimal import Decimal

from ..models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
from ..serializers import (
    CourseCategorySerializer, CourseSerializer, CourseDetailSerializer,
    ModuleSerializer, TopicSerializer, QuizSerializer, QuestionSerializer, AnswerOptionSerializer, AnswerOptionStudentViewSerializer,
    UserCourseEnrollmentSerializer, UserTopicAttemptSerializer, BasicUserTopicAttemptSerializer, ReviewSerializer,
    QuizSubmissionSerializer, SubmitAnswerSerializer
)
# Assuming BasicUserSerializer is defined in courses.serializers or imported if in users.serializers
# from apps.users.serializers import BasicUserSerializer # If it's there

User = get_user_model()

# If BasicUserSerializer is not defined elsewhere for this test file, define a minimal one.
class BasicUserSerializerForTest(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name']


class CourseCategorySerializerTests(TestCase):
    def test_category_serializer_valid_data(self):
        category_data = {"name": "Machine Learning", "description": "Learn ML"}
        serializer = CourseCategorySerializer(data=category_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, category_data["name"])

    def test_category_serializer_output_data(self):
        category = CourseCategory.objects.create(name="Data Science")
        serializer = CourseCategorySerializer(category)
        self.assertEqual(serializer.data['name'], "Data Science")
        self.assertIn('slug', serializer.data)


class CourseSerializersTests(TestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(email="courseinst@example.com", password="password", full_name="Course Instructor")
        self.category = CourseCategory.objects.create(name="Python Programming")
        self.course = Course.objects.create(
            title="Complete Python Bootcamp",
            subtitle="From zero to hero",
            description_html="<p>Content</p>",
            category=self.category,
            instructor=self.instructor,
            price=Decimal("19.99"),
            difficulty_level='beginner',
            is_published=True,
            published_date=timezone.now()
        )
        self.module = Module.objects.create(course=self.course, title="Introduction", order=1)
        self.topic = Topic.objects.create(module=self.module, title="Hello World", order=1)

        # For request context in serializers
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.user = User.objects.create_user(email="student@example.com", password="password")
        self.request.user = self.user # Simulate authenticated user

    def test_course_serializer_output_data(self):
        """Test CourseSerializer basic output for a published course."""
        # Simulate annotation that view would do
        setattr(self.course, 'is_enrolled_annotated', False)
        setattr(self.course, 'current_user_progress_annotated', None)

        serializer = CourseSerializer(self.course, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['title'], self.course.title)
        self.assertEqual(data['instructor']['full_name'], self.instructor.full_name)
        self.assertEqual(data['category']['name'], self.category.name)
        self.assertFalse(data['is_enrolled']) # Based on SerializerMethodField logic
        self.assertIsNone(data['enrollment_progress'])

    def test_course_serializer_enrollment_data_when_enrolled(self):
        """Test CourseSerializer shows enrollment data when user is enrolled."""
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course, progress_percentage=25)
        
        # Simulate annotations
        setattr(self.course, 'is_enrolled_annotated', True)
        setattr(self.course, 'current_user_progress_annotated', 25)
        
        # Pass enrollment in context if serializer uses it directly (as a fallback or primary)
        context = {'request': self.request, f'enrollment_course_{self.course.id}': enrollment}
        serializer = CourseSerializer(self.course, context=context)
        data = serializer.data
        
        self.assertTrue(data['is_enrolled'])
        self.assertEqual(data['enrollment_progress'], 25)

    def test_course_detail_serializer_includes_modules(self):
        """Test CourseDetailSerializer includes modules with topics."""
        # Simulate annotation for detail view (though not strictly necessary if modules are always fetched)
        setattr(self.course, 'is_enrolled_annotated', False)
        setattr(self.course, 'current_user_progress_annotated', None)

        serializer = CourseDetailSerializer(self.course, context={'request': self.request})
        data = serializer.data
        self.assertIn('modules', data)
        self.assertEqual(len(data['modules']), 1)
        self.assertEqual(data['modules'][0]['title'], self.module.title)
        self.assertEqual(len(data['modules'][0]['topics']), 1)
        self.assertEqual(data['modules'][0]['topics'][0]['title'], self.topic.title)

    # Test for Course creation would be more of a view test, as instructor_id/category_id are write_only
    # but we can test the serializer's create method if it had complex logic (it doesn't currently).


class ModuleTopicSerializersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="moduletest@example.com", password="password")
        self.course = Course.objects.create(title="Module Course", description_html="...")
        self.module = Module.objects.create(course=self.course, title="First Module", order=1)
        self.topic1 = Topic.objects.create(module=self.module, title="Topic Alpha", order=1, content_type='text')
        self.topic2_quiz = Topic.objects.create(module=self.module, title="Topic Beta Quiz", order=2, content_type='quiz')
        self.quiz = Quiz.objects.create(topic=self.topic2_quiz) # Quiz associated with topic2
        
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.user

    def test_module_serializer_output(self):
        serializer = ModuleSerializer(self.module, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['title'], self.module.title)
        self.assertEqual(len(data['topics']), 2)
        self.assertEqual(data['topics'][0]['title'], self.topic1.title)

    def test_topic_serializer_output_text_topic(self):
        serializer = TopicSerializer(self.topic1, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['title'], self.topic1.title)
        self.assertEqual(data['content_type'], 'text')
        self.assertIsNone(data['quiz_details'])
        self.assertIsNone(data['user_progress']) # No enrollment yet

    def test_topic_serializer_output_quiz_topic(self):
        # Pass context to indicate it's not student_view for quiz setup
        context = {'request': self.request, 'student_view': False} 
        serializer = TopicSerializer(self.topic2_quiz, context=context)
        data = serializer.data
        self.assertEqual(data['title'], self.topic2_quiz.title)
        self.assertEqual(data['content_type'], 'quiz')
        self.assertIsNotNone(data['quiz_details'])
        self.assertEqual(data['quiz_details']['id'], str(self.quiz.id))

    def test_topic_serializer_user_progress(self):
        enrollment = UserCourseEnrollment.objects.create(user=self.user, course=self.course)
        UserTopicAttempt.objects.create(
            enrollment=enrollment, topic=self.topic1, user=self.user, is_completed=True, score=None
        )
        # Pass enrollment in context for efficiency
        context = {'request': self.request, f'enrollment_course_{self.course.id}': enrollment}
        serializer = TopicSerializer(self.topic1, context=context)
        data = serializer.data
        self.assertIsNotNone(data['user_progress'])
        self.assertTrue(data['user_progress']['is_completed'])


class QuizQuestionAnswerSerializersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="quiztest@example.com", password="password")
        course = Course.objects.create(title="Quiz Course", description_html="...")
        module = Module.objects.create(course=course, title="Quiz Module", order=1)
        topic = Topic.objects.create(module=module, title="Main Quiz", order=1, content_type='quiz')
        self.quiz = Quiz.objects.create(topic=topic)
        self.question1 = Question.objects.create(quiz=self.quiz, text="Q1", question_type='single_choice', order=1)
        self.option1_q1 = AnswerOption.objects.create(question=self.question1, text="Opt A (Correct)", is_correct=True)
        self.option2_q1 = AnswerOption.objects.create(question=self.question1, text="Opt B", is_correct=False)
        
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/') # Generic request
        self.request.user = self.user


    def test_answer_option_serializer_author_view(self):
        """Test AnswerOptionSerializer shows is_correct for authoring/review."""
        serializer = AnswerOptionSerializer(self.option1_q1)
        self.assertTrue(serializer.data['is_correct'])
        serializer_false = AnswerOptionSerializer(self.option2_q1)
        self.assertFalse(serializer_false.data['is_correct'])

    def test_answer_option_student_view_serializer(self):
        """Test AnswerOptionStudentViewSerializer hides is_correct."""
        serializer = AnswerOptionStudentViewSerializer(self.option1_q1)
        self.assertNotIn('is_correct', serializer.data)
        self.assertEqual(serializer.data['text'], self.option1_q1.text)

    def test_question_serializer_author_view(self):
        """Test QuestionSerializer shows correct options for author/review context."""
        context = {'request': self.request, 'student_view': False} # Author context
        serializer = QuestionSerializer(self.question1, context=context)
        data = serializer.data
        self.assertEqual(len(data['options']), 2)
        self.assertTrue(data['options'][0]['is_correct']) # Assuming option1_q1 is first
        self.assertIn('explanation', data) # Explanation should be available

    def test_question_serializer_student_view(self):
        """Test QuestionSerializer hides sensitive option data for student quiz-taking context."""
        context = {'request': self.request, 'student_view': True} # Student context
        serializer = QuestionSerializer(self.question1, context=context)
        data = serializer.data
        self.assertEqual(len(data['options']), 2)
        self.assertNotIn('is_correct', data['options'][0]) # is_correct should be hidden
        # Explanation is typically read-only, so its presence depends on model, not student_view for options.
        # If explanation should also be hidden during quiz taking, serializer needs more logic.

    def test_quiz_serializer_output(self):
        context = {'request': self.request, 'student_view': False}
        serializer = QuizSerializer(self.quiz, context=context)
        data = serializer.data
        self.assertEqual(data['title'], f"Quiz for: {self.quiz.topic.title}")
        self.assertEqual(len(data['questions']), 1)
        self.assertEqual(data['questions'][0]['text'], self.question1.text)


class UserInteractionSerializersTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email="student1@example.com", password="password", full_name="Student One")
        self.user2 = User.objects.create_user(email="student2@example.com", password="password", full_name="Student Two")
        self.course = Course.objects.create(title="Interaction Course", description_html="...")
        self.topic = Topic.objects.create(module=Module.objects.create(course=self.course, title="IM"), title="IT", order=1)
        self.enrollment1 = UserCourseEnrollment.objects.create(user=self.user1, course=self.course)

        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.user1

    def test_review_serializer_valid_data(self):
        review_data = {"rating": 5, "comment": "Excellent course!"}
        # Course and user are typically set by the view context, not in serializer data for creation
        serializer = ReviewSerializer(data=review_data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # review = serializer.save(user=self.user1, course=self.course) # Simulate view saving
        # self.assertEqual(review.rating, 5)

    def test_review_serializer_invalid_rating(self):
        review_data = {"rating": 6, "comment": "Too good!"}
        serializer = ReviewSerializer(data=review_data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_review_serializer_output(self):
        review = Review.objects.create(user=self.user1, course=self.course, rating=4, comment="Good")
        serializer = ReviewSerializer(review, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['rating'], 4)
        self.assertEqual(data['user']['full_name'], self.user1.full_name)

    def test_user_course_enrollment_serializer_output(self):
        self.enrollment1.last_accessed_topic = self.topic
        self.enrollment1.save()
        serializer = UserCourseEnrollmentSerializer(self.enrollment1, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['user']['full_name'], self.user1.full_name)
        self.assertEqual(data['course']['title'], self.course.title)
        self.assertEqual(data['last_accessed_topic']['title'], self.topic.title)

    def test_user_topic_attempt_serializer_output(self):
        attempt = UserTopicAttempt.objects.create(
            enrollment=self.enrollment1, topic=self.topic, user=self.user1,
            is_completed=True, score=80.0, passed=True
        )
        serializer = UserTopicAttemptSerializer(attempt, context={'request': self.request})
        data = serializer.data
        self.assertTrue(data['is_completed'])
        self.assertEqual(data['score'], 80.0)
        self.assertEqual(data['topic']['title'], self.topic.title)


class QuizSubmissionSerializersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="quizsubmit@example.com", password="password")
        course = Course.objects.create(title="Submission Course", description_html="...")
        module = Module.objects.create(course=course, title="SM", order=1)
        self.topic_quiz = Topic.objects.create(module=module, title="Submission Quiz", order=1, content_type='quiz')
        quiz = Quiz.objects.create(topic=self.topic_quiz)
        self.question1 = Question.objects.create(quiz=quiz, text="Q1 SC", question_type='single_choice', order=1)
        self.q1_opt1 = AnswerOption.objects.create(question=self.question1, text="Q1OptA", is_correct=True)
        self.q1_opt2 = AnswerOption.objects.create(question=self.question1, text="Q1OptB", is_correct=False)
        self.question2 = Question.objects.create(quiz=quiz, text="Q2 SA", question_type='short_answer', order=2)
        AnswerOption.objects.create(question=self.question2, text="Correct Short Answer", is_correct=True) # For validation

    def test_submit_answer_serializer_valid_choice(self):
        data = {"question_id": str(self.question1.id), "answer_option_ids": [str(self.q1_opt1.id)]}
        serializer = SubmitAnswerSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_submit_answer_serializer_valid_short_answer(self):
        data = {"question_id": str(self.question2.id), "text_answer": "My short answer."}
        serializer = SubmitAnswerSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_submit_answer_serializer_missing_options_for_choice(self):
        data = {"question_id": str(self.question1.id)} # Missing answer_option_ids
        serializer = SubmitAnswerSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("answer_option_ids", serializer.errors)

    def test_submit_answer_serializer_missing_text_for_short_answer(self):
        data = {"question_id": str(self.question2.id)} # Missing text_answer
        serializer = SubmitAnswerSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("text_answer", serializer.errors)
        
    def test_submit_answer_serializer_invalid_question_id(self):
        invalid_uuid = uuid.uuid4()
        data = {"question_id": str(invalid_uuid), "text_answer": "Answer"}
        serializer = SubmitAnswerSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("question_id", serializer.errors)


    def test_quiz_submission_serializer_valid_data(self):
        answers_data = [
            {"question_id": str(self.question1.id), "answer_option_ids": [str(self.q1_opt2.id)]},
            {"question_id": str(self.question2.id), "text_answer": "Some text"}
        ]
        # topic_id is usually from URL, not serializer payload for this setup
        submission_data = {"answers": answers_data}
        serializer = QuizSubmissionSerializer(data=submission_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_quiz_submission_serializer_empty_answers_list(self):
        submission_data = {"answers": []} # allow_empty=False on answers field
        serializer = QuizSubmissionSerializer(data=submission_data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("answers", serializer.errors)
