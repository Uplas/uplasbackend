from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.contenttypes.models import ContentType # For GenericRelation tests

from rest_framework.test import APIRequestFactory # For providing request context
from rest_framework.exceptions import ValidationError

from apps.blog.models import (
    BlogCategory, BlogPostTag, BlogPost, BlogComment
)
from apps.blog.serializers import (
    BlogCategorySerializer, BlogPostTagSerializer,
    BlogPostListSerializer, BlogPostDetailSerializer,
    BlogCommentSerializer, SimpleUserSerializer # Ensure SimpleUserSerializer is defined or imported
)
# Assuming a Like model exists for testing SerializerMethodFields, e.g., in community
# from apps.community.models import Like

User = get_user_model()

# Test Data Setup Mixin (adapted for serializer tests)
class BlogSerializerTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.author_user = User.objects.create_user(
            username='blogser_author1', email='blogser_author1@example.com',
            password='password123', full_name='BlogSer Author One'
        )
        cls.commenter_user = User.objects.create_user(
            username='blogser_commenter1', email='blogser_commenter1@example.com',
            password='password123', full_name='BlogSer Commenter One'
        )
        cls.admin_user = User.objects.create_superuser( # For context where staff might be needed
            username='blogser_admin', email='blogser_admin@example.com',
            password='password123', full_name='BlogSer Admin'
        )

        cls.cat_tech = BlogCategory.objects.create(name='Tech Serializers', slug='tech-serializers')
        cls.tag_drf = BlogPostTag.objects.create(name='DRF', slug='drf')
        cls.tag_testing = BlogPostTag.objects.create(name='Testing', slug='testing')

        cls.post_published = BlogPost.objects.create(
            author=cls.author_user, category=cls.cat_tech,
            title='Serializing Django Models', slug='serializing-django-models-ser',
            excerpt='How to effectively serialize models.',
            content_markdown='Markdown content about serializers...',
            status='published', published_at=timezone.now()
        )
        cls.post_published.tags.add(cls.tag_drf, cls.tag_testing)

        cls.post_draft = BlogPost.objects.create(
            author=cls.author_user, category=cls.cat_tech,
            title='Draft Post on Serializers', slug='draft-post-serializers-ser',
            content_markdown='This is a draft.', status='draft'
        )

        cls.comment_on_published = BlogComment.objects.create(
            blog_post=cls.post_published, author=cls.commenter_user,
            content='Very useful serializer info!'
        )
        # post_published.comment_count should be 1 now due to signal

        # For providing request context to serializers
        cls.factory = APIRequestFactory()
        cls.request_author = cls.factory.get('/fake-blog-endpoint')
        cls.request_author.user = cls.author_user
        cls.request_author.method = 'GET' # Can be changed in tests

        cls.request_commenter = cls.factory.get('/fake-blog-endpoint')
        cls.request_commenter.user = cls.commenter_user
        cls.request_commenter.method = 'GET'
        
        cls.request_admin = cls.factory.get('/fake-blog-endpoint')
        cls.request_admin.user = cls.admin_user
        cls.request_admin.method = 'GET'

        cls.request_anonymous = cls.factory.get('/fake-blog-endpoint')
        from django.contrib.auth.models import AnonymousUser
        cls.request_anonymous.user = AnonymousUser()
        cls.request_anonymous.method = 'GET'


class BlogCategorySerializerTests(BlogSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        self.cat_tech.refresh_from_db() # Ensure post_count is updated by signals
        serializer = BlogCategorySerializer(instance=self.cat_tech)
        data = serializer.data
        self.assertEqual(data['name'], self.cat_tech.name)
        self.assertEqual(data['slug'], self.cat_tech.slug)
        self.assertEqual(data['post_count'], 1) # post_published is in this category
        self.assertIn('id', data)

    def test_deserialization_create_valid_with_slug_generation(self):
        data = {'name': 'New Category For Blog', 'description': 'A new one for testing.'}
        serializer = BlogCategorySerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, 'New Category For Blog')
        self.assertEqual(category.slug, slugify('New Category For Blog'))

    def test_deserialization_update_name_updates_slug_if_slug_not_provided(self):
        data = {'name': 'Tech Serializers Updated'}
        serializer = BlogCategorySerializer(instance=self.cat_tech, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, 'Tech Serializers Updated')
        self.assertEqual(category.slug, slugify('Tech Serializers Updated'))

    def test_deserialization_update_name_does_not_update_slug_if_slug_is_provided(self):
        original_slug = self.cat_tech.slug
        data = {'name': 'Tech Serializers Renamed Again', 'slug': original_slug} # Explicitly keeping old slug
        serializer = BlogCategorySerializer(instance=self.cat_tech, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, 'Tech Serializers Renamed Again')
        self.assertEqual(category.slug, original_slug) # Slug should not have changed


