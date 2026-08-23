"""buffer_api.py — Buffer GraphQL client.

Auth: Bearer token from BUFFER_API_KEY env var.
All requests go through the single _request() helper to avoid duplicating header setup.
"""

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.errors import QueueFullError  # noqa: E402

API_URL = "https://api.buffer.com"


def _get_token():
    token = os.environ.get("BUFFER_API_KEY")
    if not token:
        raise RuntimeError(
            "BUFFER_API_KEY environment variable is not set. "
            "Check GitHub Actions secrets or your local .env."
        )
    return token


def _request(query, variables=None, max_retries=3):
    """Single shared helper for all Buffer GraphQL requests with retry on transient errors.

    Args:
        query: GraphQL query/mutation string.
        variables: Optional dict of GraphQL variables.
        max_retries: Number of retry attempts on network/server errors or 429/5xx (default: 3).

    Returns:
        The ``data`` field from the response payload.

    Raises:
        RuntimeError: On GraphQL errors or persistent HTTP failures.
    """
    import time
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_get_token()}",
    }

    last_exc = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait_time = (2 ** attempt) * 2
                print(f"Buffer API HTTP {resp.status_code}, retrying in {wait_time}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                raise RuntimeError(f"Buffer GraphQL error: {data['errors']}")
            return data["data"]
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 2
                print(f"Buffer request failed ({exc}), retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                break

    raise RuntimeError(f"Buffer request failed after {max_retries} attempts: {last_exc}")


def get_org_id():
    """Return the org that actually has connected channels.

    The account can hold multiple organizations (order is not stable), so
    picking organizations[0] nondeterministically broke channel access.
    """
    data = _request(
        "query GetOrganizations { account { organizations { id name } } }"
    )
    orgs = data["account"]["organizations"]
    if not orgs:
        raise RuntimeError("No Buffer organization found under this API key.")
    if len(orgs) == 1:
        return orgs[0]["id"]
    channels_query = (
        "query GetChannels($orgId: OrganizationId!) { "
        "channels(input: { organizationId: $orgId }) { id } }"
    )
    for org in orgs:
        ch = _request(channels_query, variables={"orgId": org["id"]}).get("channels") or []
        if ch:
            return org["id"]
    return orgs[0]["id"]


def get_channels(services=None):
    org_id = get_org_id()
    query = (
        "query GetChannels($orgId: OrganizationId!) { "
        "channels(input: { organizationId: $orgId }) { id name service } }"
    )
    data = _request(query, variables={"orgId": org_id})
    channels = data["channels"]
    if services:
        channels = [c for c in channels if c["service"] in services]
    if not channels:
        raise RuntimeError(
            f"No Buffer channels found (services filter: {services!r}). "
            "Check that the correct BUFFER_API_KEY is set (the org with your TikTok channel)."
        )
    return channels


def create_post(channel_id, text, video_url, thumbnail_offset=2000, service=None, mode="shareNow"):
    """Queue or immediately publish a video post to a Buffer channel.

    Args:
        channel_id: Buffer Channel ID.
        text: Post caption.
        video_url: Cloudinary hosted MP4 URL.
        thumbnail_offset: Milliseconds offset for video thumbnail.
        service: Platform name ('tiktok' or 'instagram').
        mode: Buffer share mode ('shareNow' for instant publish, 'addToQueue' for scheduling).

    Raises:
        QueueFullError: When Buffer's scheduled-post limit is reached.
        RuntimeError: On other Buffer-level errors.
    """
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text } }
        ... on MutationError { message }
      }
    }
    """
    post_input = {
        "text": text,
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": mode or "shareNow",
        "assets": [
            {
                "video": {
                    "url": video_url,
                    "metadata": {"thumbnailOffset": thumbnail_offset},
                }
            }
        ],
    }

    # Platform-specific metadata
    if service == "instagram":
        post_input["metadata"] = {
            "instagram": {
                "type": "reel",
                "shouldShareToFeed": True,
            }
        }
    elif service == "facebook":
        post_input["metadata"] = {
            "facebook": {
                "type": "reel",
            }
        }

    variables = {"input": post_input}
    data = _request(query, variables=variables)
    result = data["createPost"]

    # GraphQL union: MutationError has a "message" field, PostActionSuccess has "post"
    if "message" in result and result["message"]:
        msg = result["message"]
        if "limit reached" in msg.lower() or "scheduled posts" in msg.lower():
            raise QueueFullError(f"Buffer queue full: {msg}")
        raise RuntimeError(f"Buffer createPost error: {msg}")

    post = result.get("post") or {}
    post_id = post.get("id")
    if not post_id:
        raise RuntimeError(f"Buffer createPost returned unexpected payload (missing post.id): {result}")

    return post_id