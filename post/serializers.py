from rest_framework import serializers
from .models import *
from django.core.files.storage import default_storage
from accounts.models import Profile
from interest.models import SubCategory

""" Serializers for Posts """
class LikeSerializer(serializers.ModelSerializer):
    """ Serializer for Like """
    user_name = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = Like
        fields = ['id', 'user', 'user_name', 'post', 'created_at']
        read_only_fields = ['user', 'created_at']

    def create(self, validated_data):
        user = self.context['request'].user
        post = validated_data['post']
        
        if post.status != 'approved':
            raise serializers.ValidationError("You can only like approved posts.")
        
        like, created = Like.objects.get_or_create(user=user, post=post)
    
        if created and post.user != user:
            Notification.objects.create(
                recipient=post.user,
                sender=user,
                notification_type='like',
                post=post
            )
        return like
        """ context is just a dictionary that can carry extra info to the serializer
        and request.user is provided by Django’s authentication system, 
        means: give me the currently logged-in user making this request. """


class RecursiveSerializer(serializers.Serializer):
    """Serializer for recursive nested comments"""
    def to_representation(self, instance):
        serializer = self.parent.parent.__class__(instance, context=self.context)
        return serializer.data

class CommentSerializer(serializers.ModelSerializer):
    """ Serializer for Comment """
    user_name = serializers.CharField(source='user.username', read_only=True)
    replies = RecursiveSerializer(many=True, read_only=True)
    replies_count = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField(source='user.avatar', read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'user', 'user_name', 'avatar', 'post', 'parent', 'content', 'created_at', 'updated_at', 'replies', 'replies_count', 'can_edit', 'can_delete']
        read_only_fields = ['user', 'created_at', 'updated_at']

    def get_avatar(self, obj):
        try:
            return obj.user.profile.avatar.url if obj.user.profile.avatar else None
        except Profile.DoesNotExist:
            return None

    def get_replies_count(self, obj):
        return obj.replies.count()

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.user == request.user
        return False

    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.user == request.user or obj.post.user == request.user
        return False

    def validate(self, data):
        if data.get('post') and data['post'].status != 'approved':
            raise serializers.ValidationError("You can only comment on approved posts.")
        
        if data.get('parent') and data.get('post'):
            if data['parent'].post != data['post']:
                raise serializers.ValidationError("Parent comment must belong to the same post.")
        
        return data
    
    def create(self, validated_data):
        user = self.context['request'].user
        comment = Comment.objects.create(**validated_data)
        
        # Notify post owner
        if comment.post.user != user:
            Notification.objects.create(
                recipient=comment.post.user,
                sender=user,
                notification_type='comment',
                post=comment.post,
                comment=comment
            )
        
        if comment.parent and comment.parent.user != user and comment.parent.user != comment.post.user:
            Notification.objects.create(
                recipient=comment.parent.user,
                sender=user,
                notification_type='comment',
                post=comment.post,
                comment=comment
            )
        
        return comment


class ShareSerializer(serializers.ModelSerializer):
    """ Serializer for Share """
    user_name = serializers.CharField(source='user.username', read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)
    
    class Meta:
        model = Share
        fields = ['id', 'user', 'user_name', 'post', 'post_title', 'created_at']
        read_only_fields = ['user', 'created_at']

    def validate_post(self, value):
        """Ensure only approved posts can be shared"""
        if value.status != 'approved':
            raise serializers.ValidationError("You can only share approved posts.")
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        post = validated_data['post']
        
        share = Share.objects.create(user=user, post=post)

        if post.user != user:
            Notification.objects.create(
                recipient=post.user,
                sender=user,
                notification_type='share',
                post=post
            )
        return share


