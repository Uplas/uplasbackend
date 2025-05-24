from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType

from apps.community.models import (
    Forum, Thread, Post, Comment, Like, Report,
    REPORT_STATUS_CHOICES
)
# Ensure settings are configured for tests, especially AUTH_USER_MODEL
from django.conf import settings

User = get_user_model()

class CommunityModelTestDataMixin:
    """
    Mixin to provide common setup data for community-related model tests.
    """
    @classmethod
    def setUpTestData(cls):
        # Create users
        cls.user1 = User.objects.create_user(
            username='comm_user1',
            email='comm_user1@example.com',
            password='password123',
            full_name='Community User One'
        )
        cls.user2 = User.objects.create_user(
            username='comm_user2',
            email='comm_user2@example.com',
            password='password123',
            full_name='Community User Two'
        )
        cls.moderator_user = User.objects.create_user(
            username='comm_moderator',
            email='comm_moderator@example.com',
            password='password123',
            full_name='Community Moderator',
            is_staff=True # Assuming moderators are staff
        )

        # Create a Forum
        cls.forum_general = Forum.objects.create(
            name='General Discussion',
            slug='general-discussion',
            description='A place for general chats.',
            display_order=1
        )
        cls.forum_python = Forum.objects.create(
            name='Python Help',
            slug='python-help',
            description='Get help with Python programming.',
            display_order=0
        )

        # Create a Thread in forum_general by user1
        cls.thread1_user1 = Thread.objects.create(
            forum=cls.forum_general,
            author=cls.user1,
            title='Hello World - My First Thread!',
            slug='hello-world-my-first-thread', # Ensure this is unique
            content='This is the initial content of my first thread.'
        )
        # Note: last_activity_at is auto_now_add initially, then updated by save() or Post signals

class ForumModelTests(CommunityModelTestDataMixin, TestCase):
    def test_forum_creation(self):
        self.assertEqual(self.forum_general.name, 'General Discussion')
        self.assertEqual(self.forum_general.slug, 'general-discussion')
        self.assertEqual(self.forum_general.thread_count, 0) # Initially 0, updated by Thread signal
        self.assertEqual(self.forum_general.post_count, 0) # Initially 0, updated by Thread/Post signal
        self.assertEqual(str(self.forum_general), 'General Discussion')

    def test_forum_name_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Forum.objects.create(name='General Discussion', slug='general-discussion-new')

    def test_forum_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Forum.objects.create(name='General Discussion New', slug='general-discussion')

    def test_forum_ordering(self):
        forums = Forum.objects.all()
        self.assertEqual(forums[0], self.forum_python) # display_order=0
        self.assertEqual(forums[1], self.forum_general) # display_order=1


class ThreadModelTests(CommunityModelTestDataMixin, TestCase):
    def test_thread_creation(self):
        self.assertEqual(self.thread1_user1.title, 'Hello World - My First Thread!')
        self.assertEqual(self.thread1_user1.forum, self.forum_general)
        self.assertEqual(self.thread1_user1.author, self.user1)
        self.assertEqual(self.thread1_user1.reply_count, 0) # No replies yet
        self.assertEqual(self.thread1_user1.like_count, 0)
        self.assertIsNotNone(self.thread1_user1.last_activity_at)
        self.assertEqual(str(self.thread1_user1), 'Hello World - My First Thread!')

        # Test forum thread_count update via signal
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.thread_count, 1)
        # Test forum post_count (thread itself counts as 1 "post" conceptually for forum total)
        self.assertEqual(self.forum_general.post_count, 1)


    def test_thread_slug_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Thread.objects.create(
                forum=self.forum_python, author=self.user2, title='Another Hello',
                slug='hello-world-my-first-thread', # Duplicate slug
                content='Test'
            )

    def test_thread_save_updates_last_activity(self):
        old_activity = self.thread1_user1.last_activity_at
        # Make a change and save
        self.thread1_user1.title = "Updated Thread Title"
        self.thread1_user1.save()
        self.thread1_user1.refresh_from_db()
        self.assertGreater(self.thread1_user1.last_activity_at, old_activity)

    def test_thread_deletion_updates_forum_counts(self):
        # Create another thread in the same forum to ensure count logic is correct
        thread2 = Thread.objects.create(forum=self.forum_general, author=self.user2, title="T2", slug="t2", content="c2")
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.thread_count, 2)
        self.assertEqual(self.forum_general.post_count, 2) # Each thread is 1 initial "post"

        self.thread1_user1.delete()
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.thread_count, 1)
        self.assertEqual(self.forum_general.post_count, 1) # Only thread2 remains


