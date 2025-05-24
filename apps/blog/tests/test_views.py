from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.blog.models import (
    BlogCategory, BlogPostTag, BlogPost, BlogComment
)
# Import serializers to compare response data (optional, can also check specific fields)
from apps.blog.serializers import (
    BlogCategorySerializer, BlogPostTagSerializer,
    BlogPostListSerializer, BlogPostDetailSerializer, BlogCommentSerializer
)

User = get_user_model()

# Test Data Setup Mixin (adapted for APITestCase)
class BlogViewTestDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='blogview_admin', email='blogview_admin@example.com', password='password123',
            full_name='BlogView Admin'
        )
        # For blog posts, an "author" role might be staff or a specific group.
        # For simplicity, let's make authors also staff for some tests, or just regular users.
        cls.author1 = User.objects.create_user(
            username='blogview_author1', email='blogview_author1@example.com', password='password123',
            full_name='BlogView Author One', is_staff=True # Assuming authors might be staff
        )
        cls.author2 = User.objects.create_user(
            username='blogview_author2', email='blogview_author2@example.com', password='password123',
            full_name='BlogView Author Two' # A regular user who can also be an author
        )
        cls.regular_user = User.objects.create_user(
            username='blogview_user1', email='blogview_user1@example.com', password='password123',
            full_name='BlogView Regular User'
        )

        cls.category_tech = BlogCategory.objects.create(name='Tech ViewTest', slug='tech-viewtest')
        cls.category_life = BlogCategory.objects.create(name='Lifestyle ViewTest', slug='lifestyle-viewtest')

        cls.tag_django = BlogPostTag.objects.create(name='Django ViewTest', slug='django-viewtest')
        cls.tag_python = BlogPostTag.objects.create(name='Python ViewTest', slug='python-viewtest')

        cls.post1_published_by_author1 = BlogPost.objects.create(
            author=cls.author1, category=cls.category_tech,
            title='Published Post Alpha by Author1', slug='published-post-alpha-author1',
            excerpt='Excerpt for alpha.', content_markdown='Content for alpha.',
            status='published', published_at=timezone.now()
        )
        cls.post1_published_by_author1.tags.add(cls.tag_django)

        cls.post2_draft_by_author1 = BlogPost.objects.create(
            author=cls.author1, category=cls.category_tech,
            title='Draft Post Beta by Author1', slug='draft-post-beta-author1',
            excerpt='Excerpt for beta.', content_markdown='Content for beta.',
            status='draft'
        )

        cls.post3_published_by_author2 = BlogPost.objects.create(
            author=cls.author2, category=cls.category_life,
            title='Published Post Gamma by Author2', slug='published-post-gamma-author2',
            excerpt='Excerpt for gamma.', content_markdown='Content for gamma.',
            status='published', published_at=timezone.now()
        )
        cls.post3_published_by_author2.tags.add(cls.tag_python)
        
        cls.comment1_post1_user_reg = BlogComment.objects.create(
            blog_post=cls.post1_published_by_author1,
            author=cls.regular_user,
            content="Great post, Author1!"
        )
        cls.comment2_post1_author1_reply = BlogComment.objects.create(
            blog_post=cls.post1_published_by_author1,
            author=cls.author1, # Author replying
            parent_comment=cls.comment1_post1_user_reg,
            content="Thanks RegularUser!"
        )


    def get_jwt_tokens_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return {'refresh': str(refresh), 'access': str(refresh.access_token)}

    def authenticate_client_with_jwt(self, user):
        tokens = self.get_jwt_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')

    def setUp(self):
        super().setUp()


