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


def _request(query, variables=None):
    """Single shared helper for all Buffer GraphQL requests.

    Args:
        query: GraphQL query/mutation string.
        variables: Optional dict of GraphQL variables.

    Returns:
        The ``data`` field from the response payload.

    Raises:
        RuntimeError: On GraphQL errors or HTTP failures.
    """
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_get_token()}",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(f"Buffer GraphQL error: {data['errors']}")
    return data["data"]


def get_org_id():
    data = _request(
        "query GetOrganizations { account { organizations { id name } } }"
    )
    orgs = data["account"]["organizations"]
    if not orgs:
        raise RuntimeError("No Buffer organization found under this API key.")
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


def create_post(channel_id, text, video_url, thumbnail_offset=2000, service=None):
    """Queue a video post to a Buffer channel.

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
        "mode": "addToQueue",
        "assets": [
            {
                "video": {
                    "url": video_url,
                    "metadata": {"thumbnailOffset": thumbnail_offset},
                }
            }
        ],
    }

    # Instagram requires post type (reel) and shouldShareToFeed flag
    if service == "instagram":
        post_input["metadata"] = {
            "instagram": {
                "type": "reel",
                "shouldShareToFeed": True,
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

    return result["post"]["id"]