class PostModelTests(CommunityModelTestDataMixin, TestCase):
    def setUp(self):
        # Create a post (reply) for thread1_user1
        self.post1_user2_on_thread1 = Post.objects.create(
            thread=self.thread1_user1,
            author=self.user2,
            content="This is a reply from user2."
        )

    def test_post_creation(self):
        self.assertEqual(self.post1_user2_on_thread1.thread, self.thread1_user1)
        self.assertEqual(self.post1_user2_on_thread1.author, self.user2)
        self.assertIn("This is a reply", self.post1_user2_on_thread1.content)
        self.assertEqual(self.post1_user2_on_thread1.like_count, 0)
        expected_str_part = f"Reply by {self.user2.email} in '{self.thread1_user1.title}'"
        self.assertIn(expected_str_part, str(self.post1_user2_on_thread1))

    def test_post_signal_updates_thread_and_forum(self):
        # Thread's reply_count and last_activity_at should be updated
        self.thread1_user1.refresh_from_db()
        self.assertEqual(self.thread1_user1.reply_count, 1)
        self.assertGreaterEqual(self.thread1_user1.last_activity_at, self.post1_user2_on_thread1.created_at)

        # Forum's post_count should be updated (1 for thread + 1 for post)
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.post_count, 2) # thread1 + post1

        # Add another post
        post2 = Post.objects.create(thread=self.thread1_user1, author=self.user1, content="Another reply")
        self.thread1_user1.refresh_from_db()
        self.assertEqual(self.thread1_user1.reply_count, 2)
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.post_count, 3) # thread1 + post1 + post2

        # Delete a post
        post2.delete()
        self.thread1_user1.refresh_from_db()
        self.assertEqual(self.thread1_user1.reply_count, 1)
        self.forum_general.refresh_from_db()
        self.assertEqual(self.forum_general.post_count, 2) # thread1 + post1


class CommentModelTests(CommunityModelTestDataMixin, TestCase):
    def setUp(self):
        self.post_for_comment = Post.objects.create(thread=self.thread1_user1, author=self.user1, content="A post to be commented on.")
        self.comment1_user2_on_post = Comment.objects.create(
            post=self.post_for_comment,
            author=self.user2,
            content="This is a comment on user1's post."
        )

    def test_comment_creation(self):
        self.assertEqual(self.comment1_user2_on_post.post, self.post_for_comment)
        self.assertEqual(self.comment1_user2_on_post.author, self.user2)
        self.assertIn("This is a comment", self.comment1_user2_on_post.content)
        self.assertEqual(self.comment1_user2_on_post.like_count, 0)
        expected_str_part = f"Comment by {self.user2.email} on post {self.post_for_comment.id}"
        self.assertEqual(str(self.comment1_user2_on_post), expected_str_part)

    # Add tests for Comment signals if Comment model gets a comment_count on Post, etc.


class LikeModelTests(CommunityModelTestDataMixin, TestCase):
    def setUp(self):
        self.post_to_like = Post.objects.create(thread=self.thread1_user1, author=self.user1, content="Likeable post")
        self.thread_content_type = ContentType.objects.get_for_model(Thread)
        self.post_content_type = ContentType.objects.get_for_model(Post)

    def test_like_creation_and_signal(self):
        # Like a thread
        initial_thread_likes = self.thread1_user1.like_count
        like_on_thread = Like.objects.create(user=self.user2, content_type=self.thread_content_type, object_id=self.thread1_user1.id)
        self.thread1_user1.refresh_from_db()
        self.assertEqual(self.thread1_user1.like_count, initial_thread_likes + 1)
        self.assertEqual(str(like_on_thread), f"{self.user2.email} likes {self.thread1_user1}")

        # Like a post
        initial_post_likes = self.post_to_like.like_count
        like_on_post = Like.objects.create(user=self.user1, content_type=self.post_content_type, object_id=self.post_to_like.id)
        self.post_to_like.refresh_from_db()
        self.assertEqual(self.post_to_like.like_count, initial_post_likes + 1)

    def test_like_uniqueness_user_content_object(self):
        Like.objects.create(user=self.user2, content_type=self.thread_content_type, object_id=self.thread1_user1.id)
        with self.assertRaises(IntegrityError): # User2 tries to like the same thread again
            Like.objects.create(user=self.user2, content_type=self.thread_content_type, object_id=self.thread1_user1.id)

    def test_unlike_signal_updates_count(self):
        like = Like.objects.create(user=self.user2, content_type=self.thread_content_type, object_id=self.thread1_user1.id)
        self.thread1_user1.refresh_from_db()
        likes_before_delete = self.thread1_user1.like_count

        like.delete()
        self.thread1_user1.refresh_from_db()
        self.assertEqual(self.thread1_user1.like_count, likes_before_delete - 1)


class ReportModelTests(CommunityModelTestDataMixin, TestCase):
    def setUp(self):
        self.post_to_report = Post.objects.create(thread=self.thread1_user1, author=self.user1, content="A post that might be reported.")
        self.post_content_type = ContentType.objects.get_for_model(Post)

    def test_report_creation(self):
        report = Report.objects.create(
            reporter=self.user2,
            content_type=self.post_content_type,
            object_id=self.post_to_report.id,
            reason="This post contains spam.",
            status='pending' # Default
        )
        self.assertEqual(report.reporter, self.user2)
        self.assertEqual(report.reported_object, self.post_to_report)
        self.assertEqual(report.reason, "This post contains spam.")
        self.assertEqual(report.status, 'pending')
        expected_str_part = f"Report by {self.user2.email} on post {self.post_to_report.id} (Pending Review)"
        self.assertEqual(str(report), expected_str_part)

    def test_report_status_choices(self):
        report = Report.objects.create(reporter=self.user1, content_type=self.post_content_type, object_id=self.post_to_report.id, reason="test")
        report.status = 'resolved_action_taken'
        report.moderator_notes = "User warned."
        report.resolved_by = self.moderator_user
        report.save()
        self.assertEqual(report.get_status_display(), 'Resolved - Action Taken')

# Add more tests for:
# - Edge cases for signals (e.g., deleting a Forum and checking if related Thread counts are handled gracefully or if errors occur).
# - Behavior of is_hidden, is_closed, is_pinned on Threads and Posts and how they affect counts if signals consider them.
# - Any custom methods added to models.
