from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType # For Like/Report tests

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.community.models import (
    Forum, Thread, Post, Comment, Like, Report
)
# Import serializers to compare response data (optional, can also check specific fields)
from apps.community.serializers import (
    ForumListSerializer, ForumDetailSerializer,
    ThreadListSerializer, ThreadDetailSerializer, PostSerializer
)

User = get_user_model()

# Test Data Setup Mixin (adapted for APITestCase)
class CommunityViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='comview_admin', email='comview_admin@example.com', password='password123',
            full_name='ComView Admin'
        )
        cls.user1 = User.objects.create_user(
            username='comview_user1', email='comview_user1@example.com', password='password123',
            full_name='ComView User One'
        )
        cls.user2 = User.objects.create_user(
            username='comview_user2', email='comview_user2@example.com', password='password123',
            full_name='ComView User Two'
        )
        # cls.moderator_user is effectively admin_user if moderators are staff

        cls.forum1 = Forum.objects.create(name='View Test Forum Alpha', slug='view-test-forum-alpha', display_order=0)
        cls.forum2 = Forum.objects.create(name='View Test Forum Beta', slug='view-test-forum-beta', display_order=1)

        cls.thread1_forum1_user1 = Thread.objects.create(
            forum=cls.forum1, author=cls.user1,
            title='Thread Alpha by User1', slug='thread-alpha-user1',
            content='Content for thread alpha.'
        )
        cls.thread2_forum1_user2 = Thread.objects.create(
            forum=cls.forum1, author=cls.user2,
            title='Thread Beta by User2', slug='thread-beta-user2',
            content='Content for thread beta.', is_closed=True # A closed thread
        )
        cls.thread3_forum2_user1_hidden = Thread.objects.create(
            forum=cls.forum2, author=cls.user1,
            title='Hidden Thread Gamma by User1', slug='hidden-thread-gamma-user1',
            content='This thread is hidden.', is_hidden=True
        )
        
        cls.post1_thread1_user2 = Post.objects.create(
            thread=cls.thread1_forum1_user1, author=cls.user2,
            content="User2's reply to thread alpha."
        )


    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {'refresh': str(refresh), 'access': str(refresh.access_token)}

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

    def setUp(self):
        super().setUp() # Call parent setUp if it exists


