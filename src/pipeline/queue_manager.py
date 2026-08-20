"""queue_manager.py — Buffer queue depth monitor to prevent over-scheduling.

Monitors active scheduled posts per channel and prevents queue flooding.
"""

from buffer_api import _request, get_org_id


def get_channel_queue_depth(channel_id):
    """Retrieve the number of pending scheduled posts in a Buffer channel.

    Returns:
        int: Number of pending/scheduled posts, or 0 if query fails.
    """
    org_id = get_org_id()
    query = """
    query GetPendingPosts($orgId: OrganizationId!, $channelId: String!) {
      posts(input: {
        organizationId: $orgId,
        filter: {
          channelIds: [$channelId],
          status: SCHEDULED
        }
      }) {
        totalCount
      }
    }
    """
    try:
        data = _request(query, variables={"orgId": org_id, "channelId": channel_id})
        return data.get("posts", {}).get("totalCount", 0)
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