class PostSerializer(serializers.ModelSerializer):
    """ Serializer for Post """
    user_name = serializers.CharField(source='user.username', read_only=True)
    avatar = serializers.SerializerMethodField(source='user.avatar', read_only=True)


    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    shares_count = serializers.IntegerField(source='shares.count', read_only=True)
    comments = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    media_files = serializers.ListField(
        child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=True),
        write_only=True,
        required=False
    )
    subcategories = serializers.SerializerMethodField()
    
    class Meta:
        model = Post
        fields = [
            'id', 'user', 'user_name', 'avatar', 'title', 'post_type', 'content', 'media_file', 'media_files', 'link',
            'tags', 'subcategories', 'status', 'created_at', 'updated_at',
            'likes_count', 'comments_count', 'shares_count', 'comments',
            'can_edit', 'can_delete', 'is_liked', 'community',
        ]
        read_only_fields = ['user', 'likes_count', 'comments_count', 'shares_count', 'created_at', 'updated_at']
    
    def get_subcategories(self, obj):
        """Safely get subcategories - handles case where field doesn't exist yet"""
        try:
            # Check if the field exists on the model
            if hasattr(obj, '_meta') and hasattr(obj._meta, 'get_field'):
                try:
                    obj._meta.get_field('subcategories')
                    # Field exists, try to access it
                    if hasattr(obj, 'subcategories'):
                        try:
                            return [sub.id for sub in obj.subcategories.all()]
                        except (AttributeError, Exception):
                            return []
                except Exception:
                    # Field doesn't exist in model
                    return []
        except Exception:
            pass
        return []

    def get_avatar(self, obj):
        try:
            return obj.user.profile.avatar.url if obj.user.profile.avatar else None
        except Profile.DoesNotExist:
            return None
        
    def create(self, validated_data):
        media_files = validated_data.pop('media_files', [])
        # Note: subcategories is now a SerializerMethodField (read-only)
        # If you need to set subcategories, handle it separately in the view
        post = Post.objects.create(**validated_data)
        
        # Try to set subcategories if provided in request data (not validated_data since it's read-only now)
        request = self.context.get('request')
        if request and request.data.get('subcategories'):
            try:
                subcategory_ids = request.data.get('subcategories', [])
                if isinstance(subcategory_ids, str):
                    import json
                    subcategory_ids = json.loads(subcategory_ids)
                if hasattr(post, 'subcategories') and subcategory_ids:
                    post.subcategories.set(subcategory_ids)
            except Exception:
                # Field doesn't exist yet or invalid data, skip
                pass

        if media_files:
            file_paths = []
            for media_file in media_files:
                file_path = default_storage.save(
                    f'posts/{post.id}/{media_file.name}',
                    media_file
                )
                file_paths.append(file_path)

            post.media_file = file_paths
            post.save()

        return post
    
    def update(self, instance, validated_data):
        media_files = validated_data.pop('media_files', None)
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Handle subcategories from request data (since SerializerMethodField is read-only)
        request = self.context.get('request')
        if request and hasattr(request, 'data'):
            subcategory_ids = request.data.get('subcategories')
            if subcategory_ids is not None:
                try:
                    # Handle both list and JSON string formats
                    if isinstance(subcategory_ids, str):
                        import json
                        subcategory_ids = json.loads(subcategory_ids)
                    if isinstance(subcategory_ids, list) and hasattr(instance, 'subcategories'):
                        instance.subcategories.set(subcategory_ids)
                except Exception:
                    # Field doesn't exist yet or invalid data, skip silently
                    pass
        
        if media_files is not None:
            # Delete old files if needed
            if instance.media_file:
                for old_file in instance.media_file:
                    if default_storage.exists(old_file):
                        default_storage.delete(old_file)
            
            # Save new files
            file_paths = []
            for media_file in media_files:
                file_path = default_storage.save(
                    f'posts/{instance.id}/{media_file.name}',
                    media_file
                )
                file_paths.append(file_path)
            
            instance.media_file = file_paths
        
        instance.save()
        return instance
    

    def get_comments(self, obj):
        top_level_comments = obj.comments.filter(parent=None)
        return CommentSerializer(top_level_comments, many=True, context=self.context).data

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.user == request.user
        return False

    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.user == request.user
        return False
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Like.objects.filter(user=request.user, post=obj).exists()
        return False
    
class FollowSerializer(serializers.ModelSerializer):
    """ Serializer for Follow """
    follower_name = serializers.CharField(source='follower.username', read_only=True)
    following_name = serializers.CharField(source='following.username', read_only=True)
    
    # Follower profile fields
    follower_avatar = serializers.SerializerMethodField()
    follower_about = serializers.SerializerMethodField()
    
    # Following profile fields
    following_avatar = serializers.SerializerMethodField()
    following_about = serializers.SerializerMethodField()

    class Meta:
        model = Follow
        fields = [
            'id', 'follower', 'follower_name', 'follower_avatar', 'follower_about',
            'following', 'following_name', 'following_avatar', 'following_about', 
            'created_at'
        ]
        read_only_fields = ['follower', 'created_at']
    
    def get_follower_avatar(self, obj):
        """Get follower's avatar URL"""
        try:
            if hasattr(obj.follower, 'profile') and obj.follower.profile.avatar:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.follower.profile.avatar.url)
                return obj.follower.profile.avatar.url
        except Exception:
            pass
        return None
    
    def get_follower_about(self, obj):
        """Get follower's about text"""
        try:
            if hasattr(obj.follower, 'profile') and obj.follower.profile.about:
                return obj.follower.profile.about
        except Exception:
            pass
        return None
    
    def get_following_avatar(self, obj):
        """Get following user's avatar URL"""
        try:
            if hasattr(obj.following, 'profile') and obj.following.profile.avatar:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.following.profile.avatar.url)
                return obj.following.profile.avatar.url
        except Exception:
            pass
        return None
    
    def get_following_about(self, obj):
        """Get following user's about text"""
        try:
            if hasattr(obj.following, 'profile') and obj.following.profile.about:
                return obj.following.profile.about
        except Exception:
            pass
        return None

    def validate(self, data):
        # Prevent users from following themselves
        follower = self.context['request'].user
        following = data.get('following')
        
        if follower == following:
            raise serializers.ValidationError("You cannot follow yourself.")
        
        return data

    def create(self, validated_data):
        follower = self.context['request'].user
        following = validated_data['following']
        
        follow, created = Follow.objects.get_or_create(
            follower=follower,
            following=following
        )
        
        # Create notification when someone follows
        if created:
            Notification.objects.create(
                recipient=following,
                sender=follower,
                notification_type='follow'
            )
        
        return follow