class ForumViewSetTests(CommunityViewTestDataMixin, APITestCase):
    def test_list_forums_anonymous(self):
        url = reverse('community:forum-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # forum1 and forum2

    def test_retrieve_forum_anonymous(self):
        url = reverse('community:forum-detail', kwargs={'slug': self.forum1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.forum1.name)

    def test_create_forum_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:forum-list')
        data = {'name': 'Admin Forum Gamma', 'slug': 'admin-forum-gamma', 'description': 'Admin created.'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Forum.objects.filter(slug='admin-forum-gamma').exists())

    def test_create_forum_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:forum-list')
        data = {'name': 'User1 Forum Fail', 'slug': 'user1-forum-fail'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAdminOrReadOnly

    def test_update_forum_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:forum-detail', kwargs={'slug': self.forum1.slug})
        data = {'name': 'View Test Forum Alpha (Updated)'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.forum1.refresh_from_db()
        self.assertEqual(self.forum1.name, 'View Test Forum Alpha (Updated)')

    def test_delete_forum_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        forum_to_delete = Forum.objects.create(name="To Delete Forum", slug="to-delete-forum")
        url = reverse('community:forum-detail', kwargs={'slug': forum_to_delete.slug})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Forum.objects.filter(slug='to-delete-forum').exists())


class ThreadViewSetTests(CommunityViewTestDataMixin, APITestCase):
    # Test listing threads (top-level and nested under forum)
    def test_list_threads_top_level_anonymous(self):
        """ Anonymous users see non-hidden threads. """
        url = reverse('community:thread-global-list') # Using the top-level registration
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # thread1_forum1_user1, thread2_forum1_user2 are not hidden
        # thread3_forum2_user1_hidden is hidden
        self.assertEqual(len(response.data['results']), 2)
        slugs_in_response = [item['slug'] for item in response.data['results']]
        self.assertIn(self.thread1_forum1_user1.slug, slugs_in_response)
        self.assertIn(self.thread2_forum1_user2.slug, slugs_in_response)
        self.assertNotIn(self.thread3_forum2_user1_hidden.slug, slugs_in_response)

    def test_list_threads_nested_under_forum_anonymous(self):
        url = reverse('community:forum-thread-list', kwargs={'forum_slug': self.forum1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # thread1 and thread2 in forum1
        self.assertEqual(response.data['results'][0]['slug'], self.thread1_forum1_user1.slug) # Ordered by last_activity (default) or pinned

    def test_list_hidden_threads_by_admin_top_level(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:thread-global-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3) # Admin sees all, including hidden

    # Test retrieving threads
    def test_retrieve_thread_anonymous(self):
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread1_forum1_user1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.thread1_forum1_user1.title)
        self.assertEqual(response.data['view_count'], 1) # View count incremented

    def test_retrieve_hidden_thread_anonymous_forbidden(self):
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread3_forum2_user1_hidden.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAuthorOrReadOnly (object perm)

    def test_retrieve_hidden_thread_by_author(self):
        self.authenticate_client_with_jwt(self.user1) # user1 is author of hidden thread
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread3_forum2_user1_hidden.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_hidden_thread_by_admin(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread3_forum2_user1_hidden.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # Test creating threads
    def test_create_thread_authenticated_user_success(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('community:forum-thread-list', kwargs={'forum_slug': self.forum2.slug}) # Create in forum2
        data = {
            "title": "User2 New Thread in Forum2",
            "content": "Exciting content here!",
            # Slug should be auto-generated by serializer if not provided
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_thread_slug = slugify("User2 New Thread in Forum2")
        self.assertTrue(Thread.objects.filter(slug=new_thread_slug, author=self.user2, forum=self.forum2).exists())

    def test_create_thread_unauthenticated_forbidden(self):
        url = reverse('community:forum-thread-list', kwargs={'forum_slug': self.forum1.slug})
        data = {"title": "Anon Thread Fail", "content": "test"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED) # IsAuthenticated

    # Test updating threads
    def test_update_own_thread_by_author_success(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread1_forum1_user1.slug})
        data = {"title": "Thread Alpha by User1 (Updated)", "content": "Updated content."}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.thread1_forum1_user1.refresh_from_db()
        self.assertEqual(self.thread1_forum1_user1.title, "Thread Alpha by User1 (Updated)")

    def test_update_other_user_thread_forbidden(self):
        self.authenticate_client_with_jwt(self.user2) # user2 trying to update user1's thread
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread1_forum1_user1.slug})
        data = {"title": "Attempted Update by User2"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAuthorOrReadOnly

    def test_update_thread_by_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:thread-global-detail', kwargs={'slug': self.thread1_forum1_user1.slug})
        data = {"title": "Thread Alpha (Admin Update)", "is_pinned": True}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thread1_forum1_user1.refresh_from_db()
        self.assertTrue(self.thread1_forum1_user1.is_pinned)

    # Test deleting threads
    def test_delete_own_thread_by_author_success(self):
        self.authenticate_client_with_jwt(self.user1)
        thread_to_delete = Thread.objects.create(forum=self.forum1, author=self.user1, title="To Delete", slug="to-delete", content="c")
        url = reverse('community:thread-global-detail', kwargs={'slug': thread_to_delete.slug})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Thread.objects.filter(slug=thread_to_delete.slug).exists())

    # Test moderator actions on threads
    def test_pin_thread_by_moderator_success(self):
        self.authenticate_client_with_jwt(self.admin_user) # admin_user is moderator
        url = reverse('community:thread-global-pin-thread', kwargs={'slug': self.thread1_forum1_user1.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thread1_forum1_user1.refresh_from_db()
        self.assertTrue(self.thread1_forum1_user1.is_pinned)

    def test_pin_thread_by_non_moderator_forbidden(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:thread-global-pin-thread', kwargs={'slug': self.thread1_forum1_user1.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsModeratorOrAdmin

    def test_close_thread_by_moderator_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:thread-global-close-thread', kwargs={'slug': self.thread1_forum1_user1.slug})
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thread1_forum1_user1.refresh_from_db()
        self.assertTrue(self.thread1_forum1_user1.is_closed)


class PostViewSetTests(CommunityViewTestDataMixin, APITestCase):
    def test_list_posts_for_thread_anonymous(self):
        # URL: /api/community/forums/{forum_slug}/threads/{thread_slug_or_pk}/posts/
        url = reverse('community:thread-post-list', kwargs={
            'forum_slug': self.forum1.slug,
            'thread_slug': self.thread1_forum1_user1.slug # Assuming ThreadViewSet lookup is 'slug'
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # post1_thread1_user2
        self.assertEqual(response.data['results'][0]['content'], self.post1_thread1_user2.content)

    def test_create_post_in_thread_authenticated_user_success(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:thread-post-list', kwargs={
            'forum_slug': self.forum1.slug,
            'thread_slug': self.thread1_forum1_user1.slug
        })
        data = {"content": "User1's new reply to thread alpha."}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Post.objects.filter(thread=self.thread1_forum1_user1, author=self.user1, content=data['content']).exists())
        self.thread1_forum1_user1.refresh_from_db()
        self.assertEqual(self.thread1_forum1_user1.reply_count, 2) # Original post1 + this new one

    def test_create_post_in_closed_thread_forbidden(self):
        self.authenticate_client_with_jwt(self.user1)
        # self.thread2_forum1_user2 is closed
        url = reverse('community:thread-post-list', kwargs={
            'forum_slug': self.forum1.slug,
            'thread_slug': self.thread2_forum1_user2.slug # Closed thread
        })
        data = {"content": "Trying to reply to closed thread."}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanCreateThreadOrPost (via serializer validation or permission)

    def test_update_own_post_by_author_success(self):
        # user2 is author of post1_thread1_user2
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('community:thread-post-detail', kwargs={
            'forum_slug': self.forum1.slug,
            'thread_slug': self.thread1_forum1_user1.slug,
            'pk': self.post1_thread1_user2.pk
        })
        data = {"content": "User2's reply (updated)."}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.post1_thread1_user2.refresh_from_db()
        self.assertEqual(self.post1_thread1_user2.content, "User2's reply (updated).")


class LikeToggleAPIViewTests(CommunityViewTestDataMixin, APITestCase):
    def test_like_thread_success(self):
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('community:like-toggle')
        data = {"content_type_model": "thread", "object_id": str(self.thread1_forum1_user1.id)}
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['liked'])
        self.thread1_forum1_user1.refresh_from_db()
        self.assertEqual(self.thread1_forum1_user1.like_count, 1)

    def test_unlike_thread_success(self):
        # First, like the thread
        Like.objects.create(user=self.user2, content_object=self.thread1_forum1_user1)
        self.thread1_forum1_user1.refresh_from_db()
        self.assertEqual(self.thread1_forum1_user1.like_count, 1)

        self.authenticate_client_with_jwt(self.user2)
        url = reverse('community:like-toggle')
        data = {"content_type_model": "thread", "object_id": str(self.thread1_forum1_user1.id)}
        response = self.client.delete(url, data, format='json') # DELETE to unlike
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data) # Or 204
        self.assertFalse(response.data['liked'])
        self.thread1_forum1_user1.refresh_from_db()
        self.assertEqual(self.thread1_forum1_user1.like_count, 0)

    def test_like_already_liked_thread(self):
        Like.objects.create(user=self.user2, content_object=self.thread1_forum1_user1)
        self.authenticate_client_with_jwt(self.user2)
        url = reverse('community:like-toggle')
        data = {"content_type_model": "thread", "object_id": str(self.thread1_forum1_user1.id)}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK) # Already liked, returns OK
        self.assertTrue(response.data['liked'])

    def test_like_hidden_content_by_non_staff_forbidden(self):
        self.authenticate_client_with_jwt(self.user2) # Regular user
        url = reverse('community:like-toggle')
        data = {"content_type_model": "thread", "object_id": str(self.thread3_forum2_user1_hidden.id)}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanInteractWithContent


class ReportCreateAPIViewTests(CommunityViewTestDataMixin, APITestCase):
    def test_create_report_success(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:report-content-create')
        data = {
            "content_type_model": "post",
            "object_id": str(self.post1_thread1_user2.id),
            "reason": "This reply contains spam."
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Report.objects.filter(
            reporter=self.user1,
            object_id=self.post1_thread1_user2.id,
            reason="This reply contains spam."
        ).exists())

    def test_create_report_unauthenticated_forbidden(self):
        url = reverse('community:report-content-create')
        data = {"content_type_model": "post", "object_id": str(self.post1_thread1_user2.id), "reason": "test"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ReportViewSetAdminTests(CommunityViewTestDataMixin, APITestCase):
    def setUp(self):
        super().setUpTestData()
        self.report1 = Report.objects.create(
            reporter=self.user1, content_object=self.post1_thread1_user2,
            reason="Spam post", status='pending'
        )

    def test_list_reports_by_admin(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:report-admin-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 1)

    def test_list_reports_by_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.user1)
        url = reverse('community:report-admin-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanManageReport

    def test_update_report_status_by_admin(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('community:report-admin-update-status', kwargs={'pk': self.report1.pk})
        data = {"status": "resolved_action_taken", "moderator_notes": "User warned."}
        response = self.client.patch(url, data, format='json') # PATCH for custom action
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.report1.refresh_from_db()
        self.assertEqual(self.report1.status, "resolved_action_taken")
        self.assertEqual(self.report1.moderator_notes, "User warned.")
        self.assertEqual(self.report1.resolved_by, self.admin_user)

# TODO:
# - More tests for CommentViewSet if fully implemented.
# - Test all permissions thoroughly for each action and user type.
# - Test filtering, searching, ordering for ViewSets that support them.
# - Test pagination for list views.
# - Test error responses for invalid data in POST/PUT/PATCH more extensively.
# - Test behavior when trying to interact with content in hidden threads by non-staff.
