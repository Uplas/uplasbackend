from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import (
    CourseCategory, Course, Module, Topic, Quiz, Question, AnswerOption,
    UserCourseEnrollment, UserTopicAttempt, Review
)
# Assuming CURRENCY_CHOICES is available in settings
# from apps.users.models import CURRENCY_CHOICES (or from settings)
from django.conf import settings


User = get_user_model()

class CourseCategoryViewTests(APITestCase):
    def setUp(self):
        self.category1 = CourseCategory.objects.create(name="Python", display_order=1)
        self.category2 = CourseCategory.objects.create(name="Data Science", display_order=0)
        self.list_url = reverse('courses:coursecategory-list')
        self.detail_url = reverse('courses:coursecategory-detail', kwargs={'pk': self.category1.pk})


    def test_list_course_categories(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Assuming default pagination or few items
        self.assertEqual(response.data['results'][0]['name'], self.category2.name) # Ordered by display_order, then name

    def test_retrieve_course_category(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.category1.name)


class CourseViewSetTests(APITestCase):
    def setUp(self):
        self.instructor_user = User.objects.create_user(email="inst@example.com", password="password", is_staff=True, full_name="Course Inst") # is_staff for creation permission
        self.student_user = User.objects.create_user(email="student_c@example.com", password="password", full_name="Student C")
        self.other_user = User.objects.create_user(email="other_c@example.com", password="password", full_name="Other C")

        self.category = CourseCategory.objects.create(name="Web Dev")
        self.course1 = Course.objects.create(
            title="Django Basics", slug="django-basics", instructor=self.instructor_user, category=self.category,
            description_html="Learn Django", price=Decimal("10.00"), is_published=True, published_date=timezone.now()
        )
        self.course2_draft = Course.objects.create(
            title="Flask Advanced", slug="flask-advanced", instructor=self.instructor_user, category=self.category,
            description_html="Learn Flask", price=Decimal("20.00"), is_published=False
        )
        self.module1_c1 = Module.objects.create(course=self.course1, title="M1C1 Intro", order=1)

        self.list_url = reverse('courses:course-list')
        self.detail_url_c1 = reverse('courses:course-detail', kwargs={'slug': self.course1.slug})
        self.detail_url_c2_draft = reverse('courses:course-detail', kwargs={'slug': self.course2_draft.slug})
        self.enroll_url_c1 = reverse('courses:course-enroll', kwargs={'slug': self.course1.slug})
        self.my_progress_url_c1 = reverse('courses:course-my-progress', kwargs={'slug': self.course1.slug})
        self.modules_url_c1 = reverse('courses:course-list-modules', kwargs={'slug': self.course1.slug})


    def test_list_courses_unauthenticated(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # Only course1 (published)
        self.assertEqual(response.data['results'][0]['title'], self.course1.title)

    def test_list_courses_authenticated_student(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['title'], self.course1.title)

    def test_list_courses_authenticated_instructor_staff(self):
        self.client.force_authenticate(user=self.instructor_user) # is_staff = True
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # Sees both published and draft

    def test_retrieve_published_course_unauthenticated(self):
        response = self.client.get(self.detail_url_c1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.course1.title)
        self.assertIn('modules', response.data) # CourseDetailSerializer

    def test_retrieve_draft_course_unauthenticated_fails(self):
        response = self.client.get(self.detail_url_c2_draft)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Not found for non-staff

    def test_retrieve_draft_course_instructor_staff_succeeds(self):
        self.client.force_authenticate(user=self.instructor_user)
        response = self.client.get(self.detail_url_c2_draft)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.course2_draft.title)

    def test_create_course_instructor_staff_succeeds(self):
        self.client.force_authenticate(user=self.instructor_user)
        data = {
            "title": "New Course by Instructor", "description_html": "Desc", "price": "5.00",
            "category_id": self.category.id, "difficulty_level": "beginner"
        }
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Course.objects.filter(title="New Course by Instructor").exists())

    def test_create_course_non_staff_fails(self):
        self.client.force_authenticate(user=self.student_user)
        data = {"title": "Student Course", "description_html": "Desc", "price": "5.00"}
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_course_by_instructor_succeeds(self):
        self.client.force_authenticate(user=self.instructor_user)
        data = {"title": "Django Basics Updated", "price": "12.00"}
        response = self.client.patch(self.detail_url_c1, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.title, "Django Basics Updated")

    def test_update_course_by_other_staff_fails_if_not_instructor(self):
        # Current IsInstructorOrReadOnly allows any staff for read, but write only by obj.instructor
        other_staff = User.objects.create_user(email="otherstaff@example.com", password="pw", is_staff=True)
        self.client.force_authenticate(user=other_staff)
        data = {"title": "Attempted Update"}
        response = self.client.patch(self.detail_url_c1, data, format='json') # course1 instructor is self.instructor_user
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # Or 404 if get_object filters by instructor

    def test_enroll_in_course_success(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(self.enroll_url_c1, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(UserCourseEnrollment.objects.filter(user=self.student_user, course=self.course1).exists())

    def test_enroll_in_course_already_enrolled(self):
        UserCourseEnrollment.objects.create(user=self.student_user, course=self.course1)
        self.client.force_authenticate(user=self.student_user)
        response = self.client.post(self.enroll_url_c1, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_my_progress_enrolled(self):
        UserCourseEnrollment.objects.create(user=self.student_user, course=self.course1, progress_percentage=50)
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.my_progress_url_c1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['progress_percentage'], 50)

    def test_get_my_progress_not_enrolled(self):
        self.client.force_authenticate(user=self.student_user) # Student is not enrolled
        response = self.client.get(self.my_progress_url_c1, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsEnrolled permission

    def test_list_modules_for_course(self):
        # Access to course itself is checked by CourseViewSet's permissions
        self.client.force_authenticate(user=self.student_user) # Any authenticated user can see modules of published course
        response = self.client.get(self.modules_url_c1, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], self.module1_c1.title)


class TopicViewSetTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="topicstudent@example.com", password="password")
        self.course = Course.objects.create(title="Topic Course", description_html="Desc", is_published=True, published_date=timezone.now())
        self.module = Module.objects.create(course=self.course, title="Topic Module", order=1)
        self.topic_previewable = Topic.objects.create(module=self.module, title="Preview Topic", slug="preview-topic", order=1, is_previewable=True)
        self.topic_enroll_only = Topic.objects.create(module=self.module, title="Enroll Topic", slug="enroll-topic", order=2, is_previewable=False)
        self.topic_quiz = Topic.objects.create(module=self.module, title="Quiz Topic", slug="quiz-topic", order=3, content_type='quiz', is_previewable=False)
        Quiz.objects.create(topic=self.topic_quiz, pass_mark_percentage=70)


        self.detail_url_preview = reverse('courses:topic-detail', kwargs={'slug': self.topic_previewable.slug})
        self.detail_url_enroll = reverse('courses:topic-detail', kwargs={'slug': self.topic_enroll_only.slug})
        self.complete_url_enroll = reverse('courses:topic-complete', kwargs={'slug': self.topic_enroll_only.slug})
        self.uncomplete_url_enroll = reverse('courses:topic-uncomplete', kwargs={'slug': self.topic_enroll_only.slug})
        self.submit_quiz_url = reverse('courses:submit-quiz', kwargs={'topic_slug': self.topic_quiz.slug})


    def test_retrieve_previewable_topic_unauthenticated(self):
        response = self.client.get(self.detail_url_preview)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.topic_previewable.title)

    def test_retrieve_enroll_only_topic_unauthenticated_fails(self):
        response = self.client.get(self.detail_url_enroll)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED) # IsEnrolledOrPreviewable requires auth if not previewable

    def test_retrieve_enroll_only_topic_authenticated_not_enrolled_fails(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(self.detail_url_enroll)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # Not enrolled

    def test_retrieve_enroll_only_topic_authenticated_enrolled_succeeds(self):
        UserCourseEnrollment.objects.create(user=self.student, course=self.course)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(self.detail_url_enroll)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.topic_enroll_only.title)

    def test_mark_topic_complete_enrolled_succeeds(self):
        enrollment = UserCourseEnrollment.objects.create(user=self.student, course=self.course)
        self.client.force_authenticate(user=self.student)
        response = self.client.post(self.complete_url_enroll)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        attempt = UserTopicAttempt.objects.get(enrollment=enrollment, topic=self.topic_enroll_only)
        self.assertTrue(attempt.is_completed)
        enrollment.refresh_from_db() # Check progress update
        # Assuming this is the only topic for simplicity of progress check, or check specific percentage
        # self.assertEqual(enrollment.progress_percentage, 100 / self.module.topics.count())


    def test_mark_topic_complete_quiz_not_passed_fails(self):
        UserCourseEnrollment.objects.create(user=self.student, course=self.course)
        self.client.force_authenticate(user=self.student)
        complete_quiz_topic_url = reverse('courses:topic-complete', kwargs={'slug': self.topic_quiz.slug})
        response = self.client.post(complete_quiz_topic_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must pass the quiz", response.data['detail'].lower())

    # More tests: uncomplete, quiz submission success/failure, etc.

class ReviewViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email="reviewer1@example.com", password="password")
        self.user2 = User.objects.create_user(email="reviewer2@example.com", password="password")
        self.course = Course.objects.create(title="Review Course", description_html="Desc", is_published=True, published_date=timezone.now())
        self.review1_user1 = Review.objects.create(course=self.course, user=self.user1, rating=5, comment="Great!")

        self.list_create_url = reverse('courses:course-reviews-list', kwargs={'course_slug_from_url': self.course.slug})
        self.detail_url_review1 = reverse('courses:review-detail', kwargs={'pk': self.review1_user1.pk})

    def test_list_reviews_for_course(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['rating'], 5)

    def test_create_review_enrolled_user_success(self):
        UserCourseEnrollment.objects.create(user=self.user2, course=self.course) # user2 is enrolled
        self.client.force_authenticate(user=self.user2)
        data = {"rating": 4, "comment": "Good stuff."}
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Review.objects.filter(user=self.user2, course=self.course).exists())
        self.course.refresh_from_db()
        self.assertAlmostEqual(self.course.average_rating, (5+4)/2.0) # Check signal updated rating

    def test_create_review_not_enrolled_fails(self):
        self.client.force_authenticate(user=self.user2) # user2 is NOT enrolled
        data = {"rating": 3, "comment": "Okay."}
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_review_already_reviewed_fails(self):
        UserCourseEnrollment.objects.create(user=self.user1, course=self.course) # user1 already reviewed
        self.client.force_authenticate(user=self.user1)
        data = {"rating": 1, "comment": "Trying again."}
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # ValidationError from view/serializer

    def test_update_own_review_succeeds(self):
        self.client.force_authenticate(user=self.user1)
        data = {"rating": 3, "comment": "Actually, it's just okay."}
        response = self.client.put(self.detail_url_review1, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.review1_user1.refresh_from_db()
        self.assertEqual(self.review1_user1.rating, 3)
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 3.0) # Signal should update

    def test_update_others_review_fails(self):
        self.client.force_authenticate(user=self.user2) # user2 is not author of review1
        data = {"rating": 1}
        response = self.client.put(self.detail_url_review1, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_review_succeeds(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.delete(self.detail_url_review1)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.filter(pk=self.review1_user1.pk).exists())
        self.course.refresh_from_db()
        self.assertEqual(self.course.average_rating, 0.0) # Signal should update

class MyCoursesViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="mycourses@example.com", password="password")
        self.course1 = Course.objects.create(title="C1", description_html="D1", is_published=True, published_date=timezone.now())
        self.course2 = Course.objects.create(title="C2", description_html="D2", is_published=True, published_date=timezone.now())
        Course.objects.create(title="C3 - Not Enrolled", description_html="D3", is_published=True, published_date=timezone.now())
        UserCourseEnrollment.objects.create(user=self.user, course=self.course1)
        UserCourseEnrollment.objects.create(user=self.user, course=self.course2)
        self.list_url = reverse('courses:mycourses-list')

    def test_list_my_courses_authenticated(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        course_titles = {item['course']['title'] for item in response.data['results']}
        self.assertIn(self.course1.title, course_titles)
        self.assertIn(self.course2.title, course_titles)

    def test_list_my_courses_unauthenticated(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class QuizSubmissionViewTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="quiztaker@example.com", password="password")
        self.course = Course.objects.create(title="Quiz Course For Submission", description_html="...")
        self.module = Module.objects.create(course=self.course, title="Quiz Module Sub", order=1)
        self.topic_quiz = Topic.objects.create(module=self.module, title="The Actual Quiz", slug="the-actual-quiz", order=1, content_type='quiz')
        self.quiz = Quiz.objects.create(topic=self.topic_quiz, pass_mark_percentage=60)
        
        self.q1 = Question.objects.create(quiz=self.quiz, text="Q1: 2+2?", question_type='single_choice', order=1, points=10)
        self.q1_opt_correct = AnswerOption.objects.create(question=self.q1, text="4", is_correct=True)
        self.q1_opt_wrong = AnswerOption.objects.create(question=self.q1, text="5", is_correct=False)

        self.q2 = Question.objects.create(quiz=self.quiz, text="Q2: Capitals?", question_type='multiple_choice', order=2, points=20)
        self.q2_opt_paris = AnswerOption.objects.create(question=self.q2, text="Paris", is_correct=True)
        self.q2_opt_london = AnswerOption.objects.create(question=self.q2, text="London", is_correct=True)
        self.q2_opt_berlin = AnswerOption.objects.create(question=self.q2, text="Berlin", is_correct=False) # Wrong for this MC example

        self.enrollment = UserCourseEnrollment.objects.create(user=self.student, course=self.course)
        self.submit_url = reverse('courses:submit-quiz', kwargs={'topic_slug': self.topic_quiz.slug})
        self.client.force_authenticate(user=self.student)

    def test_submit_quiz_correct_answers_pass(self):
        submission_data = {
            "answers": [
                {"question_id": str(self.q1.id), "answer_option_ids": [str(self.q1_opt_correct.id)]},
                {"question_id": str(self.q2.id), "answer_option_ids": [str(self.q2_opt_paris.id), str(self.q2_opt_london.id)]}
            ]
        }
        response = self.client.post(self.submit_url, submission_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['passed'])
        self.assertAlmostEqual(response.data['score_percentage'], 100.0)
        self.assertEqual(response.data['total_score_achieved'], 30) # 10 + 20
        
        attempt = UserTopicAttempt.objects.get(enrollment=self.enrollment, topic=self.topic_quiz)
        self.assertTrue(attempt.passed)
        self.assertTrue(attempt.is_completed) # Quiz completion marks topic complete
        self.assertAlmostEqual(attempt.score, 100.0)
        self.assertIsNotNone(attempt.answer_history_json)

    def test_submit_quiz_partially_correct_answers_fail_if_below_pass_mark(self):
        submission_data = {
            "answers": [
                {"question_id": str(self.q1.id), "answer_option_ids": [str(self.q1_opt_wrong.id)]}, # 0 points
                {"question_id": str(self.q2.id), "answer_option_ids": [str(self.q2_opt_paris.id)]}      # MC needs both, so 0 points
            ]
        }
        # Max score = 30. Current score = 0. Pass mark 60%. 0/30 = 0% -> Fail
        response = self.client.post(self.submit_url, submission_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(response.data['passed'])
        self.assertAlmostEqual(response.data['score_percentage'], 0.0)
        self.assertEqual(response.data['total_score_achieved'], 0)
        
        attempt = UserTopicAttempt.objects.get(enrollment=self.enrollment, topic=self.topic_quiz)
        self.assertFalse(attempt.passed)
        self.assertFalse(attempt.is_completed)

    def test_submit_quiz_not_enrolled_fails(self):
        other_user = User.objects.create_user(email="nonenrolled@example.com", password="pw")
        client_other = APIClient()
        client_other.force_authenticate(user=other_user)
        submission_data = {"answers": [{"question_id": str(self.q1.id), "answer_option_ids": [str(self.q1_opt_correct.id)]}]}
        response = client_other.post(self.submit_url, submission_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsEnrolled permission

    def test_submit_quiz_invalid_payload_empty_answers(self):
        submission_data = {"answers": []}
        response = self.client.post(self.submit_url, submission_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("answers", response.data)
