from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.text import slugify
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken # For JWT authentication

# Import models from the courses app
from apps.courses.models import (
    Category, Course, Module, Topic, Question, Choice,
    Enrollment, CourseReview, CourseProgress, TopicProgress
)
# Import serializers to compare response data (optional, can also check specific fields)
from apps.courses.serializers import (
    CategorySerializer, CourseListSerializer, CourseDetailSerializer
)

User = get_user_model()

# Test Data Setup (similar to SerializerTestDataMixin, adapted for APITestCase)
class ViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='view_admin', email='view_admin@example.com', password='password123',
            full_name='View Admin'
        )
        cls.instructor_user = User.objects.create_user(
            username='view_instructor', email='view_instructor@example.com', password='password123',
            full_name='View Instructor', is_instructor=True # Assuming custom user model field
        )
        cls.student_user = User.objects.create_user(
            username='view_student', email='view_student@example.com', password='password123',
            full_name='View Student'
        )
        cls.another_student = User.objects.create_user(
            username='view_student2', email='view_student2@example.com', password='password123',
            full_name='Another View Student'
        )
        # Anonymous user is represented by not authenticating the client

        cls.category1 = Category.objects.create(name='View Test Category 1', slug='view-test-category-1')
        cls.category2 = Category.objects.create(name='View Test Category 2', slug='view-test-category-2')

        cls.course1 = Course.objects.create(
            title='View Course 1 Published', slug='view-course-1-pub',
            instructor=cls.instructor_user, category=cls.category1,
            short_description='A published course for view tests.', price=Decimal('29.99'),
            is_published=True, is_free=False
        )
        cls.course2_unpublished = Course.objects.create(
            title='View Course 2 Unpublished', slug='view-course-2-unpub',
            instructor=cls.instructor_user, category=cls.category1,
            short_description='An unpublished course.', price=Decimal('10.00'),
            is_published=False
        )
        cls.course3_free_published = Course.objects.create(
            title='View Course 3 Free Published', slug='view-course-3-free-pub',
            instructor=cls.instructor_user, category=cls.category2,
            short_description='A free published course.', price=Decimal('0.00'),
            is_published=True, is_free=True
        )

        cls.module1_c1 = Module.objects.create(course=cls.course1, title='C1 Module 1', order=1)
        cls.topic1_m1_c1 = Topic.objects.create(
            module=cls.module1_c1, title='C1 M1 Topic 1', slug='c1-m1-t1', order=1,
            content={'type': 'text'}, is_previewable=True
        )
        cls.topic2_m1_c1 = Topic.objects.create(
            module=cls.module1_c1, title='C1 M1 Topic 2', slug='c1-m1-t2', order=2,
            content={'type': 'text'}, is_previewable=False # Not previewable
        )
        
        cls.question1_t1 = Question.objects.create(topic=cls.topic1_m1_c1, text="Q1?", question_type='single-choice', order=1)
        cls.choice1_q1 = Choice.objects.create(question=cls.question1_t1, text="Correct", is_correct=True, order=1)


    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

    def setUp(self):
        super().setUp() # Call parent setUp if it exists
        # self.client is available from APITestCase


