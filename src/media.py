import hmac
import hashlib
import os
import time

import requests


def upload_video(path, folder="clips"):
    cloud = os.environ["CLOUDINARY_CLOUD_NAME"]
    api_key = os.environ["CLOUDINARY_API_KEY"]
    api_secret = os.environ["CLOUDINARY_API_SECRET"]

    params = {
        "timestamp": str(int(time.time())),
        "folder": folder,
        "public_id": os.path.splitext(os.path.basename(path))[0],
        "resource_type": "video",
        "type": "upload",
    }
    to_sign = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    params["signature"] = hmac.new(
        api_secret.encode(), to_sign.encode(), hashlib.sha1
    ).hexdigest()
    params["api_key"] = api_key

    with open(path, "rb") as f:
        files = {"file": (os.path.basename(path), f, "video/mp4")}
        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
            data=params,
            files=files,
            timeout=300,
        )
    resp.raise_for_status()
    return resp.json()["secure_url"]