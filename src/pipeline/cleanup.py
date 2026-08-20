"""cleanup.py — Automatic cleanup of older Cloudinary video uploads.

Prevents exceeding the 10GB free tier storage limit by purging clips older than N days.
"""

import os
from datetime import datetime, timezone, timedelta
import cloudinary
import cloudinary.api
import cloudinary.uploader


def cleanup_cloudinary_clips(folder="clips", keep_days=14):
    """Delete clips older than keep_days from Cloudinary.

    Args:
        folder: Cloudinary asset folder name (default: "clips").
        keep_days: Number of days to retain videos (default: 14).

    Returns:
        int: Number of deleted clips.
    """
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
    api_key = os.environ.get("CLOUDINARY_API_KEY")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        print("Cloudinary credentials not set, skipping storage cleanup")
        return 0

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    deleted_count = 0

    try:
        # Fetch uploaded video assets under prefix
        response = cloudinary.api.resources(
            type="upload",
            resource_type="video",
            prefix=folder,
            max_results=500,
        )
        resources = response.get("resources") or []

        for item in resources:
            public_id = item.get("public_id")
            created_at_str = item.get("created_at")

            if not public_id or not created_at_str:
                continue

            try:
                # Format: 2026-08-20T10:00:00Z
                created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_dt < cutoff:
                    cloudinary.uploader.destroy(public_id, resource_type="video")
                    deleted_count += 1
            except Exception as exc:
                print(f"Failed to delete {public_id}: {exc}")

        if deleted_count > 0:
            print(f"Cloudinary cleanup: Deleted {deleted_count} clips older than {keep_days} days")
        else:
            print("Cloudinary cleanup: No expired clips to delete")

    except Exception as exc:
        print(f"Cloudinary cleanup encountered an error: {exc}")

    return deleted_count