class BlogPostTagSerializerTests(BlogSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        serializer = BlogPostTagSerializer(instance=self.tag_drf)
        data = serializer.data
        self.assertEqual(data['name'], self.tag_drf.name)
        self.assertEqual(data['slug'], self.tag_drf.slug)

    # Add create/update tests similar to BlogCategorySerializer if slug generation is implemented there


class BlogPostSerializersTests(BlogSerializerTestDataMixin, TestCase):
    def test_blog_post_list_serializer_output(self):
        self.post_published.refresh_from_db() # For comment_count
        serializer = BlogPostListSerializer(instance=self.post_published, context={'request': self.request_anonymous})
        data = serializer.data
        self.assertEqual(data['title'], self.post_published.title)
        self.assertEqual(data['author']['username'], self.author_user.username)
        self.assertEqual(data['category']['name'], self.cat_tech.name)
        self.assertEqual(len(data['tags']), 2)
        self.assertEqual(data['status_display'], self.post_published.get_status_display())
        self.assertEqual(data['comment_count'], 1) # comment_on_published
        # self.assertFalse(data['is_liked_by_user']) # Anonymous user

    def test_blog_post_detail_serializer_read(self):
        serializer = BlogPostDetailSerializer(instance=self.post_published, context={'request': self.request_author})
        data = serializer.data
        self.assertEqual(data['title'], self.post_published.title)
        self.assertEqual(data['content_markdown'], self.post_published.content_markdown)
        self.assertEqual(data['author']['id'], self.author_user.id)
        self.assertTrue(data['user_can_edit']) # Author viewing their own post

    def test_blog_post_detail_serializer_create_by_author(self):
        data = {
            "title": "My New Blog Post via Serializer",
            "category_id": self.cat_tutorials.id,
            "tag_ids": [self.tag_python.id, self.tag_webdev.id],
            "excerpt": "A quick summary.",
            "content_markdown": "Full content of the new post.",
            "status": "draft",
            "featured_image": "http://example.com/image.jpg"
        }
        serializer = BlogPostDetailSerializer(data=data, context={'request': self.request_author})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        blog_post = serializer.save() # Author is set from context by serializer's create
        
        self.assertEqual(blog_post.title, "My New Blog Post via Serializer")
        self.assertEqual(blog_post.author, self.author_user)
        self.assertEqual(blog_post.category, self.cat_tutorials)
        self.assertEqual(blog_post.tags.count(), 2)
        self.assertIn(self.tag_python, blog_post.tags.all())
        self.assertEqual(blog_post.status, 'draft')
        self.assertEqual(blog_post.slug, slugify("My New Blog Post via Serializer"))

    def test_blog_post_detail_serializer_update_by_author(self):
        data = {
            "title": "Serializing Django Models (Updated)",
            "content_markdown": "Updated Markdown content here.",
            "status": "published",
            "tag_ids": [self.tag_django.id] # Change tags
        }
        serializer = BlogPostDetailSerializer(instance=self.post_published, data=data, partial=True, context={'request': self.request_author})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        blog_post = serializer.save()
        self.assertEqual(blog_post.title, "Serializing Django Models (Updated)")
        self.assertEqual(blog_post.tags.count(), 1)
        self.assertIn(self.tag_django, blog_post.tags.all())
        self.assertNotIn(self.tag_python, blog_post.tags.all()) # Python tag should be removed
        self.assertEqual(blog_post.status, 'published')
        self.assertIsNotNone(blog_post.published_at)

    def test_blog_post_detail_serializer_title_validation(self):
        data = {"title": "Short", "content_markdown": "Valid content."} # Title too short
        serializer = BlogPostDetailSerializer(data=data, context={'request': self.request_author})
        self.assertFalse(serializer.is_valid())
        self.assertIn('title', serializer.errors)
        self.assertIn("at least 10 characters long", str(serializer.errors['title']))


class BlogCommentSerializerTests(BlogSerializerTestDataMixin, TestCase):
    def test_serialization_output(self):
        self.comment_on_published.refresh_from_db() # For like_count if implemented
        serializer = BlogCommentSerializer(instance=self.comment_on_published, context={'request': self.request_author})
        data = serializer.data
        self.assertEqual(data['content'], self.comment_on_published.content)
        self.assertEqual(data['author']['username'], self.commenter_user.username)
        self.assertTrue(data['is_publicly_visible'])
        self.assertTrue(data['user_can_edit']) # author_user is staff in this test setup

    def test_deserialization_create_valid_comment(self):
        data = {
            "blog_post_id": self.post_published.id,
            "content": "A new comment from user1."
        }
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_author})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        comment = serializer.save() # Author set from context by serializer's create
        self.assertEqual(comment.author, self.author_user)
        self.assertEqual(comment.blog_post, self.post_published)
        self.assertEqual(comment.content, "A new comment from user1.")
        self.post_published.refresh_from_db()
        self.assertEqual(self.post_published.comment_count, 3) # comment1, comment2_reply, new one

    def test_deserialization_create_reply_valid(self):
        data = {
            "blog_post_id": self.post_published.id,
            "parent_comment_id": self.comment_on_published.id,
            "content": "Replying to the first comment."
        }
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_author})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        reply = serializer.save()
        self.assertEqual(reply.parent_comment, self.comment_on_published)
        self.assertEqual(reply.blog_post, self.post_published)

    def test_deserialization_create_comment_on_draft_post_fails(self):
        data = {"blog_post_id": self.post_draft.id, "content": "Trying to comment on draft."}
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_commenter})
        self.assertFalse(serializer.is_valid())
        self.assertIn('blog_post_id', serializer.errors)
        self.assertIn("Comments are only allowed on published blog posts.", str(serializer.errors['blog_post_id']))

    def test_deserialization_reply_to_comment_on_different_post_fails(self):
        # Create another post
        another_post = BlogPost.objects.create(author=self.author_user, title="Another Post", slug="another-post-ser", content_markdown="c", status='published')
        
        data = {
            "blog_post_id": another_post.id, # Replying to another_post
            "parent_comment_id": self.comment_on_published.id, # But parent is on self.post_published
            "content": "Mismatched parent."
        }
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_commenter})
        self.assertFalse(serializer.is_valid())
        self.assertIn('parent_comment_id', serializer.errors)
        self.assertIn("Parent comment does not belong to the same blog post.", str(serializer.errors['parent_comment_id']))

# Add more tests for:
# - SerializerMethodFields like 'is_liked_by_user' when Like model is integrated.
# - Update operations for BlogCommentSerializer.
# - Validation of all fields in all serializers.
# - Behavior of read-only and write-only fields during updates.
# - Slug generation edge cases in BlogCategorySerializer and BlogPostTagSerializer if implemented there.
