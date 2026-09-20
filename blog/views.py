# blog/views.py
#
# =============================================================================
#  SMART CACHE LAYER — GUIDED ACTIVITY
#  Advanced Python Programming | ALU BSE
# =============================================================================
#
#  This file contains three API views. Your job is to add caching to each one.
#  Read each TODO carefully — they build on each other.
#
#  Run the timing script first (docs/ACTIVITY.md → Level 1) to see
#  how slow the uncached responses are before you begin.
# =============================================================================
from django.core.cache import cache
import time
import logging

from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from .models import Post
from .serializers import PostSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LEVEL 2 — Shared Cache (Public Data)
# ---------------------------------------------------------------------------

class PostListView(APIView):
    """
    GET  /api/posts/       — Returns all published posts.
    POST /api/posts/       — Creates a new post (authenticated users only).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        # ---------------------------------------------------------------
        # TODO (Level 2): Implement cache-aside for this endpoint.
        #
        # Requirements:
        #   - Cache key: should be shared across ALL users (it's public data)
        #   - TTL: 300 seconds (5 minutes)
        #   - On cache miss: query the DB, store in cache, return data
        #   - On cache hit: return cached data directly
        #
        # Hint: use `cache.get(key)` and `cache.set(key, value, timeout)`
        # ---------------------------------------------------------------

        # REMOVE these two lines once you implement the cache below
        posts = Post.objects.filter(status=Post.STATUS_PUBLISHED).select_related("author")
        serializer = PostSerializer(posts, many=True)
        return Response(serializer.data)

    def post(self, request):
        # ---------------------------------------------------------------
        # TODO (Level 4): After saving the new post, invalidate the cache
        # so the next GET reflects the new data.
        #
        # Question: which cache key do you need to delete here?
        # ---------------------------------------------------------------

        serializer = PostSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(author=request.user)
            # YOUR CACHE INVALIDATION CODE HERE
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# LEVEL 2 (continued) — Single Post Cache
# ---------------------------------------------------------------------------

class PostDetailView(APIView):
    """
    GET /api/posts/<post_id>/ — Returns a single published post.
    """

    permission_classes = [AllowAny]

    def get(self, request, post_id: int):
        cache_key = f"posts:details:{post_id}"

        #1. Check cache
        cashed_post = cache.get(cache_key)
        if cached_post is not None:
            return Response(cached_post)
        try:
            post = Post.objects.select_related("author").get(
                id=post_id, status=Post.STATUS_PUBLISHED
            )
        except Post.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PostSerializer(post)

        cache.set(cache_key, serializer.data, timeout=CACHE_TTL_POST_DETAIL)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# LEVEL 3 — User-Isolated Cache (Personal Data)
# ---------------------------------------------------------------------------

class MyDraftsView(APIView):
    """
    GET /api/posts/my-drafts/ — Returns draft posts for the logged-in user only.

    !! SECURITY CRITICAL !!
    This endpoint returns private data. Every student must ensure
    that User A can never see User B's drafts under any circumstances.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ---------------------------------------------------------------
        # TODO (Level 3): Implement user-isolated cache-aside.
        #
        # Requirements:
        #   - Cache key: MUST include the user's ID — never use a generic key
        #   - TTL: 120 seconds (2 minutes — personal data should expire quickly)
        #   - Auth check: already handled by permission_classes above
        #
        # SECURITY QUESTION to answer in your code comment:
        #   What would happen if you used the key "my-drafts" for all users?
        # ---------------------------------------------------------------

        # REMOVE these lines once you implement the cache below
        drafts = Post.objects.filter(
            author=request.user,
            status=Post.STATUS_DRAFT
        ).select_related("author")

        serializer = PostSerializer(drafts, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# BONUS — Deliberately Broken View (Level 3 Bug-Spotting)
# ---------------------------------------------------------------------------

class BrokenDraftsView(APIView):
    """
    GET /api/posts/broken-drafts/

    This view has a critical security bug.
    Your task: read the code, find the bug, and explain it in the activity sheet.
    DO NOT fix the code here — write your answer in docs/ACTIVITY.md.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # !! BUG: find it, name it, explain the real-world impact !!
        data = cache.get("my-drafts")
        if data is None:
            drafts = Post.objects.filter(
                author=request.user,
                status=Post.STATUS_DRAFT
            ).select_related("author")
            serializer = PostSerializer(drafts, many=True)
            data = serializer.data
            cache.set("my-drafts", data, timeout=120)
        return Response(data)
