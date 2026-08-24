"""queue_manager.py — Buffer queue depth monitor to prevent over-scheduling.

Monitors active scheduled posts per channel and prevents queue flooding.
"""

from buffer_api import _request, get_org_id

# BUG-01 fix: org_id never changes within a run — cache it at module level
# to avoid one extra GraphQL API call per clip × per channel.
_ORG_ID_CACHE = None


def _get_org_id_cached():
    """Return org_id, fetching from API only on first call per process.

    Prefer-services disambiguates multi-org accounts (a Twitter-only org
    shares the account and 'first with channels' can resolve to it).
    """
    global _ORG_ID_CACHE
    if _ORG_ID_CACHE is None:
        _ORG_ID_CACHE = get_org_id(
            prefer_services=("tiktok", "instagram", "facebook")
        )
    return _ORG_ID_CACHE


def get_channel_queue_depth(channel_id):
    """Retrieve the number of pending scheduled posts in a Buffer channel.

    Note: the API key is not authorized for ``posts.totalCount`` (FORBIDDEN),
    so we fetch edges and count client-side instead.
    """
    org_id = _get_org_id_cached()
    query = """
    query GetPendingPosts($orgId: OrganizationId!, $channelId: ChannelId!) {
      posts(input: {
        organizationId: $orgId,
        filter: {
          channelIds: [$channelId],
          status: scheduled
        }
      }) {
        edges { node { id } }
      }
    }
    """
    try:
        data = _request(query, variables={"orgId": org_id, "channelId": channel_id})
        edges = data.get("posts", {}).get("edges") or []
        return len(edges)
    except Exception as exc:
        print(f"Could not retrieve queue depth for channel {channel_id}: {exc}")
        return 0


def can_queue_posts(channel_id, max_queue_depth=20):
    """Check whether a channel has room in its queue for new posts.

    Args:
        channel_id: Buffer channel ID.
        max_queue_depth: Maximum allowed scheduled posts in queue.

    Returns:
        tuple[bool, int]: (allowed, current_queue_depth)
    """
    depth = get_channel_queue_depth(channel_id)
    if depth >= max_queue_depth:
        return False, depth
    return True, depth
