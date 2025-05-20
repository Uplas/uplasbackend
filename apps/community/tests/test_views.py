from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch # If any external calls were made (not typical for this app)

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from ..models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
from apps.projects.models import ProjectTag # Assuming shared tag model

User = get_user_model()

class CommunityCategoryViewSetTests(APITestCase):
    def setUp(self):
        self.cat1 = CommunityCategory.objects.create(name="General", display_order=1)
        self.cat2 = CommunityCategory.objects.create(name="Feedback", display_order=0)
        self.list_url = reverse('community:communitycategory-list')

    def test_list_categories(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['results'][0]['name'], self.cat2.name) # Ordered by display_order
        self.assertIn('posts_count', response.data['results'][0]) # Check for annotated count


class CommunityGroupViewSetTests(APITestCase):
    def setUp(self):
        self.creator = User.objects.create_user(email="creator_cg@example.com", password="password", full_name="Group Creator")
        self.member1 = User.objects.create_user(email="member1_cg@example.com", password="password", full_name="Member One")
        self.non_member = User.objects.create_user(email="nonmember_cg@example.com", password="password", full_name="Non Member")

        self.public_group = CommunityGroup.objects.create(name="Public Study Group", creator=self.creator, description="Open to all", is_private=False)
        self.private_group = CommunityGroup.objects.create(name="Private Project Team", creator=self.creator, description="Invite only", is_private=True)
        # Creator is automatically made an admin member by model's perform_create
        # GroupMembership.objects.create(user=self.creator, group=self.private_group, role='admin') # Already done by perform_create in view
        GroupMembership.objects.create(user=self.member1, group=self.private_group, role='member')


        self.list_create_url = reverse('community:communitygroup-list')
        self.detail_public_url = reverse('community:communitygroup-detail', kwargs={'slug': self.public_group.slug})
        self.detail_private_url = reverse('community:communitygroup-detail', kwargs={'slug': self.private_group.slug})
        self.join_public_url = reverse('community:communitygroup-join-group', kwargs={'slug': self.public_group.slug})
        self.leave_public_url = reverse('community:communitygroup-leave-group', kwargs={'slug': self.public_group.slug})
        self.posts_public_url = reverse('community:communitygroup-list-group-posts', kwargs={'slug': self.public_group.slug})


    def test_list_groups_unauthenticated(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only see public_group
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], self.public_group.name)

    def test_list_groups_authenticated_non_member(self):
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see public_group, and private_group if they are a member (not in this case)
        group_names = {g['name'] for g in response.data['results']}
        self.assertIn(self.public_group.name, group_names)
        self.assertNotIn(self.private_group.name, group_names) # Non-member shouldn't see private group

    def test_list_groups_authenticated_member_of_private(self):
        self.client.force_authenticate(user=self.member1) # member1 is in private_group
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        group_names = {g['name'] for g in response.data['results']}
        self.assertIn(self.public_group.name, group_names)
        self.assertIn(self.private_group.name, group_names) # Member should see private group

    def test_create_group_authenticated(self):
        self.client.force_authenticate(user=self.non_member)
        data = {"name": "My New Group", "description": "A group by non_member."}
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(CommunityGroup.objects.filter(name="My New Group", creator=self.non_member).exists())
        new_group = CommunityGroup.objects.get(name="My New Group")
        self.assertTrue(GroupMembership.objects.filter(user=self.non_member, group=new_group, role='admin').exists())

    def test_retrieve_public_group(self):
        response = self.client.get(self.detail_public_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.public_group.name)

    def test_retrieve_private_group_member_succeeds(self):
        self.client.force_authenticate(user=self.member1)
        response = self.client.get(self.detail_private_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.private_group.name)

    def test_retrieve_private_group_non_member_fails(self):
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(self.detail_private_url)
        # The get_queryset in the view should filter it out, leading to 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


    def test_join_public_group_success(self):
        self.client.force_authenticate(user=self.non_member)
        response = self.client.post(self.join_public_url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(GroupMembership.objects.filter(user=self.non_member, group=self.public_group).exists())

    def test_join_public_group_already_member(self):
        GroupMembership.objects.create(user=self.non_member, group=self.public_group)
        self.client.force_authenticate(user=self.non_member)
        response = self.client.post(self.join_public_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_leave_public_group_success(self):
        GroupMembership.objects.create(user=self.non_member, group=self.public_group)
        self.client.force_authenticate(user=self.non_member)
        response = self.client.post(self.leave_public_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertFalse(GroupMembership.objects.filter(user=self.non_member, group=self.public_group).exists())

    def test_creator_cannot_leave_if_sole_admin(self):
        # Creator is auto-admin. No other admins.
        self.client.force_authenticate(user=self.creator)
        leave_private_url = reverse('community:communitygroup-leave-group', kwargs={'slug': self.private_group.slug})
        response = self.client.post(leave_private_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sole admin", response.data['detail'])


    def test_list_posts_in_public_group(self):
        CommunityPost.objects.create(author=self.creator, group=self.public_group, title="Post in Public", content_html="...")
        self.client.force_authenticate(user=self.non_member) # Non-member can see posts in public group
        response = self.client.get(self.posts_public_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_create_post_in_group_member_succeeds(self):
        GroupMembership.objects.create(user=self.member1, group=self.public_group) # Make member1 a member of public_group
        self.client.force_authenticate(user=self.member1)
        data = {"title": "Member Post", "content_html": "My content"}
        response = self.client.post(self.posts_public_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(CommunityPost.objects.filter(title="Member Post", group=self.public_group, author=self.member1).exists())

    def test_create_post_in_group_non_member_fails(self): # Assuming CanPostInGroup requires membership
        self.client.force_authenticate(user=self.non_member) # non_member is not in public_group
        data = {"title": "Non Member Post", "content_html": "My content"}
        response = self.client.post(self.posts_public_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # CanPostInGroup permission


class CommunityPostViewSetTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email="postuser1@example.com", password="password", full_name="Post User One")
        self.user2 = User.objects.create_user(email="postuser2@example.com", password="password", full_name="Post User Two")
        self.category = CommunityCategory.objects.create(name="General Posts")
        self.tag1 = ProjectTag.objects.create(name="Discussion")
        self.post1 = CommunityPost.objects.create(
            author=self.user1, title="First Discussion", slug="first-discussion",
            content_html="<p>Content 1</p>", category=self.category,
            last_activity_at=timezone.now() - timezone.timedelta(hours=1)
        )
        self.post1.tags.add(self.tag1)
        self.post2_closed = CommunityPost.objects.create(
            author=self.user2, title="Closed Topic", slug="closed-topic",
            content_html="<p>No comments please.</p>", is_closed=True
        )

        self.list_create_url = reverse('community:communitypost-list')
        self.detail_url_post1 = reverse('community:communitypost-detail', kwargs={'slug': self.post1.slug})
        self.comments_url_post1 = reverse('community:communitypost-manage-comments', kwargs={'slug': self.post1.slug})
        self.react_url_post1 = reverse('community:communitypost-react-to-item', kwargs={'slug': self.post1.slug})


    def test_list_posts(self):
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_create_post_authenticated(self):
        self.client.force_authenticate(user=self.user1)
        data = {
            "title": "My New Uplas Post",
            "content_html": "<p>Awesome thoughts here.</p>",
            "category_id": self.category.id,
            "tag_ids": [self.tag1.id]
        }
        response = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(CommunityPost.objects.filter(title="My New Uplas Post", author=self.user1).exists())

    def test_retrieve_post_increments_view_count(self):
        initial_views = self.post1.view_count
        response = self.client.get(self.detail_url_post1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.view_count, initial_views + 1)

    def test_update_own_post(self):
        self.client.force_authenticate(user=self.user1)
        data = {"title": "First Discussion [Updated]", "content_html": "<p>Updated content.</p>"}
        response = self.client.patch(self.detail_url_post1, data, format='json') # PATCH for partial update
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.title, "First Discussion [Updated]")

    def test_update_others_post_fails(self):
        self.client.force_authenticate(user=self.user2) # user2 is not author of post1
        data = {"title": "Malicious Update"}
        response = self.client.patch(self.detail_url_post1, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # IsAuthorOrReadOnly

    def test_delete_own_post(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.delete(self.detail_url_post1)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CommunityPost.objects.filter(slug=self.post1.slug).exists())

    # --- Comments on Post Tests ---
    def test_list_comments_for_post(self):
        PostComment.objects.create(post=self.post1, author=self.user2, content_html="A comment")
        response = self.client.get(self.comments_url_post1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_create_comment_on_post_authenticated(self):
        self.client.force_authenticate(user=self.user2)
        data = {"content_html": "My insightful comment."}
        response = self.client.post(self.comments_url_post1, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(PostComment.objects.filter(post=self.post1, author=self.user2).exists())
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.comment_count, 1)

    def test_create_comment_on_closed_post_fails(self):
        self.client.force_authenticate(user=self.user1)
        closed_post_comments_url = reverse('community:communitypost-manage-comments', kwargs={'slug': self.post2_closed.slug})
        data = {"content_html": "Trying to comment."}
        response = self.client.post(closed_post_comments_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Reactions on Post Tests ---
    def test_react_to_post_success_and_toggle(self):
        self.client.force_authenticate(user=self.user2)
        # First reaction (like)
        response_like = self.client.post(self.react_url_post1, {"reaction_type": "like"}, format='json')
        self.assertEqual(response_like.status_code, status.HTTP_201_CREATED, response_like.data)
        self.assertEqual(response_like.data['data']['reaction_type'], 'like')
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.reaction_count, 1)

        # React again with same type (unlike)
        response_unlike = self.client.post(self.react_url_post1, {"reaction_type": "like"}, format='json')
        self.assertEqual(response_unlike.status_code, status.HTTP_200_OK) # Changed from 204, view returns updated count
        self.assertEqual(response_unlike.data['status'], 'Reaction removed.')
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.reaction_count, 0)

        # React with different type (new reaction)
        response_heart = self.client.post(self.react_url_post1, {"reaction_type": "heart"}, format='json')
        self.assertEqual(response_heart.status_code, status.HTTP_201_CREATED)
        self.post1.refresh_from_db()
        self.assertEqual(self.post1.reaction_count, 1)


class PostCommentViewSetTests(APITestCase): # For individual comment management
    def setUp(self):
        self.user_comment_author = User.objects.create_user(email="commentauthor@example.com", password="password")
        self.user_other = User.objects.create_user(email="othercommentuser@example.com", password="password")
        post_author = User.objects.create_user(email="comment_post_author@example.com", password="password")
        self.post = CommunityPost.objects.create(author=post_author, title="Post for Comments", content_html="...")
        self.comment = PostComment.objects.create(post=self.post, author=self.user_comment_author, content_html="Original comment")
        
        self.detail_url = reverse('community:postcomment-detail', kwargs={'pk': self.comment.pk})
        self.react_url = reverse('community:postcomment-react-to-item', kwargs={'pk': self.comment.pk})


    def test_update_own_comment(self):
        self.client.force_authenticate(user=self.user_comment_author)
        data = {"content_html": "Updated comment content."}
        response = self.client.patch(self.detail_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.content_html, "Updated comment content.")

    def test_delete_own_comment(self):
        self.client.force_authenticate(user=self.user_comment_author)
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PostComment.objects.filter(pk=self.comment.pk).exists())
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 0) # Check signal


    def test_react_to_comment_success(self):
        self.client.force_authenticate(user=self.user_other)
        response = self.client.post(self.react_url, {"reaction_type": "thumbs_up"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.reaction_count, 1)


class TrendingTagsViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="taguser@example.com", password="password")
        self.tag_hot = ProjectTag.objects.create(name="HotTopic")
        self.tag_cool = ProjectTag.objects.create(name="CoolStuff")
        self.tag_old = ProjectTag.objects.create(name="OldNews")

        # Recent posts
        post1 = CommunityPost.objects.create(author=self.user, title="P1", content_html="c", created_at=timezone.now() - timezone.timedelta(days=1))
        post1.tags.add(self.tag_hot, self.tag_cool)
        post2 = CommunityPost.objects.create(author=self.user, title="P2", content_html="c", created_at=timezone.now() - timezone.timedelta(days=2))
        post2.tags.add(self.tag_hot)
        # Old post
        post_old = CommunityPost.objects.create(author=self.user, title="OldP", content_html="c", created_at=timezone.now() - timezone.timedelta(days=10))
        post_old.tags.add(self.tag_old, self.tag_hot)

        self.url = reverse('community:trending-tags')

    def test_get_trending_tags_default_7_days(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # HotTopic (2 recent), CoolStuff (1 recent)
        self.assertEqual(response.data[0]['name'], self.tag_hot.name) # HotTopic should be first
        self.assertEqual(response.data[1]['name'], self.tag_cool.name)
        # Check usage_count if serializer exposes it (it's used for ordering)
        # For this, ProjectTagSerializer would need to include 'usage_count' or similar

    def test_get_trending_tags_custom_days(self):
        response = self.client.get(self.url, {'days': '1'}) # Only post1 tags
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2) # HotTopic, CoolStuff from post1
        # Order might be HotTopic then CoolStuff or vice-versa depending on secondary sort (name)

    def test_get_trending_tags_no_recent_posts(self):
        # Delete recent posts for this test
        CommunityPost.objects.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7)).delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0) # No tags from posts in last 7 days