class UserSuggestionSerializer(serializers.Serializer):
    """ Serializer for User Suggestions with follow status """
    id = serializers.IntegerField()
    username = serializers.CharField()
    avatar = serializers.SerializerMethodField()
    about = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    followers_count = serializers.IntegerField()
    following_count = serializers.IntegerField()
    posts_count = serializers.IntegerField()
    is_following = serializers.BooleanField()
    follow_id = serializers.IntegerField(allow_null=True)
    
    def get_avatar(self, obj):
        """Get user's avatar URL"""
        try:
            if hasattr(obj, 'profile') and obj.profile.avatar:
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.profile.avatar.url)
                return obj.profile.avatar.url
        except Exception:
            pass
        return None
    
    def get_about(self, obj):
        """Get user's about text"""
        try:
            if hasattr(obj, 'profile') and obj.profile.about:
                return obj.profile.about
        except Exception:
            pass
        return None
    
    def get_display_name(self, obj):
        """Get user's display name"""
        try:
            if hasattr(obj, 'profile') and obj.profile.display_name:
                return obj.profile.display_name
        except Exception:
            pass
        return obj.username
    
class PostReportSerializer(serializers.ModelSerializer):
    """ Serializer for Post Report """
    reporter_name = serializers.CharField(source='reporter.username', read_only=True)
    reporter_id = serializers.IntegerField(source='reporter.id', read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)
    post_id = serializers.IntegerField(source='post.id', read_only=True)
    post_author = serializers.CharField(source='post.user.username', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.username', read_only=True, allow_null=True)

    class Meta:
        model = PostReport
        fields = [
            'id', 'reporter', 'reporter_name', 'reporter_id',
            'post', 'post_id', 'post_title', 'post_author',
            'reason', 'description', 'status',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['reporter', 'status', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at']

    def validate(self, data):
        # Prevent users from reporting their own posts
        post = data.get('post')
        reporter = self.context['request'].user
        
        if post:
            # If post is an ID, get the actual post object
            if isinstance(post, (int, str)):
                try:
                    from .models import Post
                    post_obj = Post.objects.get(pk=post)
                except Post.DoesNotExist:
                    raise serializers.ValidationError("Post not found.")
            else:
                post_obj = post
            
            # Check if user is trying to report their own post
            if post_obj.user == reporter:
                raise serializers.ValidationError("You cannot report your own post.")
            
            # Check if user has already reported this post
            # Handle case where table doesn't exist yet (migration not run)
            try:
                from .models import PostReport
                if PostReport.objects.filter(reporter=reporter, post=post_obj).exists():
                    raise serializers.ValidationError("You have already reported this post.")
            except Exception as e:
                # If table doesn't exist, skip duplicate check (will fail on save anyway)
                # But at least we can validate the other checks
                # Only skip if it's a table-related error, not a validation error
                if isinstance(e, serializers.ValidationError):
                    raise
                pass
        
        return data


class NotificationSerializer(serializers.ModelSerializer):
    """ Serializer for Notification """
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    post_title = serializers.CharField(source='post.title', read_only=True)
    community_name = serializers.CharField(source='community.name', read_only=True)
    community_title = serializers.CharField(source='community.title', read_only=True)
    
    class Meta:
        model = Notification
        fields = [
            'id', 'sender', 'sender_name', 'notification_type', 
            'post', 'post_title', 'comment', 'community', 'community_name', 
            'community_title', 'is_read', 'created_at'
        ]
        read_only_fields = ['sender', 'created_at']

class UserProfileSerializer(serializers.Serializer):
    """ Serializer for User Profile """
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    followers_count = serializers.IntegerField()
    following_count = serializers.IntegerField()
    posts_count = serializers.IntegerField()
    is_following = serializers.BooleanField()

""" End of Serializers for Posts """