class BlogCategoryViewSetTests(BlogViewTestDataMixin, APITestCase):
    def test_list_categories_anonymous(self):
        url = reverse('blog:blog-category-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 2)

    def test_retrieve_category_anonymous(self):
        url = reverse('blog:blog-category-detail', kwargs={'slug': self.category_tech.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.category_tech.name)

    def test_create_category_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('blog:blog-category-list')
        data = {'name': 'New Category by Admin', 'slug': 'new-cat-admin'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(BlogCategory.objects.filter(slug='new-cat-admin').exists())

    def test_create_category_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.author1) # Non-admin (even if staff for posts)
        url = reverse('blog:blog-category-list')
        data = {'name': 'Forbidden Category', 'slug': 'forbidden-cat'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAdminOrReadOnly


class BlogPostTagViewSetTests(BlogViewTestDataMixin, APITestCase):
    def test_list_tags_anonymous(self):
        url = reverse('blog:blog-post-tag-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data['results']) >= 2)

    def test_create_tag_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('blog:blog-post-tag-list')
        data = {'name': 'New Tag by Admin Blog', 'slug': 'new-tag-admin-blog'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BlogPostTag.objects.filter(slug='new-tag-admin-blog').exists())

    def test_create_tag_non_admin_forbidden(self):
        self.authenticate_client_with_jwt(self.author1)
        url = reverse('blog:blog-post-tag-list')
        data = {'name': 'Forbidden Tag Blog', 'slug': 'forbidden-tag-blog'}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BlogPostViewSetTests(BlogViewTestDataMixin, APITestCase):
    def test_list_blog_posts_anonymous_sees_published(self):
        url = reverse('blog:blog-post-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # post1_published_by_author1 and post3_published_by_author2 are published
        self.assertEqual(len(response.data['results']), 2)
        slugs_in_response = [item['slug'] for item in response.data['results']]
        self.assertIn(self.post1_published_by_author1.slug, slugs_in_response)
        self.assertNotIn(self.post2_draft_by_author1.slug, slugs_in_response)

    def test_list_blog_posts_author_sees_published_and_own_drafts(self):
        self.authenticate_client_with_jwt(self.author1)
        url = reverse('blog:blog-post-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # author1 sees their published post1, their draft post2, and other's published post3
        self.assertEqual(len(response.data['results']), 3, response.data)
        slugs_in_response = [item['slug'] for item in response.data['results']]
        self.assertIn(self.post1_published_by_author1.slug, slugs_in_response)
        self.assertIn(self.post2_draft_by_author1.slug, slugs_in_response)
        self.assertIn(self.post3_published_by_author2.slug, slugs_in_response)


    def test_retrieve_published_post_anonymous(self):
        url = reverse('blog:blog-post-detail', kwargs={'slug': self.post1_published_by_author1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.post1_published_by_author1.title)
        self.assertEqual(response.data['view_count'], 1) # View count incremented

    def test_retrieve_draft_post_anonymous_forbidden(self):
        url = reverse('blog:blog-post-detail', kwargs={'slug': self.post2_draft_by_author1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAuthorOrAdminOrReadOnlyForBlogPost

    def test_retrieve_draft_post_by_author_success(self):
        self.authenticate_client_with_jwt(self.author1)
        url = reverse('blog:blog-post-detail', kwargs={'slug': self.post2_draft_by_author1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.post2_draft_by_author1.title)

    def test_create_blog_post_by_authenticated_author_success(self):
        self.authenticate_client_with_jwt(self.author2) # author2 is a regular user who can be an author
        url = reverse('blog:blog-post-list')
        data = {
            "title": "Author2 New Post", "slug": "author2-new-post", # Slug provided
            "category_id": self.category_life.id,
            "tag_ids": [self.tag_python.id],
            "excerpt": "Summary by Author2.",
            "content_markdown": "Full content by Author2.",
            "status": "draft"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_post = BlogPost.objects.get(slug="author2-new-post")
        self.assertEqual(new_post.author, self.author2)
        self.assertEqual(new_post.category, self.category_life)

    def test_create_blog_post_unauthenticated_forbidden(self):
        url = reverse('blog:blog-post-list')
        data = {"title": "Anon Post Fail", "content_markdown": "test"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_own_blog_post_by_author_success(self):
        self.authenticate_client_with_jwt(self.author1)
        url = reverse('blog:blog-post-detail', kwargs={'slug': self.post1_published_by_author1.slug})
        data = {"title": "Published Post Alpha (Author1 Updated)", "status": "published"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.post1_published_by_author1.refresh_from_db()
        self.assertEqual(self.post1_published_by_author1.title, "Published Post Alpha (Author1 Updated)")

    def test_update_other_author_post_forbidden(self):
        self.authenticate_client_with_jwt(self.author2) # author2 trying to update author1's post
        url = reverse('blog:blog-post-detail', kwargs={'slug': self.post1_published_by_author1.slug})
        data = {"title": "Attempted Update by Author2"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_change_status_action_by_admin_success(self):
        self.authenticate_client_with_jwt(self.admin_user)
        url = reverse('blog:blog-post-change-status', kwargs={'slug': self.post2_draft_by_author1.slug})
        data = {"status": "published"}
        response = self.client.post(url, data, format='json') # POST for actions
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.post2_draft_by_author1.refresh_from_db()
        self.assertEqual(self.post2_draft_by_author1.status, "published")
        self.assertIsNotNone(self.post2_draft_by_author1.published_at)

    def test_change_status_action_by_author_forbidden(self): # Assuming only mods change status via this action
        self.authenticate_client_with_jwt(self.author1)
        url = reverse('blog:blog-post-change-status', kwargs={'slug': self.post2_draft_by_author1.slug})
        data = {"status": "published"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsBlogModerator


class BlogCommentViewSetTests(BlogViewTestDataMixin, APITestCase):
    def test_list_comments_for_published_post_anonymous(self):
        # URL: /api/blog/posts/{post_slug}/comments/
        url = reverse('blog:blogpost-comment-list', kwargs={'post_slug': self.post1_published_by_author1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # comment1_post1_user_reg and comment2_post1_author1_reply are approved by default
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['content'], self.comment1_post1_user_reg.content)

    def test_list_comments_hides_unapproved_for_anonymous(self):
        # comment3_unapproved is on post1_published_by_author1 but is_approved=False
        self.comment1_post1_user_reg.is_approved = False # Make one unapproved
        self.comment1_post1_user_reg.save()

        url = reverse('blog:blogpost-comment-list', kwargs={'post_slug': self.post1_published_by_author1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only comment2_post1_author1_reply should be visible now
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['content'], self.comment2_post1_author1_reply.content)


    def test_create_comment_on_published_post_authenticated_user_success(self):
        self.authenticate_client_with_jwt(self.regular_user)
        url = reverse('blog:blogpost-comment-list', kwargs={'post_slug': self.post1_published_by_author1.slug})
        data = {"content": "RegularUser's new comment!"}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(BlogComment.objects.filter(
            blog_post=self.post1_published_by_author1,
            author=self.regular_user,
            content=data['content']
        ).exists())
        self.post1_published_by_author1.refresh_from_db()
        self.assertEqual(self.post1_published_by_author1.comment_count, 3) # Initial 2 + this new one

    def test_create_comment_on_draft_post_forbidden(self):
        self.authenticate_client_with_jwt(self.regular_user)
        url = reverse('blog:blogpost-comment-list', kwargs={'post_slug': self.post2_draft_by_author1.slug})
        data = {"content": "Trying to comment on draft."}
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanCommentOnPublicPost

    def test_update_own_comment_by_author_success(self):
        self.authenticate_client_with_jwt(self.regular_user) # regular_user is author of comment1
        url = reverse('blog:blogpost-comment-detail', kwargs={
            'post_slug': self.post1_published_by_author1.slug,
            'pk': self.comment1_post1_user_reg.pk
        })
        data = {"content": "Great post, Author1! (Updated by me)"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.comment1_post1_user_reg.refresh_from_db()
        self.assertEqual(self.comment1_post1_user_reg.content, data['content'])

    def test_approve_comment_action_by_moderator_success(self):
        self.comment1_post1_user_reg.is_approved = False # Make it unapproved first
        self.comment1_post1_user_reg.save()
        self.authenticate_client_with_jwt(self.admin_user) # admin is moderator
        url = reverse('blog:blogpost-comment-approve-comment', kwargs={
            'post_slug': self.post1_published_by_author1.slug,
            'pk': self.comment1_post1_user_reg.pk
        })
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.comment1_post1_user_reg.refresh_from_db()
        self.assertTrue(self.comment1_post1_user_reg.is_approved)

# TODO:
# - Test all permissions thoroughly for each action and user type.
# - Test filtering, searching, ordering for BlogPostViewSet.
# - Test pagination for list views.
# - Test error responses for invalid data in POST/PUT/PATCH more extensively.
# - Test other moderator actions on BlogCommentViewSet (hide, toggle user hide).
# - Test interaction with a Like model if integrated for blog posts/comments.
