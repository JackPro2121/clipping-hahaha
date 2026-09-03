import os
import uuid

import cloudinary
from cloudinary.uploader import upload


def upload_video(path, folder="clips"):
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    base_name = os.path.splitext(os.path.basename(path))[0]
    unique_id = f"{base_name}_{uuid.uuid4().hex[:8]}"
    result = upload(
        path,
        resource_type="video",
        folder=folder,
        public_id=unique_id,
    )
    return result["secure_url"]