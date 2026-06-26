"""
skip_post.py

Marks a post in the queue as skipped. Called by the publish-approved workflow
when the dashboard sends a skip_post dispatch event, so "Skip" actually
persists instead of only changing in the browser tab.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
QUEUE_PATH = ROOT / "docs" / "data" / "queue.json"


def main():
    if len(sys.argv) != 2:
        print("Usage: python skip_post.py <post_id>", file=sys.stderr)
        sys.exit(1)

    post_id = sys.argv[1]
    queue = json.loads(QUEUE_PATH.read_text())
    found = False
    for post in queue:
        if post["id"] == post_id:
            post["status"] = "skipped"
            found = True

    if not found:
        print(f"Post {post_id} not found", file=sys.stderr)
        sys.exit(1)

    QUEUE_PATH.write_text(json.dumps(queue, indent=2))
    print(f"Marked {post_id} as skipped")


if __name__ == "__main__":
    main()
