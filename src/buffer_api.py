import os

import requests

API_URL = "https://api.buffer.com"


def _gql(query):
    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}",
        },
        json={"query": query},
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def get_org_id():
    data = _gql(
        "query GetOrganizations { account { organizations { id name } } }"
    )
    orgs = data["account"]["organizations"]
    if not orgs:
        raise RuntimeError("No Buffer organization found")
    return orgs[0]["id"]


def get_channels(services=None):
    org_id = get_org_id()
    query = (
        "query GetChannels($orgId: ID!) { "
        "channels(input: { organizationId: $orgId }) { id name service } }"
    )
    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}",
        },
        json={
            "query": query,
            "variables": {"orgId": org_id},
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    channels = payload["data"]["channels"]
    if services:
        channels = [c for c in channels if c["service"] in services]
    if not channels:
        raise RuntimeError("No Buffer channels found")
    return channels


def create_post(channel_id, text, video_url, thumbnail_offset=2000):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text } }
        ... on MutationError { message }
      }
    }
    """
    resp = requests.post(
        API_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}",
        },
        json={
            "query": query,
            "variables": {
                "input": {
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
            },
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    result = payload["data"]["createPost"]
    if "message" in result and result["message"]:
        raise RuntimeError(f"Buffer error: {result['message']}")
    return result["post"]["id"]