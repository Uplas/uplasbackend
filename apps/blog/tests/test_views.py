from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import BlogCategory, BlogPost, BlogComment, Author, Tag
# Assuming Tag is from projects.models
from apps.projects.models import ProjectTag

User = get_user_model()

class BlogCategoryViewSetTests(APITestCase):
    def setUp(self):
        self.cat1 = BlogCategory.objects.create(name="Tech News", display_order=0)
        BlogCategory.objects.create(name="Tutorials", display_order=1)
        # Create a published post in cat1 to test published_post_count
        author = User.objects.create_user(email="catpostauthor@example.com", password="password")
        BlogPost.objects.create(title="Post in Tech News", author=author, category=self.cat1, content_html="c", status='published', publish_date=timezone.now())

        self.list_url = reverse('blog:blogcategory-list')
        self.detail_url = reverse('blog:blogcategory-detail', kwargs={'pk': self.cat1.pk})


    def test_list_blog_categories(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        # Assuming cat1 (Tech News) has a post and cat2 (Tutorials) doesn't for this annotation test
        self.assertEqual(response.data['results'][0]['name'], self.cat1.name) # display_order 0
        self.assertEqual(response.data['results'][0]['published_post_count'], 1)
        self.assertEqual(response.data['results'][1]['name'], "Tutorials")
        self.assertEqual(response.data['results'][1]['published_post_count'], 0)


    def test_retrieve_blog_category(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.cat1.name)


class AuthorViewSetTests(APITestCase): # Assuming admin-only for write ops
    def setUp(self):
        self.admin_user = User.objects.create_superuser(email="admin_blog@example.com", password="password", username="adminbloguser")
        self.uplas_user_for_author = User.objects.create_user(email="uplas_author@example.com", password="password", full_name="Uplas Author Profile")
        self.author1 = Author.objects.create(user=self.uplas_user_for_author, display_name="Dr. Uplas")
        self.author2_guest = Author.objects.create(display_name="Guest Author X")

        self.list_url = reverse('blog:blogauthor-list')
        self.detail_url_a1 = reverse('blog:blogauthor-detail', kwargs={'pk': self.author1.pk})
        self.client = APIClient()


    def test_list_authors_admin(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_list_authors_non_admin_fails(self):
        regular_user = User.objects.create_user(email="reg@example.com", password="p")
        self.client.force_authenticate(user=regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAdminUser permission

    def test_create_author_admin_succeeds(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {"display_name": "New Guest Author", "bio": "A bio."}
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Author.objects.filter(display_name="New Guest Author").exists())


class BlogPostViewSetTests(APITestCase):
    def setUp(self):
        self.author_user = User.objects.create_user(email="postauthor_v@example.com", password="password", full_name="PostView Author")
        self.staff_user = User.objects.create_user(email="staff_blog_v@example.com", password="password", is_staff=True, full_name="Staff BlogView")
        self.other_user = User.objects.create_user(email="other_blog_v@example.com", password="password")

        self.category = BlogCategory.objects.create(name="View Test Category")
        self.tag_general = Tag.objects.create(name="General View Test")

        self.post_published = BlogPost.objects.create(
            title="Published Post for Views", slug="published-post-views", author=self.author_user,
            content_html="<p>Public content.</p>", status='published', publish_date=timezone.now() - timezone.timedelta(days=1),
            category=self.category
        )
        self.post_published.tags.add(self.tag_general)

        self.post_draft_by_author = BlogPost.objects.create(
            title="Draft by Author User", slug="draft-by-author-user", author=self.author_user,
            content_html="<p>Draft content.</p>", status='draft'
        )
        self.post_draft_by_staff = BlogPost.objects.create( # Different author for permission tests
            title="Draft by Staff User", slug="draft-by-staff-user", author=self.staff_user,
            content_html="<p>Another draft.</p>", status='draft'
        )
        
        self.list_url = reverse('blog:blogpost-list')
        self.detail_published_url = reverse('blog:blogpost-detail', kwargs={'slug': self.post_published.slug})
        self.detail_draft_author_url = reverse('blog:blogpost-detail', kwargs={'slug': self.post_draft_by_author.slug})
        self.comments_url_published = reverse('blog:blogpost-manage-comments', kwargs={'slug': self.post_published.slug})
        self.related_url_published = reverse('blog:blogpost-related-posts', kwargs={'slug': self.post_published.slug})


    def test_list_posts_unauthenticated(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1) # Only published
        self.assertEqual(response.data['results'][0]['title'], self.post_published.title)

    def test_list_posts_author_sees_own_draft_and_published(self):
        self.client.force_authenticate(user=self.author_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = {p['title'] for p in response.data['results']}
        self.assertIn(self.post_published.title, titles)
        self.assertIn(self.post_draft_by_author.title, titles) # Author sees own draft
        self.assertNotIn(self.post_draft_by_staff.title, titles) # Does not see other's draft
        self.assertEqual(len(response.data['results']), 2)


    def test_list_posts_staff_sees_all(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3) # Staff sees all (published and all drafts)

    def test_retrieve_published_post_increments_view_count(self):
        initial_views = self.post_published.view_count
        response = self.client.get(self.detail_published_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post_published.refresh_from_db()
        self.assertEqual(self.post_published.view_count, initial_views + 1)

    def test_retrieve_own_draft_by_author_succeeds(self):
        self.client.force_authenticate(user=self.author_user)
        response = self.client.get(self.detail_draft_author_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.post_draft_by_author.title)

    def test_retrieve_others_draft_by_non_staff_author_fails(self):
        self.client.force_authenticate(user=self.author_user) # author_user is not staff
        detail_draft_staff_url = reverse('blog:blogpost-detail', kwargs={'slug': self.post_draft_by_staff.slug})
        response = self.client.get(detail_draft_staff_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Filtered by get_queryset

    def test_create_post_staff_succeeds(self):
        self.client.force_authenticate(user=self.staff_user)
        data = {
            "title": "Staff Created Post", "content_html": "Important announcement.",
            "status": "published", "category_id": self.category.id,
            "author_id": self.staff_user.id # Explicitly set author for ModelViewSet create
        }
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(BlogPost.objects.filter(title="Staff Created Post", author=self.staff_user).exists())

    def test_create_post_non_staff_fails(self):
        self.client.force_authenticate(user=self.other_user) # other_user is not staff
        data = {"title": "User Post Attempt", "content_html": "c", "status": "draft", "author_id": self.other_user.id}
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAdminUser for create


    def test_update_own_post_by_author_succeeds(self):
        self.client.force_authenticate(user=self.author_user)
        data = {"title": "My Updated Draft Title"}
        response = self.client.patch(self.detail_draft_author_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post_draft_by_author.refresh_from_db()
        self.assertEqual(self.post_draft_by_author.title, "My Updated Draft Title")

    def test_update_others_post_by_non_staff_author_fails(self):
        self.client.force_authenticate(user=self.author_user)
        detail_draft_staff_url = reverse('blog:blogpost-detail', kwargs={'slug': self.post_draft_by_staff.slug})
        data = {"title": "Attempting to edit staff draft"}
        response = self.client.patch(detail_draft_staff_url, data, format='json')
        # Will 404 first from get_object if author cannot see it, or 403 from permission if they can see but not edit.
        # Based on get_queryset, author_user won't see post_draft_by_staff, so 404 from get_object.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_own_post_by_author_succeeds(self):
        self.client.force_authenticate(user=self.author_user)
        response = self.client.delete(self.detail_draft_author_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BlogPost.objects.filter(slug=self.post_draft_by_author.slug).exists())

    # --- Comments on Post Tests (via BlogPostViewSet.manage_comments) ---
    def test_list_approved_comments_for_post(self):
        BlogComment.objects.create(post=self.post_published, author=self.other_user, content="Approved Comment", is_approved=True)
        BlogComment.objects.create(post=self.post_published, author_name="Guest", content="Unapproved", is_approved=False)
        response = self.client.get(self.comments_url_published)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['content'], "Approved Comment")

    def test_create_comment_authenticated_user(self):
        self.client.force_authenticate(user=self.other_user)
        data = {"content": "A valid comment from authenticated user."}
        response = self.client.post(self.comments_url_published, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(BlogComment.objects.filter(post=self.post_published, author=self.other_user).exists())

    def test_create_comment_guest_user(self):
        # Unauthenticated client
        data = {"author_name": "Visitor Joe", "content": "Nice post, from guest!"}
        response = self.client.post(self.comments_url_published, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(BlogComment.objects.filter(post=self.post_published, author_name="Visitor Joe").exists())

    def test_create_comment_guest_user_missing_name(self):
        data = {"content": "Trying to be anonymous guest."} # Missing author_name
        response = self.client.post(self.comments_url_published, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("author_name", response.data)

    def test_get_related_posts(self):
        # Create another published post in the same category
        BlogPost.objects.create(
            title="Related Post", slug="related-post", author=self.author_user,
            content_html="<p>Similar topic.</p>", status='published', publish_date=timezone.now(),
            category=self.category # Same category as self.post_published
        )
        response = self.client.get(self.related_url_published)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) > 0)
        self.assertEqual(response.data[0]['category']['name'], self.category.name)


class BlogCommentViewSetTests(APITestCase): # For managing individual comments
    def setUp(self):
        self.comment_author = User.objects.create_user(email="comment_author_v@example.com", password="password")
        self.staff = User.objects.create_user(email="comment_staff_v@example.com", password="password", is_staff=True)
        self.other_user = User.objects.create_user(email="comment_other_v@example.com", password="password")
        
        post_author = User.objects.create_user(email="comment_post_author_v@example.com", password="password")
        self.post = BlogPost.objects.create(author=post_author, title="Post for Individual Comments", content_html="...", status='published', publish_date=timezone.now())
        
        self.comment_by_author = BlogComment.objects.create(post=self.post, author=self.comment_author, content="My own comment.", is_approved=True)
        self.comment_guest = BlogComment.objects.create(post=self.post, author_name="Guesty", content="A guest comment.", is_approved=True)
        self.comment_unapproved = BlogComment.objects.create(post=self.post, author=self.other_user, content="Needs approval.", is_approved=False)

        self.detail_url_author_comment = reverse('blog:blogcomment-detail', kwargs={'pk': self.comment_by_author.pk})
        self.detail_url_guest_comment = reverse('blog:blogcomment-detail', kwargs={'pk': self.comment_guest.pk})
        self.detail_url_unapproved = reverse('blog:blogcomment-detail', kwargs={'pk': self.comment_unapproved.pk})


    def test_list_comments_unauthenticated_shows_approved(self):
        # Default list in BlogCommentViewSet shows approved comments
        list_url = reverse('blog:blogcomment-list') + f'?post_slug={self.post.slug}'
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2) # comment_by_author and comment_guest
        comment_contents = {c['content'] for c in response.data['results']}
        self.assertIn(self.comment_by_author.content, comment_contents)
        self.assertIn(self.comment_guest.content, comment_contents)

    def test_list_comments_staff_shows_all(self):
        self.client.force_authenticate(user=self.staff)
        list_url = reverse('blog:blogcomment-list') + f'?post_slug={self.post.slug}'
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3) # Staff sees unapproved too

    def test_update_own_comment_by_author(self):
        self.client.force_authenticate(user=self.comment_author)
        data = {"content": "My comment, updated."}
        response = self.client.patch(self.detail_url_author_comment, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.comment_by_author.refresh_from_db()
        self.assertEqual(self.comment_by_author.content, "My comment, updated.")

    def test_update_others_comment_by_non_staff_fails(self):
        self.client.force_authenticate(user=self.other_user) # Not author of comment_by_author
        data = {"content": "Trying to edit."}
        response = self.client.patch(self.detail_url_author_comment, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_guest_comment_by_staff_succeeds(self):
        self.client.force_authenticate(user=self.staff)
        data = {"content": "Guest comment moderated.", "is_approved": True} # Staff can change approval
        response = self.client.patch(self.detail_url_guest_comment, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.comment_guest.refresh_from_db()
        self.assertEqual(self.comment_guest.content, "Guest comment moderated.")

    def test_delete_own_comment_by_author(self):
        self.client.force_authenticate(user=self.comment_author)
        response = self.client.delete(self.detail_url_author_comment)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BlogComment.objects.filter(pk=self.comment_by_author.pk).exists())

    def test_delete_guest_comment_by_staff(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(self.detail_url_guest_comment)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BlogComment.objects.filter(pk=self.comment_guest.pk).exists())
