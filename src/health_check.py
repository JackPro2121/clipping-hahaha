"""health_check.py — Daily automated health checker for pipeline state and Buffer queue.

Can be run via GitHub Actions scheduled workflow (.github/workflows/health-check.yml).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from notifications.slack import send_slack_alert, send_slack_notification
from utils.state import load_state

ROOT = Path(__file__).resolve().parent.parent


def check_pipeline_health():
    """Analyze current sources state and identify anomalies or stale queues."""
    state = load_state()
    sources = state.get("sources") or []

    pending = [s for s in sources if s.get("status") == "pending"]
    failed = [s for s in sources if s.get("status") == "failed"]
    stale_retries = [s for s in pending if s.get("retry_count", 0) >= 3]

    print(f"Health Check: {len(sources)} active sources ({len(pending)} pending, {len(failed)} failed)")

    issues = []
    if failed:
        issues.append(f"• *{len(failed)} permanently failed sources* requiring attention.")
    if stale_retries:
        issues.append(f"• *{len(stale_retries)} pending sources* in heavy retry backoff (>=3 retries).")

    if issues:
        details = "\n".join(issues)
        print(f"Health alert: {details}")
        send_slack_alert("Pipeline Health Warning", details, is_error=True)
    else:
        print("Health Check OK: All sources healthy and up-to-date.")
        send_slack_notification(
            {
                "text": "🟢 Clip & Post Health Check: All systems healthy. No stuck or failed queues.",
            }
        )

    return len(issues) == 0


if __name__ == "__main__":
    check_pipeline_health()
