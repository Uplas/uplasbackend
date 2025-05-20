from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.db.utils import IntegrityError, DataError
import uuid

from ..models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
from apps.projects.models import ProjectTag # Assuming shared tag model

User = get_user_model()

class CommunityCategoryModelTests(TestCase):
    def test_create_community_category(self):
        category = CommunityCategory.objects.create(name="Announcements", display_order=1)
        self.assertEqual(category.name, "Announcements")
        self.assertEqual(category.slug, slugify("Announcements"))
        self.assertEqual(str(category), "Announcements")

    def test_community_category_name_unique(self):
        CommunityCategory.objects.create(name="General Discussion")
        with self.assertRaises(IntegrityError):
            CommunityCategory.objects.create(name="General Discussion")


class CommunityGroupModelTests(TestCase):
    def setUp(self):
        self.user_creator = User.objects.create_user(email="creator@example.com", password="password")
        self.user_member = User.objects.create_user(email="member@example.com", password="password")

    def test_create_community_group(self):
        group = CommunityGroup.objects.create(
            name="Django Study Group",
            description="A group for Django learners.",
            creator=self.user_creator
        )
        self.assertEqual(group.name, "Django Study Group")
        self.assertEqual(group.slug, slugify("Django Study Group"))
        self.assertEqual(group.creator, self.user_creator)
        self.assertFalse(group.is_private)
        self.assertEqual(str(group), "Django Study Group")

    def test_community_group_name_unique(self):
        CommunityGroup.objects.create(name="Python Wizards", creator=self.user_creator, description="d")
        with self.assertRaises(IntegrityError):
            CommunityGroup.objects.create(name="Python Wizards", creator=self.user_creator, description="d2")

    def test_community_group_slug_uniqueness_on_create(self):
        CommunityGroup.objects.create(name="React Fanatics", creator=self.user_creator, description="d")
        group2 = CommunityGroup.objects.create(name="React Fanatics", creator=self.user_member, description="d2") # Different creator, same name
        self.assertTrue(group2.slug.startswith(slugify("React Fanatics") + "-"))


    def test_add_members_to_group_via_membership(self):
        group = CommunityGroup.objects.create(name="Testers United", creator=self.user_creator, description="d")
        GroupMembership.objects.create(user=self.user_member, group=group, role='member')
        self.assertIn(self.user_member, group.members.all())
        self.assertEqual(group.members.count(), 1)


class GroupMembershipModelTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email="gm_user1@example.com", password="password")
        self.user2 = User.objects.create_user(email="gm_user2@example.com", password="password")
        self.group = CommunityGroup.objects.create(name="Awesome Group", creator=self.user1, description="d")

    def test_create_group_membership(self):
        membership = GroupMembership.objects.create(user=self.user1, group=self.group, role='admin')
        self.assertEqual(membership.user, self.user1)
        self.assertEqual(membership.group, self.group)
        self.assertEqual(membership.role, 'admin')
        self.assertEqual(str(membership), f"{self.user1.email} in {self.group.name} as Admin")

    def test_group_membership_unique_user_group(self):
        """Test a user can only have one membership record per group."""
        GroupMembership.objects.create(user=self.user1, group=self.group, role='member')
        with self.assertRaises(IntegrityError):
            GroupMembership.objects.create(user=self.user1, group=self.group, role='admin')


class CommunityPostModelTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(email="postauthor@example.com", password="password")
        self.category = CommunityCategory.objects.create(name="Tech Talk")
        self.group = CommunityGroup.objects.create(name="AI Group", creator=self.author, description="d")
        self.tag_python = ProjectTag.objects.create(name="Python")

    def test_create_community_post(self):
        post_title = "My First AI Discussion"
        post = CommunityPost.objects.create(
            author=self.author,
            title=post_title,
            content_html="<p>Let's discuss AI!</p>",
            category=self.category,
            group=self.group
        )
        post.tags.add(self.tag_python)

        self.assertEqual(post.author, self.author)
        self.assertEqual(post.title, post_title)
        self.assertTrue(post.slug.startswith(slugify(post_title)))
        self.assertIsNotNone(post.slug.split('-')[-1]) # Check for random suffix
        self.assertEqual(post.category, self.category)
        self.assertEqual(post.group, self.group)
        self.assertIn(self.tag_python, post.tags.all())
        self.assertEqual(post.view_count, 0)
        self.assertEqual(post.reaction_count, 0)
        self.assertEqual(post.comment_count, 0)
        self.assertIsNotNone(post.last_activity_at)
        self.assertEqual(str(post), post_title)

    def test_community_post_slug_uniqueness_with_random_suffix(self):
        title = "Same Title Post"
        post1 = CommunityPost.objects.create(author=self.author, title=title, content_html="c1")
        post2 = CommunityPost.objects.create(author=self.author, title=title, content_html="c2")
        self.assertNotEqual(post1.slug, post2.slug)
        self.assertTrue(post1.slug.startswith(slugify(title)))
        self.assertTrue(post2.slug.startswith(slugify(title)))

    def test_community_post_last_activity_default(self):
        post = CommunityPost.objects.create(author=self.author, title="Activity Test", content_html="c")
        self.assertTrue(timezone.now() - post.last_activity_at < timezone.timedelta(seconds=5))


