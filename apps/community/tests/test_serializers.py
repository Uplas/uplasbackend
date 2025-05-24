from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType
from uuid import uuid4

from rest_framework.test import APIRequestFactory # For providing request context
from rest_framework.exceptions import ValidationError

from apps.community.models import (
    Forum, Thread, Post, Comment, Like, Report
)
from apps.community.serializers import (
    ForumListSerializer, ForumDetailSerializer,
    ThreadListSerializer, ThreadDetailSerializer,
    PostSerializer, CommentSerializer,
    LikeSerializer, ReportSerializer,
    SimpleUserSerializer # Assuming this is defined in community.serializers or imported
)

User = get_user_model()

# Test Data Setup Mixin (adapted for serializer tests)
class CommunitySerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(
            username='comser_user1', email='comser_user1@example.com',
            password='password123', full_name='ComSer User One'
        )
        cls.user2 = User.objects.create_user(
            username='comser_user2', email='comser_user2@example.com',
            password='password123', full_name='ComSer User Two'
        )
        cls.moderator_user = User.objects.create_user(
            username='comser_moderator', email='comser_moderator@example.com',
            password='password123', full_name='ComSer Moderator', is_staff=True
        )

        cls.forum_general = Forum.objects.create(
            name='General Serializer Forum', slug='general-serializer-forum',
            description='For testing serializers.', display_order=0
        )
        # Thread signal updates forum_general.thread_count and post_count
        cls.thread1 = Thread.objects.create(
            forum=cls.forum_general, author=cls.user1,
            title='Thread for Serializer Test', slug='thread-serializer-test',
            content='Initial content for thread serializer test.'
        )
        # Post signal updates thread1.reply_count, last_activity_at and forum_general.post_count
        cls.post1_thread1 = Post.objects.create(
            thread=cls.thread1, author=cls.user2,
            content='A reply to test post serializer.'
        )
        cls.comment1_post1 = Comment.objects.create(
            post=cls.post1_thread1, author=cls.user1,
            content='A comment on the post.'
        )

        # For providing request context to serializers
        cls.factory = APIRequestFactory()

        # Mock requests with different users
        cls.request_user1 = cls.factory.get('/fake-community-endpoint')
        cls.request_user1.user = cls.user1
        cls.request_user1.method = 'GET' # Default, can be changed in tests

        cls.request_user2 = cls.factory.get('/fake-community-endpoint')
        cls.request_user2.user = cls.user2
        cls.request_user2.method = 'GET'

        cls.request_moderator = cls.factory.get('/fake-community-endpoint')
        cls.request_moderator.user = cls.moderator_user
        cls.request_moderator.method = 'GET'
        
        cls.request_anonymous = cls.factory.get('/fake-community-endpoint')
        # Simulate anonymous user by not setting request.user or using Django's AnonymousUser
        from django.contrib.auth.models import AnonymousUser
        cls.request_anonymous.user = AnonymousUser()
        cls.request_anonymous.method = 'GET'


class ForumSerializersTests(CommunitySerializerTestDataMixin, TestCase):
    def test_forum_list_serializer_output(self):
        self.forum_general.refresh_from_db() # Ensure counts are updated by signals
        serializer = ForumListSerializer(instance=self.forum_general)
        data = serializer.data
        self.assertEqual(data['name'], self.forum_general.name)
        self.assertEqual(data['slug'], self.forum_general.slug)
        self.assertEqual(data['thread_count'], 1) # thread1
        self.assertEqual(data['post_count'], 2) # thread1 content + post1_thread1

    def test_forum_detail_serializer_output(self):
        serializer = ForumDetailSerializer(instance=self.forum_general)
        data = serializer.data
        self.assertEqual(data['name'], self.forum_general.name)
        self.assertIn('created_at', data)

    def test_forum_detail_serializer_create_valid(self):
        data = {'name': 'New Tech Forum', 'slug': 'new-tech-forum', 'description': 'Discuss new tech.'}
        serializer = ForumDetailSerializer(data=data, context={'request': self.request_moderator}) # Admin context
        self.assertTrue(serializer.is_valid(), serializer.errors)
        forum = serializer.save()
        self.assertEqual(forum.name, 'New Tech Forum')

