"""
publish.py

Called when a post is approved on the dashboard. If LinkedIn API credentials
are present (i.e. your Community Management API access is approved), it
publishes directly. Otherwise it just marks the post as "ready for manual
posting" — nothing is silently lost while you wait on LinkedIn's approval.

This script does NOT auto-publish without the explicit approval step having
already happened — that approval is recorded by the dashboard before this
ever runs.
"""

import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
QUEUE_PATH = ROOT / "docs" / "data" / "queue.json"

LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_ORG_URN = os.environ.get("LINKEDIN_ORG_URN")  # e.g. "urn:li:organization:12345678"

LINKEDIN_API_BASE = "https://api.linkedin.com/rest"
LINKEDIN_API_VERSION = "202602"  # update to current LinkedIn API version string


def has_linkedin_credentials() -> bool:
    return bool(LINKEDIN_ACCESS_TOKEN and LINKEDIN_ORG_URN)


def svg_to_png_bytes(svg_string: str) -> bytes:
    """
    Converts SVG to PNG for upload. Requires 'cairosvg' (see requirements.txt).
    LinkedIn's image upload endpoint expects a raster format.
    """
    import cairosvg
    return cairosvg.svg2png(bytestring=svg_string.encode("utf-8"), output_width=1200, output_height=1200)


def register_image_upload() -> dict:
    resp = requests.post(
        f"{LINKEDIN_API_BASE}/images?action=initializeUpload",
        headers={
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "LinkedIn-Version": LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={"initializeUploadRequest": {"owner": LINKEDIN_ORG_URN}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["value"]


def upload_image_bytes(upload_url: str, image_bytes: bytes) -> None:
    resp = requests.put(upload_url, data=image_bytes, timeout=60)
    resp.raise_for_status()


def create_post(text: str, image_urn: str) -> dict:
    resp = requests.post(
        f"{LINKEDIN_API_BASE}/posts",
        headers={
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "LinkedIn-Version": LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={
            "author": LINKEDIN_ORG_URN,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "content": {"media": {"id": image_urn}},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return {"post_urn": resp.headers.get("x-restli-id")}


def publish_to_linkedin(post: dict) -> dict:
    full_text = f"{post['hook_text']}\n\n{post['body']}\n\n{post['cta']}"
    png_bytes = svg_to_png_bytes(post["svg"])

    upload_info = register_image_upload()
    upload_image_bytes(upload_info["uploadUrl"], png_bytes)
    result = create_post(full_text, upload_info["image"])
    return result


def mark_status(post_id: str, status: str, detail: str = "") -> None:
    queue = json.loads(QUEUE_PATH.read_text())
    for post in queue:
        if post["id"] == post_id:
            post["status"] = status
            if detail:
                post["status_detail"] = detail
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def main():
    if len(sys.argv) != 2:
        print("Usage: python publish.py <post_id>", file=sys.stderr)
        sys.exit(1)

    post_id = sys.argv[1]
    queue = json.loads(QUEUE_PATH.read_text())
    post = next((p for p in queue if p["id"] == post_id), None)
    if not post:
        print(f"Post {post_id} not found in queue", file=sys.stderr)
        sys.exit(1)

    if not has_linkedin_credentials():
        mark_status(post_id, "ready_for_manual_post",
                    "LinkedIn API not yet approved — copy this post into LinkedIn's native scheduler.")
        print(f"No LinkedIn API credentials yet. Post {post_id} marked ready for manual posting.")
        return

    try:
        result = publish_to_linkedin(post)
        mark_status(post_id, "published", detail=result.get("post_urn", ""))
        print(f"Published {post_id} to LinkedIn: {result}")
    except Exception as e:
        mark_status(post_id, "publish_failed", detail=str(e))
        print(f"Failed to publish {post_id}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
