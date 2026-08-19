import os

import cloudinary
from cloudinary.uploader import upload


def upload_video(path, folder="clips"):
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )
    public_id = os.path.splitext(os.path.basename(path))[0]
    result = upload(
        path,
        resource_type="video",
        folder=folder,
        public_id=public_id,
    )
    return result["secure_url"]