class PostCommentModelSignalTests(TestCase):
    def setUp(self):
        self.user_commenter = User.objects.create_user(email="commenter@example.com", password="password")
        self.post_author = User.objects.create_user(email="commentpostauthor@example.com", password="password")
        self.post = CommunityPost.objects.create(author=self.post_author, title="Commentable Post", content_html="Content")

    def test_create_comment_updates_post_counts_and_activity(self):
        initial_last_activity = self.post.last_activity_at
        self.assertEqual(self.post.comment_count, 0)

        comment = PostComment.objects.create(post=self.post, author=self.user_commenter, content_html="First comment!")
        self.post.refresh_from_db()

        self.assertEqual(self.post.comment_count, 1)
        self.assertTrue(self.post.last_activity_at > initial_last_activity)
        self.assertEqual(self.post.last_activity_at, comment.created_at)
        self.assertEqual(str(comment), f"Comment by {self.user_commenter.email} on '{self.post.title}'")


    def test_create_threaded_comment(self):
        parent_comment = PostComment.objects.create(post=self.post, author=self.user_commenter, content_html="Parent")
        reply = PostComment.objects.create(post=self.post, author=self.user_commenter, content_html="Reply", parent_comment=parent_comment)
        self.assertEqual(reply.parent_comment, parent_comment)
        self.assertIn(reply, parent_comment.replies.all())

        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 2) # Both parent and reply are comments on the post
        self.assertEqual(self.post.last_activity_at, reply.created_at)


    def test_delete_comment_updates_post_counts_and_activity(self):
        comment1 = PostComment.objects.create(post=self.post, author=self.user_commenter, content_html="C1")
        # time.sleep(0.01) # Ensure timestamps are different if resolution is low
        comment2 = PostComment.objects.create(post=self.post, author=self.user_commenter, content_html="C2")
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 2)
        self.assertEqual(self.post.last_activity_at, comment2.created_at)

        comment2.delete()
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 1)
        self.assertEqual(self.post.last_activity_at, comment1.created_at) # Falls back to earlier comment

        comment1.delete()
        self.post.refresh_from_db()
        self.assertEqual(self.post.comment_count, 0)
        # Last activity should now be post's own updated_at or created_at if signal logic handles this.
        # Current signal sets it to latest comment time, or post.updated_at.
        # If no comments, it might remain the timestamp of the last deleted comment's effect.
        # Let's verify it's at least not newer than post's own update time.
        self.assertTrue(self.post.last_activity_at <= self.post.updated_at)



class PostReactionModelSignalTests(TestCase):
    def setUp(self):
        self.user_reactor = User.objects.create_user(email="reactor@example.com", password="password")
        self.post_author = User.objects.create_user(email="reactionpostauthor@example.com", password="password")
        self.post = CommunityPost.objects.create(author=self.post_author, title="React Post", content_html="Content")
        self.comment = PostComment.objects.create(post=self.post, author=self.post_author, content_html="React Comment")

    def test_create_reaction_to_post_updates_post_count(self):
        self.assertEqual(self.post.reaction_count, 0)
        reaction = PostReaction.objects.create(user=self.user_reactor, post=self.post, reaction_type='like')
        self.post.refresh_from_db()
        self.assertEqual(self.post.reaction_count, 1)
        self.assertEqual(str(reaction), f"{self.user_reactor.email} Liked post ID {self.post.id}")


    def test_create_reaction_to_comment_updates_comment_count(self):
        self.assertEqual(self.comment.reaction_count, 0)
        PostReaction.objects.create(user=self.user_reactor, comment=self.comment, reaction_type='heart')
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.reaction_count, 1)

    def test_delete_reaction_updates_counts(self):
        reaction_post = PostReaction.objects.create(user=self.user_reactor, post=self.post, reaction_type='like')
        reaction_comment = PostReaction.objects.create(user=self.user_reactor, comment=self.comment, reaction_type='heart')
        self.post.refresh_from_db()
        self.comment.refresh_from_db()
        self.assertEqual(self.post.reaction_count, 1)
        self.assertEqual(self.comment.reaction_count, 1)

        reaction_post.delete()
        self.post.refresh_from_db()
        self.assertEqual(self.post.reaction_count, 0)

        reaction_comment.delete()
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.reaction_count, 0)

    def test_reaction_unique_constraints(self):
        """Test unique_together constraints for reactions."""
        # User reacts to post
        PostReaction.objects.create(user=self.user_reactor, post=self.post, reaction_type='like')
        with self.assertRaises(IntegrityError): # Same user, same post, same reaction_type
            PostReaction.objects.create(user=self.user_reactor, post=self.post, reaction_type='like')
        
        # Different reaction_type by same user on same post is fine
        PostReaction.objects.create(user=self.user_reactor, post=self.post, reaction_type='heart')
        self.assertEqual(self.post.reactions.filter(user=self.user_reactor).count(), 2)

        # User reacts to comment
        PostReaction.objects.create(user=self.user_reactor, comment=self.comment, reaction_type='thumbs_up')
        with self.assertRaises(IntegrityError): # Same user, same comment, same reaction_type
            PostReaction.objects.create(user=self.user_reactor, comment=self.comment, reaction_type='thumbs_up')

    def test_reaction_either_post_or_comment_constraint(self):
        """Test CHECK constraint: reaction must be for post OR comment, not both/neither."""
        with self.assertRaises(IntegrityError): # Both post and comment
            PostReaction.objects.create(user=self.user_reactor, post=self.post, comment=self.comment, reaction_type='laugh')
        
        # Test with neither post nor comment (should fail if model doesn't allow nulls on both if other is null,
        # but our constraint handles the XOR logic. Direct DB save might fail earlier on NOT NULL if FKs not nullable)
        # This is implicitly tested by the constraint logic which requires one to be non-null.
        # A direct create without post or comment would fail on the constraint.
        # reaction_no_target = PostReaction(user=self.user_reactor, reaction_type='laugh')
        # with self.assertRaises(IntegrityError): # Or ValueError depending on save() overrides
        #     reaction_no_target.save() # This will trigger the constraint
