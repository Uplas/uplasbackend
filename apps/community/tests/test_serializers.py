from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework.test import APIRequestFactory # For providing request context

from ..models import (
    CommunityCategory, CommunityGroup, GroupMembership,
    CommunityPost, PostComment, PostReaction
)
from ..serializers import (
    CommunityCategorySerializer, CommunityGroupSerializer, GroupMembershipSerializer,
    CommunityPostSerializer, PostCommentSerializer, PostReactionSerializer,
    BasicUserSerializerForCommunity, BasicProjectTagSerializer # Import basic serializers used
)
from apps.projects.models import ProjectTag # Assuming shared tag model

User = get_user_model()

class CommunityCategorySerializerTests(TestCase):
    def test_category_serializer_valid_data(self):
        category_data = {"name": "Introductions", "description": "Say hello!"}
        # posts_count is read-only and annotated by view, not part of input data
        serializer = CommunityCategorySerializer(data=category_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        category = serializer.save()
        self.assertEqual(category.name, category_data["name"])

    def test_category_serializer_output_data(self):
        category = CommunityCategory.objects.create(name="Support", display_order=1)
        # Simulate annotation from viewset
        setattr(category, 'posts_count', 5) 
        serializer = CommunityCategorySerializer(category)
        data = serializer.data
        self.assertEqual(data['name'], "Support")
        self.assertEqual(data['display_order'], 1)
        self.assertEqual(data['posts_count'], 5)
        self.assertIn('slug', data)


class CommunityGroupSerializerTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(email="groupcreator@example.com", password="password", full_name="Group Creator")
        self.member_user = User.objects.create_user(email="groupmember@example.com", password="password", full_name="Group Member")
        self.group = CommunityGroup.objects.create(name="Study Buddies", creator=self.creator, description="Let's study together")
        
        self.factory = APIRequestFactory()
        self.request_member = self.factory.get('/')
        self.request_member.user = self.member_user
        
        self.request_non_member = self.factory.get('/')
        self.request_non_member.user = User.objects.create_user(email="non@ex.com", password="p")


    def test_group_serializer_output_data(self):
        """Test CommunityGroupSerializer output."""
        # Simulate annotations from view
        setattr(self.group, 'members_annotated_count', 0) # Initially no members except creator via GroupMembership model
        setattr(self.group, 'is_member_annotated', False)

        serializer = CommunityGroupSerializer(self.group, context={'request': self.request_non_member})
        data = serializer.data
        self.assertEqual(data['name'], self.group.name)
        self.assertEqual(data['creator']['full_name'], self.creator.full_name)
        self.assertEqual(data['members_count'], 0) # Relies on annotation or SerializerMethodField
        self.assertFalse(data['is_member'])

    def test_group_serializer_is_member_true(self):
        """Test is_member is true when user is a member."""
        GroupMembership.objects.create(user=self.member_user, group=self.group, role='member')
        # Simulate annotations
        setattr(self.group, 'members_annotated_count', 1)
        setattr(self.group, 'is_member_annotated', True)
        
        serializer = CommunityGroupSerializer(self.group, context={'request': self.request_member})
        data = serializer.data
        self.assertTrue(data['is_member'])
        self.assertEqual(data['members_count'], 1)


class GroupMembershipSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="membershipuser@example.com", password="password", full_name="Membership User")
        self.group = CommunityGroup.objects.create(name="Role Group", creator=self.user, description="d")
        self.membership = GroupMembership.objects.create(user=self.user, group=self.group, role='admin')

    def test_group_membership_serializer_output(self):
        serializer = GroupMembershipSerializer(self.membership)
        data = serializer.data
        self.assertEqual(data['user']['full_name'], self.user.full_name)
        self.assertEqual(data['group'], self.group.id) # PKRelatedField would show ID, if nested GroupSerializer then full object
        self.assertEqual(data['role'], 'admin')
        self.assertEqual(data['role_display'], 'Admin') # Check display value


class CommunityPostSerializerTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(email="postauthor_s@example.com", password="password", full_name="Post Author S")
        self.category = CommunityCategory.objects.create(name="Discussions")
        self.tag_general = ProjectTag.objects.create(name="General")
        self.post = CommunityPost.objects.create(
            author=self.author, title="First Post", content_html="<p>Hello world</p>", category=self.category
        )
        self.post.tags.add(self.tag_general)

        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.author # For user_reaction_type context

    def test_community_post_serializer_output(self):
        """Test CommunityPostSerializer basic output."""
        # Simulate annotated reaction for efficiency
        # setattr(self.post, 'current_user_reaction_on_post_annotated', None) # No reaction initially
        
        # Create context dictionary
        context_data = {'request': self.request}
        # If using the 'user_reactions_map' optimization from view for list context:
        # context_data['user_reactions_map'] = {self.post.id: None}


        serializer = CommunityPostSerializer(self.post, context=context_data)
        data = serializer.data
        self.assertEqual(data['title'], self.post.title)
        self.assertEqual(data['author']['full_name'], self.author.full_name)
        self.assertEqual(data['category']['name'], self.category.name)
        self.assertEqual(len(data['tags']), 1)
        self.assertEqual(data['tags'][0]['name'], self.tag_general.name)
        self.assertEqual(data['comment_count'], 0) # Denormalized field
        self.assertEqual(data['reaction_count'], 0) # Denormalized field
        self.assertIsNone(data['user_reaction_type']) # No reaction from this user yet

    def test_community_post_serializer_with_user_reaction(self):
        """Test user_reaction_type is serialized correctly."""
        PostReaction.objects.create(user=self.author, post=self.post, reaction_type='like')
        
        # Simulate annotation (if view provides it this way)
        # setattr(self.post, 'current_user_reaction_on_post_annotated', 'like')
        
        # Create context dictionary
        context_data = {'request': self.request}
        # If using the 'user_reactions_map' optimization from view:
        # context_data['user_reactions_map'] = {self.post.id: 'like'}


        serializer = CommunityPostSerializer(self.post, context=context_data)
        data = serializer.data
        self.assertEqual(data['user_reaction_type'], 'like')

    def test_community_post_serializer_create_valid(self):
        post_data = {
            "title": "New Post Title",
            "content_html": "<p>Some exciting content!</p>",
            "category_id": self.category.id, # Pass ID for writable related field
            "tag_ids": [self.tag_general.id]  # Pass list of IDs for M2M
        }
        # Serializer needs author from context (typically view's perform_create)
        serializer = CommunityPostSerializer(data=post_data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # To test save, we need to simulate how view sets the author:
        # saved_post = serializer.save(author=self.author)
        # self.assertEqual(saved_post.title, post_data['title'])
        # self.assertIn(self.tag_general, saved_post.tags.all())

    def test_community_post_serializer_content_required(self):
        post_data = {"title": "Missing Content Post"}
        serializer = CommunityPostSerializer(data=post_data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn('content_html', serializer.errors)


class PostCommentSerializerTests(TestCase):
    def setUp(self):
        self.comment_author = User.objects.create_user(email="commenter_s@example.com", password="password", full_name="Commenter S")
        post_author = User.objects.create_user(email="p_author_s@example.com", password="password")
        self.post = CommunityPost.objects.create(author=post_author, title="Post with Comments", content_html="...")
        self.comment1 = PostComment.objects.create(post=self.post, author=self.comment_author, content_html="First!")
        
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/')
        self.request.user = self.comment_author

    def test_post_comment_serializer_output(self):
        context_data = {'request': self.request}
        serializer = PostCommentSerializer(self.comment1, context=context_data)
        data = serializer.data
        self.assertEqual(data['content_html'], self.comment1.content_html)
        self.assertEqual(data['author']['full_name'], self.comment_author.full_name)
        self.assertEqual(data['reaction_count'], 0)
        self.assertEqual(data['replies_count'], 0)
        self.assertIsNone(data['user_reaction_type'])

    def test_post_comment_serializer_with_user_reaction(self):
        PostReaction.objects.create(user=self.comment_author, comment=self.comment1, reaction_type='heart')
        
        context_data = {'request': self.request}
        # Simulate annotation/prefetch if view provides it this way
        # setattr(self.comment1, 'current_user_reaction_on_comment_annotated', 'heart')
        # context_data['user_reactions_map'] = {self.comment1.id: 'heart'}


        serializer = PostCommentSerializer(self.comment1, context=context_data)
        data = serializer.data
        self.assertEqual(data['user_reaction_type'], 'heart')

    def test_post_comment_create_valid(self):
        comment_data = {"content_html": "A new insightful comment."}
        # Post and author set by view context
        serializer = PostCommentSerializer(data=comment_data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # saved_comment = serializer.save(author=self.comment_author, post=self.post)
        # self.assertEqual(saved_comment.content_html, comment_data['content_html'])

class PostReactionSerializerTests(TestCase):
    def setUp(self):
        self.reactor = User.objects.create_user(email="reactor_s@example.com", password="password", full_name="Reactor S")
        post_author = User.objects.create_user(email="post_author_r@example.com", password="password")
        self.post = CommunityPost.objects.create(author=post_author, title="Reactable Post", content_html="...")
        self.comment = PostComment.objects.create(post=self.post, author=post_author, content_html="Reactable Comment")
        
        self.factory = APIRequestFactory()
        self.request = self.factory.get('/') # For context
        self.request.user = self.reactor

    def test_post_reaction_serializer_create_for_post(self):
        data = {"post": self.post.id, "reaction_type": "like"}
        serializer = PostReactionSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # reaction = serializer.save(user=self.reactor) # User set by view
        # self.assertEqual(reaction.post, self.post)
        # self.assertEqual(reaction.reaction_type, 'like')

    def test_post_reaction_serializer_create_for_comment(self):
        data = {"comment": self.comment.id, "reaction_type": "heart"}
        serializer = PostReactionSerializer(data=data, context={'request': self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_post_reaction_serializer_missing_target(self):
        """Test fails if neither post nor comment is provided."""
        data = {"reaction_type": "laugh"}
        serializer = PostReactionSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors) # From validate method

    def test_post_reaction_serializer_both_targets(self):
        """Test fails if both post and comment are provided."""
        data = {"post": self.post.id, "comment": self.comment.id, "reaction_type": "laugh"}
        serializer = PostReactionSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_post_reaction_serializer_invalid_reaction_type(self):
        data = {"post": self.post.id, "reaction_type": "invalid_react"}
        serializer = PostReactionSerializer(data=data, context={'request': self.request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("reaction_type", serializer.errors)

    def test_post_reaction_serializer_output(self):
        reaction = PostReaction.objects.create(user=self.reactor, post=self.post, reaction_type='insightful')
        serializer = PostReactionSerializer(reaction, context={'request': self.request})
        data = serializer.data
        self.assertEqual(data['reaction_type'], 'insightful')
        self.assertEqual(data['reaction_type_display'], 'Insightful')
        self.assertEqual(data['user']['full_name'], self.reactor.full_name)