class ThreadSerializersTests(CommunitySerializerTestDataMixin, TestCase):
    def test_thread_list_serializer_output(self):
        # User1 likes their own thread
        Like.objects.create(user=self.user1, content_object=self.thread1)
        self.thread1.refresh_from_db() # For like_count

        serializer = ThreadListSerializer(instance=self.thread1, context={'request': self.request_user1})
        data = serializer.data
        self.assertEqual(data['title'], self.thread1.title)
        self.assertEqual(data['author']['username'], self.user1.username)
        self.assertEqual(data['forum_name'], self.forum_general.name)
        self.assertEqual(data['reply_count'], 1) # post1_thread1
        self.assertEqual(data['like_count'], 1)
        self.assertTrue(data['is_liked_by_user']) # user1 liked it
        self.assertTrue(data['user_can_edit']) # user1 is author

    def test_thread_detail_serializer_read(self):
        serializer = ThreadDetailSerializer(instance=self.thread1, context={'request': self.request_user2})
        data = serializer.data
        self.assertEqual(data['title'], self.thread1.title)
        self.assertEqual(data['content'], self.thread1.content)
        self.assertFalse(data['is_liked_by_user']) # user2 has not liked it
        self.assertFalse(data['user_can_edit']) # user2 is not author or staff
        self.assertTrue(data['user_can_reply']) # Thread is open

    def test_thread_detail_serializer_create_valid(self):
        data = {
            "forum_id": self.forum_general.id, # Assuming direct forum_id for simplicity here
            "title": "A Brand New Thread",
            "content": "Content for the new thread.",
            # Slug will be auto-generated
        }
        # Create a POST request mock
        request_post_user2 = self.factory.post('/fake-community-endpoint')
        request_post_user2.user = self.user2

        serializer = ThreadDetailSerializer(data=data, context={'request': request_post_user2})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        thread = serializer.save(author=self.user2, forum=self.forum_general) # Author & forum set in view normally
        
        self.assertEqual(thread.title, "A Brand New Thread")
        self.assertEqual(thread.author, self.user2)
        self.assertEqual(thread.forum, self.forum_general)
        self.assertEqual(thread.slug, slugify("A Brand New Thread"))

    def test_thread_detail_serializer_update_by_author(self):
        data = {"title": "Updated Title by Author", "content": "Updated content."}
        serializer = ThreadDetailSerializer(instance=self.thread1, data=data, partial=True, context={'request': self.request_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        thread = serializer.save()
        self.assertEqual(thread.title, "Updated Title by Author")


class PostSerializerTests(CommunitySerializerTestDataMixin, TestCase):
    def test_post_serializer_output(self):
        Like.objects.create(user=self.user1, content_object=self.post1_thread1)
        self.post1_thread1.refresh_from_db()

        serializer = PostSerializer(instance=self.post1_thread1, context={'request': self.request_user1})
        data = serializer.data
        self.assertEqual(data['content'], self.post1_thread1.content)
        self.assertEqual(data['author']['username'], self.user2.username) # user2 is author of post1
        self.assertEqual(data['thread_title'], self.thread1.title)
        self.assertEqual(data['like_count'], 1)
        self.assertTrue(data['is_liked_by_user']) # user1 liked user2's post
        self.assertFalse(data['user_can_edit']) # user1 is not author of post1

    def test_post_serializer_create_valid(self):
        data = {
            "thread_id": self.thread1.id,
            "content": "User1 replying to thread1."
        }
        request_post_user1 = self.factory.post('/fake-community-endpoint')
        request_post_user1.user = self.user1

        serializer = PostSerializer(data=data, context={'request': request_post_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        post = serializer.save(author=self.user1, thread=self.thread1) # Author & thread set in view
        self.assertEqual(post.content, "User1 replying to thread1.")
        self.assertEqual(post.author, self.user1)

    def test_post_serializer_create_on_closed_thread_fails(self):
        self.thread1.is_closed = True
        self.thread1.save()
        data = {"thread_id": self.thread1.id, "content": "Trying to post on closed."}
        serializer = PostSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('thread_id', serializer.errors) # Validation is on thread_id
        self.assertIn("Cannot post to a closed thread.", str(serializer.errors['thread_id']))


class CommentSerializerTests(CommunitySerializerTestDataMixin, TestCase):
    def test_comment_serializer_output(self):
        serializer = CommentSerializer(instance=self.comment1_post1, context={'request': self.request_user2})
        data = serializer.data
        self.assertEqual(data['content'], self.comment1_post1.content)
        self.assertEqual(data['author']['username'], self.user1.username) # user1 authored comment1
        self.assertFalse(data['is_liked_by_user']) # user2 viewing user1's comment
        self.assertFalse(data['user_can_edit']) # user2 not author

    def test_comment_serializer_create_valid(self):
        data = {
            "post_id": self.post1_thread1.id,
            "content": "User2 commenting on user2's post (self.post1_thread1)."
        }
        request_post_user2 = self.factory.post('/fake-community-endpoint')
        request_post_user2.user = self.user2

        serializer = CommentSerializer(data=data, context={'request': request_post_user2})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        comment = serializer.save(author=self.user2, post=self.post1_thread1)
        self.assertEqual(comment.author, self.user2)


class LikeSerializerTests(CommunitySerializerTestDataMixin, TestCase):
    def test_like_create_valid_thread(self):
        data = {
            "content_type_model": "thread",
            "object_id": str(self.thread1.id)
        }
        # User2 likes thread1
        request_post_user2 = self.factory.post('/fake-community-endpoint')
        request_post_user2.user = self.user2
        request_post_user2.method = 'POST' # Important for serializer's duplicate check

        serializer = LikeSerializer(data=data, context={'request': request_post_user2})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        like = serializer.save() # User is set from context in create()
        self.assertEqual(like.user, self.user2)
        self.assertEqual(like.liked_object, self.thread1)
        self.thread1.refresh_from_db()
        self.assertEqual(self.thread1.like_count, 1)

    def test_like_create_duplicate_fails(self):
        Like.objects.create(user=self.user2, content_object=self.thread1) # User2 already liked
        data = {"content_type_model": "thread", "object_id": str(self.thread1.id)}
        request_post_user2 = self.factory.post('/fake-community-endpoint')
        request_post_user2.user = self.user2
        request_post_user2.method = 'POST'

        serializer = LikeSerializer(data=data, context={'request': request_post_user2})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors) # Or specific error key
        self.assertIn("You have already liked this item.", str(serializer.errors['non_field_errors']))

    def test_like_create_invalid_content_type_model(self):
        data = {"content_type_model": "invalidmodel", "object_id": str(self.thread1.id)}
        serializer = LikeSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('content_type_model', serializer.errors)

    def test_like_create_non_existent_object_id(self):
        data = {"content_type_model": "thread", "object_id": str(uuid4())} # Random UUID
        serializer = LikeSerializer(data=data, context={'request': self.request_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('object_id', serializer.errors)


class ReportSerializerTests(CommunitySerializerTestDataMixin, TestCase):
    def test_report_create_valid(self):
        data = {
            "content_type_model": "post",
            "object_id": str(self.post1_thread1.id),
            "reason": "This post is offensive."
        }
        request_post_user1 = self.factory.post('/fake-community-endpoint')
        request_post_user1.user = self.user1
        request_post_user1.method = 'POST'

        serializer = ReportSerializer(data=data, context={'request': request_post_user1})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        report = serializer.save() # Reporter set from context
        self.assertEqual(report.reporter, self.user1)
        self.assertEqual(report.reported_object, self.post1_thread1)
        self.assertEqual(report.reason, "This post is offensive.")
        self.assertEqual(report.status, 'pending')

    def test_report_create_duplicate_pending_fails(self):
        Report.objects.create(reporter=self.user1, content_object=self.post1_thread1, reason="Initial report", status='pending')
        data = {"content_type_model": "post", "object_id": str(self.post1_thread1.id), "reason": "Reporting again."}
        
        request_post_user1 = self.factory.post('/fake-community-endpoint')
        request_post_user1.user = self.user1
        request_post_user1.method = 'POST'

        serializer = ReportSerializer(data=data, context={'request': request_post_user1})
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertIn("You have already submitted a pending report for this item.", str(serializer.errors['non_field_errors']))

    def test_report_serialization_output_with_details(self):
        report = Report.objects.create(reporter=self.user1, content_object=self.post1_thread1, reason="Test", status='resolved_action_taken', resolved_by=self.moderator_user)
        serializer = ReportSerializer(instance=report, context={'request': self.request_moderator})
        data = serializer.data
        self.assertEqual(data['reporter']['username'], self.user1.username)
        self.assertEqual(data['resolved_by']['username'], self.moderator_user.username)
        self.assertEqual(data['status_display'], dict(REPORT_STATUS_CHOICES).get('resolved_action_taken'))
        self.assertIsNotNone(data['reported_object_details'])
        self.assertEqual(data['reported_object_details']['type'], 'post')
        self.assertEqual(data['reported_object_details']['id'], str(self.post1_thread1.id))

    def test_report_update_by_admin(self):
        report = Report.objects.create(reporter=self.user1, content_object=self.post1_thread1, reason="Test", status='pending')
        data = {
            "status": "resolved_no_action",
            "moderator_notes": "Reviewed, no action needed."
        }
        serializer = ReportSerializer(instance=report, data=data, partial=True, context={'request': self.request_moderator})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_report = serializer.save() # resolved_by is set in view typically, or serializer update
        self.assertEqual(updated_report.status, "resolved_no_action")
        self.assertEqual(updated_report.moderator_notes, "Reviewed, no action needed.")
        # self.assertEqual(updated_report.resolved_by, self.moderator_user) # If serializer's update sets it

