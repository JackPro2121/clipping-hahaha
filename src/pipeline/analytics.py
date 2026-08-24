"""pipeline/analytics.py — Performance feedback loop via Buffer GraphQL metrics.

Fetches per-post metrics (views/reach/impressions/reactions) for every channel,
writes analytics.json for trend tracking, and posts a Slack digest showing
what content performs best. Runnable standalone:

    python src/pipeline/analytics.py [days]

The GraphQL schema was probed live: pagination args (first/after) live at the
posts-query level (NOT inside input), Post.metrics is a list of
{name, value, unit} triples, and per-service metric names differ
(IG/TikTok: Views/Reach, Facebook: Impressions).
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from buffer_api import _request, get_channels, get_org_id  # noqa: E402
from notifications.slack import send_slack_notification  # noqa: E402
from utils.config import load_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
ANALYTICS_FILE = ROOT / "analytics.json"

SENT_Q = """
query Sent($orgId: OrganizationId!, $channelId: ChannelId!, $first: Int!, $cursor: String) {
  posts(first: $first, after: $cursor, input: {
    organizationId: $orgId,
    filter: { channelIds: [$channelId], status: sent }
  }) {
    edges { node { id text sentAt metrics { name value unit } } }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# Metric names observed per service (Buffer normalizes nothing).
_VIEW_METRICS = ("Views", "Impressions")
_LIKE_METRICS = ("Reactions", "Likes")


def _post_views(metrics):
    return sum(metrics.get(k, 0) or 0 for k in _VIEW_METRICS)


def _post_likes(metrics):
    return sum(metrics.get(k, 0) or 0 for k in _LIKE_METRICS)


def fetch_channel_posts(org_id, channel_id, days=30):
    """Return [{sentAt, text, views, reach, likes}] for posts in the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = None
    rows = []
    while True:
        variables = {"orgId": org_id, "channelId": channel_id, "first": 50}
        if cursor:
            variables["cursor"] = cursor
        data = _request(SENT_Q, variables=variables)
        page = data["posts"]
        for edge in page["edges"]:
            node = edge["node"]
            sent_at = node.get("sentAt")
            if not sent_at:
                continue
            dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
            if dt < cutoff:
                continue
            m = {mm["name"]: mm["value"] for mm in node.get("metrics") or []}
            rows.append(
                {
                    "sent_at": sent_at,
                    "text": (node.get("text") or "")[:120],
                    "views": _post_views(m),
                    "reach": m.get("Reach", 0) or 0,
                    "likes": _post_likes(m),
                }
            )
        if page["pageInfo"]["hasNextPage"]:
            cursor = page["pageInfo"]["endCursor"]
        else:
            break
    return rows


def build_digest(channels_posts, days=30):
    """Aggregate per-channel stats + top performers into a digest dict."""
    per_channel = {}
    all_posts = []
    for service, rows in channels_posts.items():
        views = sum(r["views"] for r in rows)
        reach = sum(r["reach"] for r in rows)
        likes = sum(r["likes"] for r in rows)
        best = max(rows, key=lambda r: r["views"]) if rows else None
        per_channel[service] = {
            "posts": len(rows),
            "views": views,
            "reach": reach,
            "likes": likes,
            "avg_views": round(views / len(rows), 1) if rows else 0,
            "best_views": best["views"] if best else 0,
        }
        for r in rows:
            row = dict(r)
            row["service"] = service
            all_posts.append(row)

    top = sorted(all_posts, key=lambda r: r["views"], reverse=True)[:3]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "channels": per_channel,
        "top_posts": [
            {k: r[k] for k in ("service", "views", "likes", "text")}
            for r in top
        ],
        "total_views": sum(c["views"] for c in per_channel.values()),
        "total_posts": sum(c["posts"] for c in per_channel.values()),
    }


def save_analytics(digest):
    """Persist digest to analytics.json, keeping a rolling history (last 90)."""
    history = []
    if ANALYTICS_FILE.exists():
        try:
            history = json.loads(ANALYTICS_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            history = []
    history.append(digest)
    ANALYTICS_FILE.write_text(
        json.dumps(history[-90:], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return ANALYTICS_FILE


def send_digest(digest):
    """Post the performance digest to Slack (never raises)."""
    try:
        lines = [
            f"*{svc}*: {c['posts']} posts | {c['views']} views | avg {c['avg_views']}/post"
            for svc, c in digest["channels"].items()
        ]
        tops = [
            f"  {t['views']} views ({t['service']}): {t['text'][:60]}"
            for t in digest["top_posts"]
        ]
        payload = {
            "text": (
                f"📊 *{digest['window_days']}d performance*: "
                f"{digest['total_posts']} posts, {digest['total_views']} total views\n"
                + "\n".join(lines)
                + ("\n\n*Top posts:*\n" + "\n".join(tops) if tops else "")
            )
        }
        send_slack_notification(payload)
    except Exception as exc:
        print(f"Slack digest failed: {str(exc)[:100]}")


def main(days=30, notify=True):
    cfg = load_config()
    services = cfg.get("buffer", {}).get("services") or None
    org_id = get_org_id(prefer_services=services)
    channels = get_channels(services)
    channels_posts = {}
    for c in channels:
        try:
            channels_posts[c["service"]] = fetch_channel_posts(org_id, c["id"], days)
        except Exception as exc:
            print(f"{c['service']}: metrics fetch failed: {str(exc)[:120]}")
            channels_posts[c["service"]] = []

    digest = build_digest(channels_posts, days)
    path = save_analytics(digest)

    print(f"=== {days}-day digest ===")
    for svc, c in digest["channels"].items():
        print(
            f"{svc:10s} {c['posts']:3d} posts | {c['views']:6d} views | "
            f"avg {c['avg_views']:6.1f} | likes {c['likes']}"
        )
    for t in digest["top_posts"]:
        print(f"TOP {t['views']:6d} views [{t['service']}] {t['text'][:60]}")
    print(f"Saved -> {path}")

    if notify:
        send_digest(digest)
    return digest


if __name__ == "__main__":
    days_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    main(days=days_arg)
