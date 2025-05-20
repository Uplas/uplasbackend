from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework.test import APIRequestFactory # For providing request context

from ..models import BlogCategory, BlogPost, BlogComment, Author, Tag
from ..serializers import (
    BlogCategorySerializer, BlogPostSerializer, BlogCommentSerializer,
    AuthorSerializer, BasicUserSerializerForBlog, BasicTagSerializerForBlog
)

User = get_user_model()

class BlogCategorySerializerTests(TestCase):
    def test_category_serializer_output(self):
        category = BlogCategory.objects.create(name="Product Updates", display_order=0)
        # Simulate annotation if viewset provides it
        setattr(category, 'posts_count', 3)
        serializer = BlogCategorySerializer(category)
        data = serializer.data
        self.assertEqual(data['name'], "Product Updates")
        self.assertEqual(data['slug'], slugify("Product Updates"))
        self.assertEqual(data['posts_count'], 3)

    def test_category_serializer_create(self):
        data = {"name": "Guides", "description": "Helpful guides."}
        serializer = BlogCategorySerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, "Guides")


class AuthorSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="blog_author_user@example.com", password="password", full_name="Blog Author User"
        )
        self.user.profile_picture_url = "http://example.com/user_avatar.png" # Assuming direct field on User
        self.user.save()

    def test_author_serializer_with_linked_user_override(self):
        author_profile = Author.objects.create(
            user=self.user,
            display_name="Dr. Blogger",
            bio="Blogging expert.",
            avatar_url="http://example.com/dr_blogger.png"
        )
        serializer = AuthorSerializer(author_profile)
        data = serializer.data
        self.assertEqual(data['display_name'], "Dr. Blogger")
        self.assertEqual(data['effective_display_name'], "Dr. Blogger")
        self.assertEqual(data['effective_avatar_url'], "http://example.com/dr_blogger.png")
        self.assertEqual(data['user_details']['full_name'], self.user.full_name)

    def test_author_serializer_with_linked_user_no_override(self):
        author_profile = Author.objects.create(user=self.user, display_name="") # No override display name or avatar
        serializer = AuthorSerializer(author_profile)
        data = serializer.data
        self.assertEqual(data['effective_display_name'], self.user.full_name) # Falls back to user
        self.assertEqual(data['effective_avatar_url'], self.user.profile_picture_url) # Falls back

    def test_author_serializer_guest_author(self):
        guest_author = Author.objects.create(display_name="Anonymous Contributor", bio="Writes sometimes.")
        serializer = AuthorSerializer(guest_author)
        data = serializer.data
        self.assertEqual(data['display_name'], "Anonymous Contributor")
        self.assertEqual(data['effective_display_name'], "Anonymous Contributor")
        self.assertIsNone(data['effective_avatar_url'])
        self.assertIsNone(data['user_details']) # No linked user

    def test_author_serializer_create_with_user_link(self):
        data = {"user": self.user.id, "display_name": "Linked Author"}
        serializer = AuthorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        author = serializer.save()
        self.assertEqual(author.user, self.user)
        self.assertEqual(author.display_name, "Linked Author")

    def test_author_serializer_create_guest(self):
        data = {"display_name": "Pure Guest"}
        serializer = AuthorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        author = serializer.save()
        self.assertIsNone(author.user)
        self.assertEqual(author.display_name, "Pure Guest")


