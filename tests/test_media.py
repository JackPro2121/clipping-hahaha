from unittest.mock import patch
import os
from media import upload_video


def test_upload_video_unique_public_id(monkeypatch):
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "test_cloud")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "test_key")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "test_secret")

    public_ids = []

    def mock_upload(path, resource_type, folder, public_id):
        public_ids.append(public_id)
        return {"secure_url": f"https://res.cloudinary.com/test/{folder}/{public_id}.mp4"}

    with patch("media.upload", side_effect=mock_upload):
        url1 = upload_video("clip_01.mp4")
        url2 = upload_video("clip_01.mp4")

    assert len(public_ids) == 2
    assert public_ids[0].startswith("clip_01_")
    assert public_ids[1].startswith("clip_01_")
    assert public_ids[0] != public_ids[1], "Public IDs should be unique across uploads"
    assert url1 != url2
