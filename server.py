"""
server.py — Local dashboard server for Nour's competitor monitor
-----------------------------------------------------------------
Run with:  python server.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, send_from_directory, abort
from pathlib import Path
import json
import os
import sys
import mimetypes

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = Flask(__name__, static_folder="dashboard", static_url_path="")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "instagram"

# ── Helpers ─────────────────────────────────────────────────────────────────────
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".webp", ".gif"}

def is_media(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS

def relative_url(path: Path) -> str:
    """Convert an absolute path to a URL the frontend can fetch."""
    return "/media/" + path.relative_to(DATA_DIR).as_posix()

def load_json_sidecar(media_path: Path) -> dict:
    """Load the JSON metadata sidecar for a media file."""
    # Try exact match first, then stem match
    sidecar = media_path.with_suffix(".json")
    if sidecar.exists():
        with open(sidecar, "r", encoding="utf-8") as f:
            return json.load(f)

    # Try stem-based match (instaloader sometimes names differently)
    for f in media_path.parent.glob(f"{media_path.stem}*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            return json.load(fh)

    return {}

def read_profile(username: str) -> dict:
    profile_file = DATA_DIR / username / "profile.json"
    if profile_file.exists():
        with open(profile_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"username": username}

def list_media_in(folder: Path, content_type: str) -> list:
    """List all media files in a folder, newest first."""
    if not folder.exists():
        return []
    items = []
    for f in sorted(folder.iterdir(), reverse=True):
        if is_media(f):
            meta = load_json_sidecar(f)
            items.append({
                "filename": f.name,
                "url": relative_url(f),
                "type": content_type,
                "is_video": f.suffix.lower() == ".mp4",
                "timestamp": meta.get("timestamp"),
                "caption": meta.get("caption", ""),
                "likes": meta.get("likes"),
                "comments": meta.get("comments"),
                "shortcode": meta.get("shortcode"),
                "ig_url": meta.get("url"),
            })
    return items

# ── API Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("dashboard", "index.html")

@app.route("/api/competitors")
def get_competitors():
    """Return list of competitor usernames that have data."""
    if not DATA_DIR.exists():
        return jsonify([])
    competitors = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir():
            profile = read_profile(d.name)
            profile["has_stories"] = any(is_media(f) for f in (d / "stories").glob("*")) if (d / "stories").exists() else False
            profile["has_posts"] = any(is_media(f) for f in (d / "posts").glob("*")) if (d / "posts").exists() else False
            profile["has_reels"] = any(is_media(f) for f in (d / "reels").glob("*")) if (d / "reels").exists() else False
            competitors.append(profile)
    return jsonify(competitors)

@app.route("/api/content/<username>")
def get_content(username: str):
    """Return all downloaded content for a competitor, grouped by type."""
    user_dir = DATA_DIR / username
    if not user_dir.exists():
        abort(404, description=f"No data found for @{username}")

    return jsonify({
        "username": username,
        "profile": read_profile(username),
        "stories": list_media_in(user_dir / "stories", "story"),
        "posts": list_media_in(user_dir / "posts", "post"),
        "reels": list_media_in(user_dir / "reels", "reel"),
    })

@app.route("/api/content")
def get_all_content():
    """Return content for all competitors."""
    if not DATA_DIR.exists():
        return jsonify([])
    result = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir():
            result.append({
                "username": d.name,
                "profile": read_profile(d.name),
                "stories": list_media_in(d / "stories", "story"),
                "posts": list_media_in(d / "posts", "post"),
                "reels": list_media_in(d / "reels", "reel"),
            })
    return jsonify(result)

@app.route("/api/stats")
def get_stats():
    """Return quick stats for the dashboard header."""
    if not DATA_DIR.exists():
        return jsonify({"competitors": 0, "stories": 0, "posts": 0, "reels": 0})

    competitors = 0
    stories = posts = reels = 0
    for d in DATA_DIR.iterdir():
        if d.is_dir():
            competitors += 1
            stories += sum(1 for f in (d / "stories").glob("*") if is_media(f)) if (d / "stories").exists() else 0
            posts += sum(1 for f in (d / "posts").glob("*") if is_media(f)) if (d / "posts").exists() else 0
            reels += sum(1 for f in (d / "reels").glob("*") if is_media(f)) if (d / "reels").exists() else 0

    return jsonify({"competitors": competitors, "stories": stories, "posts": posts, "reels": reels})

# ── Media serving ───────────────────────────────────────────────────────────────
@app.route("/media/<path:filepath>")
def serve_media(filepath: str):
    """Serve downloaded media files."""
    full_path = DATA_DIR / filepath
    if not full_path.exists():
        abort(404)
    mime = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
    return send_from_directory(DATA_DIR, filepath, mimetype=mime)

# ── Run ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🎯 Nour Competitor Monitor — Dashboard")
    print("=" * 55)
    print("  Open your browser at:  http://localhost:5000")
    print("  Press Ctrl+C to stop.")
    print("=" * 55 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