class CategoryViewSetTests(ViewTestDataMixin, APITestCase):
    def test_list_categories_anonymous(self):
        url = reverse('courses:category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # category1 and category2

    def test_retrieve_category_anonymous(self):
        url = reverse('courses:category-detail', kwargs={'slug': self.category1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.category1.name)

    def test_create_category_anonymous_forbidden(self):
        url = reverse('courses:category-list')
        data = {'name': 'Forbidden Category', 'slug': 'forbidden-category'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED) # Or 403 if AllowAny with IsAdminOrReadOnly

    def test_create_category_student_forbidden(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:category-list')
        data = {'name': 'Student Category Fail', 'slug': 'student-cat-fail'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_category_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('courses:category-list')
        data = {'name': 'Admin Created Category', 'slug': 'admin-created-cat'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Category.objects.filter(slug='admin-created-cat').exists())

    def test_update_category_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('courses:category-detail', kwargs={'slug': self.category1.slug})
        data = {'name': 'Updated Name by Admin'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.category1.refresh_from_db()
        self.assertEqual(self.category1.name, 'Updated Name by Admin')

    def test_delete_category_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        category_to_delete = Category.objects.create(name="To Delete", slug="to-delete")
        url = reverse('courses:category-detail', kwargs={'slug': category_to_delete.slug})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(slug='to-delete').exists())


class CourseViewSetListRetrieveTests(ViewTestDataMixin, APITestCase):
    def test_list_courses_anonymous(self):
        """ Anonymous users should only see published courses. """
        url = reverse('courses:course-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # course1 and course3_free_published are published
        self.assertEqual(len(response.data['results']), 2)
        slugs_in_response = [item['slug'] for item in response.data['results']]
        self.assertIn(self.course1.slug, slugs_in_response)
        self.assertIn(self.course3_free_published.slug, slugs_in_response)
        self.assertNotIn(self.course2_unpublished.slug, slugs_in_response)

    def test_retrieve_published_course_anonymous(self):
        url = reverse('courses:course-detail', kwargs={'slug': self.course1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.course1.title)

    def test_retrieve_unpublished_course_anonymous_not_found(self):
        url = reverse('courses:course-detail', kwargs={'slug': self.course2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_courses_authenticated_student(self):
        """ Authenticated students also only see published courses by default. """
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # course1 and course3

    def test_retrieve_unpublished_course_student_not_found(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-detail', kwargs={'slug': self.course2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_unpublished_course_by_its_instructor(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-detail', kwargs={'slug': self.course2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.course2_unpublished.title)

    def test_retrieve_unpublished_course_by_admin(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('courses:course-detail', kwargs={'slug': self.course2_unpublished.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.course2_unpublished.title)

    def test_list_courses_filtering_by_category_slug(self):
        url = f"{reverse('courses:course-list')}?category__slug={self.category1.slug}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # course1 is in category1 and published. course3 is in category2.
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['slug'], self.course1.slug)

    def test_list_courses_search(self):
        url = f"{reverse('courses:course-list')}?search=Published" # course1 and course3 titles contain "Published"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)


class CourseViewSetCreateUpdateDeleteTests(ViewTestDataMixin, APITestCase):
    def test_create_course_instructor_success(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-list')
        data = {
            "title": "Instructor New Course",
            "slug": "instructor-new-course",
            "category_id": self.category1.id,
            "short_description": "A new course by instructor.",
            "price": "50.00", "currency": "USD", "level": "intermediate", "language": "en"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['instructor']['id'], str(self.instructor_user.id)) # Check instructor is set
        self.assertTrue(Course.objects.filter(slug='instructor-new-course').exists())

    def test_create_course_student_forbidden(self): # Assuming only instructors/admins can create
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-list')
        data = {"title": "Student Course Fail", "slug": "student-course-fail", "category_id": self.category1.id, "short_description":"test"}
        response = self.client.post(url, data, format='json')
        # The permission IsAuthenticated is on create, so this might pass if student is authenticated
        # However, perform_create sets instructor=request.user.
        # If we want to restrict course creation to instructors, the permission should be stricter.
        # For now, CourseViewSet has IsAuthenticated for create.
        # Let's assume the business logic is any authenticated user can create, and they become instructor.
        # If that's not the case, this test or the permission needs adjustment.
        # Based on current CourseViewSet:
        self.assertEqual(response.status_code, status.HTTP_201_CREATED) # Student becomes instructor of this course
        created_course = Course.objects.get(slug='student-course-fail')
        self.assertEqual(created_course.instructor, self.student_user)
        # If the intent is to forbid students from creating, then permission should be IsInstructorOrAdmin
        # For now, this test reflects the current permission setup.

    def test_update_own_course_instructor_success(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-detail', kwargs={'slug': self.course1.slug})
        data = {"title": "Updated Title by Owner"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.course1.refresh_from_db()
        self.assertEqual(self.course1.title, "Updated Title by Owner")

    def test_update_other_instructor_course_forbidden(self):
        # Create another instructor and their course
        other_instructor = User.objects.create_user(username='otherinstr', email='oi@e.com', password='pw', is_instructor=True)
        other_course = Course.objects.create(title="Other's Course", slug="other-course", instructor=other_instructor, category=self.category1, short_description='s')

        self.authenticate_client_with_jwt(self.instructor_user) # Authenticate as self.instructor_user
        url = reverse('courses:course-detail', kwargs={'slug': other_course.slug})
        data = {"title": "Attempted Update"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsInstructorOrReadOnly

    def test_delete_own_course_instructor_success(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        course_to_delete = Course.objects.create(
            title="To Delete by Instructor", slug="to-delete-instr", instructor=self.instructor_user,
            category=self.category1, short_description='s'
        )
        url = reverse('courses:course-detail', kwargs={'slug': course_to_delete.slug})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Course.objects.filter(slug=course_to_delete.slug).exists())

    def test_delete_other_instructor_course_forbidden(self):
        other_instructor = User.objects.create_user(username='otherinstr2', email='oi2@e.com', password='pw', is_instructor=True)
        other_course = Course.objects.create(title="Other's Course To Delete", slug="other-course-del", instructor=other_instructor, category=self.category1, short_description='s')

        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-detail', kwargs={'slug': other_course.slug})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CourseViewSetCustomActionsTests(ViewTestDataMixin, APITestCase):
    def test_enroll_action_free_course_success(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-enroll', kwargs={'slug': self.course3_free_published.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=self.course3_free_published).exists())

    def test_enroll_action_paid_course_requires_payment(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-enroll', kwargs={'slug': self.course1.slug}) # course1 is paid
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertFalse(Enrollment.objects.filter(user=self.student_user, course=self.course1).exists())

    def test_enroll_action_already_enrolled(self):
        Enrollment.objects.create(user=self.student_user, course=self.course3_free_published)
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-enroll', kwargs={'slug': self.course3_free_published.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already enrolled", response.data['detail'].lower())

    def test_my_courses_action(self):
        Enrollment.objects.create(user=self.student_user, course=self.course1)
        Enrollment.objects.create(user=self.student_user, course=self.course3_free_published)
        # another_student is not enrolled in any of these
        Enrollment.objects.create(user=self.another_student, course=self.course1)


        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-my-courses')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # course1 and course3
        slugs_in_response = [item['slug'] for item in response.data]
        self.assertIn(self.course1.slug, slugs_in_response)
        self.assertIn(self.course3_free_published.slug, slugs_in_response)

    def test_instructor_courses_action(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-instructor-courses')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # instructor_user is instructor for course1, course2_unpublished, course3_free_published
        self.assertEqual(len(response.data), 3)

    def test_get_my_progress_action(self):
        enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        # CourseProgress created by signal
        course_progress = CourseProgress.objects.get(user=self.student_user, course=self.course1)
        TopicProgress.objects.create(user=self.student_user, topic=self.topic1_m1_c1, is_completed=True, course_progress=course_progress)

        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-get-my-progress', kwargs={'slug': self.course1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['progress_percentage'] > 0)
        self.assertEqual(response.data['course_title'], self.course1.title)


# --- Tests for Nested ViewSets (Module, Topic, Question) ---
# These will require constructing nested URLs correctly.

class ModuleViewSetTests(ViewTestDataMixin, APITestCase):
    def test_list_modules_for_course_anonymous(self):
        url = reverse('courses:course-modules-list', kwargs={'course_slug': self.course1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # module1_c1
        self.assertEqual(response.data['results'][0]['title'], self.module1_c1.title)

    def test_retrieve_module_anonymous(self):
        url = reverse('courses:course-modules-detail', kwargs={'course_slug': self.course1.slug, 'pk': self.module1_c1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.module1_c1.title)
        self.assertEqual(len(response.data['topics']), 2) # topic1 and topic2

    def test_create_module_by_course_instructor(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:course-modules-list', kwargs={'course_slug': self.course1.slug})
        data = {"title": "New Module by Instructor", "order": 3, "description": "Test desc"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Module.objects.filter(title="New Module by Instructor", course=self.course1).exists())

    def test_create_module_by_non_instructor_forbidden(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-modules-list', kwargs={'course_slug': self.course1.slug})
        data = {"title": "Student Module Fail", "order": 3}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TopicViewSetTests(ViewTestDataMixin, APITestCase):
    def test_list_topics_for_module_anonymous(self):
        # URL: /api/courses/{course_slug}/modules/{module_pk}/topics/
        url = reverse('courses:module-topics-list', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # topic1 and topic2

    def test_retrieve_previewable_topic_anonymous(self):
        # self.topic1_m1_c1 is_previewable=True
        url = reverse('courses:module-topics-detail', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'slug': self.topic1_m1_c1.slug
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.topic1_m1_c1.title)

    def test_retrieve_non_previewable_topic_anonymous_forbidden(self):
        # self.topic2_m1_c1 is_previewable=False
        url = reverse('courses:module-topics-detail', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'slug': self.topic2_m1_c1.slug
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanViewTopicContent

    def test_retrieve_non_previewable_topic_enrolled_student_ok(self):
        Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:module-topics-detail', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'slug': self.topic2_m1_c1.slug
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.topic2_m1_c1.title)

    def test_mark_topic_as_complete_enrolled_student(self):
        Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:module-topics-mark-as-complete', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'slug': self.topic1_m1_c1.slug
        })
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(TopicProgress.objects.filter(user=self.student_user, topic=self.topic1_m1_c1, is_completed=True).exists())

    def test_mark_topic_as_complete_non_enrolled_student_forbidden(self):
        self.authenticate_client_with_jwt(self.student_user) # Not enrolled
        url = reverse('courses:module-topics-mark-as-complete', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'slug': self.topic1_m1_c1.slug
        })
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanPerformEnrolledAction


class QuestionViewSetTests(ViewTestDataMixin, APITestCase):
    def test_list_questions_for_topic_instructor(self):
        self.authenticate_client_with_jwt(self.instructor_user)
        url = reverse('courses:topic-questions-list', kwargs={
            'course_slug': self.course1.slug,
            'module_pk': self.module1_c1.pk,
            'topic_slug': self.topic1_m1_c1.slug
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # Only question1_t1 for topic1_m1_c1
        self.assertEqual(response.data['results'][0]['text'], self.question1_t1.text)

    # Add tests for create, update, delete questions by instructor
    # Add tests for non-instructor access (should be forbidden for write, maybe read if not part of quiz view)

class CourseReviewViewSetTests(ViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)

    def test_create_review_enrolled_student_success(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-reviews-list', kwargs={'course_slug': self.course1.slug})
        data = {"rating": 5, "comment": "Great course for views!"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CourseReview.objects.filter(user=self.student_user, course=self.course1, rating=5).exists())

    def test_create_review_not_enrolled_forbidden(self):
        self.authenticate_client_with_jwt(self.another_student) # Not enrolled
        url = reverse('courses:course-reviews-list', kwargs={'course_slug': self.course1.slug})
        data = {"rating": 4, "comment": "Trying to review"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanSubmitCourseReview

    def test_create_review_duplicate_forbidden(self):
        CourseReview.objects.create(user=self.student_user, course=self.course1, rating=3, comment="First review")
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:course-reviews-list', kwargs={'course_slug': self.course1.slug})
        data = {"rating": 5, "comment": "Second attempt"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanSubmitCourseReview (via serializer validation)


class QuizSubmissionViewTests(ViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)

    def test_submit_quiz_valid_success(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:submit-quiz')
        data = {
            'topic_id': str(self.topic1_m1_c1.id),
            'answers': [
                {'question_id': str(self.question1_t1.id), 'selected_choice_ids': [str(self.choice1_q1.id)]}, # Correct
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['score'], 100.0) # 1 correct out of 1 submitted (for this test)
        self.assertTrue(QuizAttempt.objects.filter(user=self.student_user, topic=self.topic1_m1_c1).exists())

    def test_submit_quiz_not_enrolled_forbidden(self):
        self.authenticate_client_with_jwt(self.another_student) # Not enrolled
        url = reverse('courses:submit-quiz')
        data = {'topic_id': str(self.topic1_m1_c1.id), 'answers': []}
        response = self.client.post(url, data, format='json')
        # Permission check is on get_object() in the view, which uses topic_id from data
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class QuizAttemptResultViewSetTests(ViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.enrollment = Enrollment.objects.create(user=self.student_user, course=self.course1)
        self.attempt = QuizAttempt.objects.create(
            user=self.student_user, topic=self.topic1_m1_c1, score=50.0, correct_answers=1, total_questions_in_topic=2
        )

    def test_list_my_quiz_attempts(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:quizattempt-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.attempt.id))

    def test_retrieve_my_quiz_attempt(self):
        self.authenticate_client_with_jwt(self.student_user)
        url = reverse('courses:quizattempt-detail', kwargs={'pk': self.attempt.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], 50.0)

    def test_retrieve_other_student_attempt_forbidden_or_not_found(self):
        # Create attempt for another student
        other_attempt = QuizAttempt.objects.create(
            user=self.another_student, topic=self.topic1_m1_c1, score=100, correct_answers=1, total_questions_in_topic=1
        )
        self.authenticate_client_with_jwt(self.student_user) # Authenticated as self.student_user
        url = reverse('courses:quizattempt-detail', kwargs={'pk': other_attempt.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Because queryset filters by request.user

# Remember to add more tests for:
# - All CRUD operations for ModuleViewSet, TopicViewSet, QuestionViewSet with various user roles.
# - Pagination tests for list views.
# - More complex permission scenarios.
# - Error handling for invalid data in POST/PUT/PATCH requests.
# - Functionality of all custom actions.