class BlogPostSerializerTests(TestCase):
    def setUp(self):
        self.user_author = User.objects.create_user(
            email="bp_author@example.com", password="password", full_name="BP Author"
        )
        self.user_author.profile_picture_url = "http://example.com/bp_author.png"
        self.user_author.save()

        self.guest_author_profile = Author.objects.create(display_name="Guest Expert")
        self.category = BlogCategory.objects.create(name="Tech News")
        self.tag_ai = Tag.objects.create(name="AI")

        self.post_by_user = BlogPost.objects.create(
            title="AI in 2025", author=self.user_author, content_html="<p>Future is AI.</p>",
            status='published', category=self.category
        )
        self.post_by_user.tags.add(self.tag_ai)

        self.post_by_guest_override = BlogPost.objects.create(
            title="My Guest Post", author=self.user_author, # Uplas user still main author
            author_profile_override=self.guest_author_profile,
            content_html="<p>A guest's view.</p>", status='draft'
        )
        
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/') # Dummy request for context

    def test_blog_post_serializer_output_by_uplas_user(self):
        serializer = BlogPostSerializer(self.post_by_user, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['title'], self.post_by_user.title)
        self.assertEqual(data['display_author_name'], self.user_author.full_name)
        self.assertEqual(data['display_author_avatar_url'], self.user_author.profile_picture_url)
        self.assertEqual(data['category']['name'], self.category.name)
        self.assertEqual(len(data['tags']), 1)
        self.assertEqual(data['tags'][0]['name'], self.tag_ai.name)
        self.assertEqual(data['status'], 'published')
        self.assertEqual(data['comment_count'], 0) # Based on method

    def test_blog_post_serializer_output_by_guest_override(self):
        serializer = BlogPostSerializer(self.post_by_guest_override, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['title'], self.post_by_guest_override.title)
        self.assertEqual(data['display_author_name'], self.guest_author_profile.display_name)
        self.assertIsNone(data['display_author_avatar_url']) # Guest author has no avatar set
        self.assertEqual(data['status'], 'draft')

    def test_blog_post_serializer_create_valid(self):
        # For creation, author_id is required
        post_data = {
            "title": "API Created Post",
            "content_html": "<p>Created via API.</p>",
            "status": "draft",
            "author_id": self.user_author.id, # Required
            "category_id": self.category.id,
            "tag_ids": [self.tag_ai.id]
        }
        serializer = BlogPostSerializer(data=post_data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # saved_post = serializer.save() # Author is already part of validated_data due to author_id
        # self.assertEqual(saved_post.author, self.user_author)

    def test_blog_post_serializer_create_missing_author(self):
        post_data = {"title": "No Author Post", "content_html": "c", "status": "draft"}
        serializer = BlogPostSerializer(data=post_data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('author_id', serializer.errors) # author_id is required=True

    def test_blog_post_serializer_comment_count_method(self):
        BlogComment.objects.create(post=self.post_by_user, content="C1", is_approved=True)
        BlogComment.objects.create(post=self.post_by_user, content="C2 (unapproved)", is_approved=False)
        BlogComment.objects.create(post=self.post_by_user, content="C3", is_approved=True)

        serializer = BlogPostSerializer(self.post_by_user, context={'request': self.request})
        self.assertEqual(serializer.data['comment_count'], 2) # Only approved comments


class BlogCommentSerializerTests(TestCase):
    def setUp(self):
        self.blog_author = User.objects.create_user(email="bc_post_author@example.com", password="password")
        self.commenter_auth = User.objects.create_user(email="bc_auth_user@example.com", password="password", full_name="Auth Commenter")
        self.commenter_auth.profile_picture_url = "http://example.com/auth_commenter.png"
        self.commenter_auth.save()

        self.post = BlogPost.objects.create(author=self.blog_author, title="Comment Test Post", content_html="...")
        
        self.factory = APIRequestFactory()
        self.request_authenticated = self.factory.post('/') # Simulate POST for creating comment
        self.request_authenticated.user = self.commenter_auth
        
        self.request_guest = self.factory.post('/')
        self.request_guest.user = MagicMock(is_authenticated=False) # Simulate anonymous user


    def test_blog_comment_serializer_output_authenticated_user(self):
        comment = BlogComment.objects.create(post=self.post, author=self.commenter_auth, content="By auth user.")
        serializer = BlogCommentSerializer(comment, context={'request': self.request_authenticated})
        data = serializer.data
        self.assertEqual(data['content'], comment.content)
        self.assertIsNotNone(data['author']) # Should show author PK
        self.assertEqual(data['commenter_display_name'], self.commenter_auth.full_name)
        self.assertEqual(data['commenter_avatar_url'], self.commenter_auth.profile_picture_url)
        self.assertEqual(data['author_name'], "") # Guest field should be empty

    def test_blog_comment_serializer_output_guest_user(self):
        comment = BlogComment.objects.create(post=self.post, author_name="Guesty", content="By guest.")
        serializer = BlogCommentSerializer(comment, context={'request': self.request_guest}) # Guest request
        data = serializer.data
        self.assertEqual(data['content'], comment.content)
        self.assertIsNone(data['author']) # No Uplas user linked
        self.assertEqual(data['author_name'], "Guesty")
        self.assertEqual(data['commenter_display_name'], "Guesty")
        self.assertTrue("Guesty" in data['commenter_avatar_url']) # Placeholder avatar

    def test_blog_comment_create_by_authenticated_user(self):
        data = {"content": "Authenticated reply."}
        # 'post' and 'author' are set by the view from context.
        # Serializer needs 'post_instance' in context for parent_comment validation if applicable.
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_authenticated, 'post_instance': self.post})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # saved_comment = serializer.save(author=self.commenter_auth, post=self.post)
        # self.assertEqual(saved_comment.author, self.commenter_auth)
        # self.assertEqual(saved_comment.author_name, "")

    def test_blog_comment_create_by_guest_valid(self):
        data = {"author_name": "Guest User", "content": "Guest comment here."}
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_guest, 'post_instance': self.post})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # saved_comment = serializer.save(post=self.post) # Author will be None
        # self.assertIsNone(saved_comment.author)
        # self.assertEqual(saved_comment.author_name, "Guest User")

    def test_blog_comment_create_by_guest_missing_name(self):
        data = {"content": "Guest comment without name."} # Missing author_name
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_guest, 'post_instance': self.post})
        self.assertFalse(serializer.is_valid())
        self.assertIn('author_name', serializer.errors)

    def test_blog_comment_reply_validation_same_post(self):
        parent_comment = BlogComment.objects.create(post=self.post, author=self.commenter_auth, content="Parent")
        other_post = BlogPost.objects.create(author=self.blog_author, title="Other Post", content_html="...")
        
        # Attempt to reply to parent_comment but associate with other_post (via context)
        data = {"content": "Reply to wrong post's comment", "parent_comment_id": parent_comment.id}
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_authenticated, 'post_instance': other_post})
        self.assertFalse(serializer.is_valid())
        self.assertIn('parent_comment_id', serializer.errors) # Validation in serializer checks this

    def test_blog_comment_reply_validation_correct_post(self):
        parent_comment = BlogComment.objects.create(post=self.post, author=self.commenter_auth, content="Parent")
        data = {"content": "Valid reply", "parent_comment_id": parent_comment.id}
        serializer = BlogCommentSerializer(data=data, context={'request': self.request_authenticated, 'post_instance': self.post})
        self.assertTrue(serializer.is_valid(), serializer.errors)
