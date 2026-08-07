"""
scrape.py — Competitor Instagram monitor for Nour
---------------------------------------------------
Authenticates using Firefox cookies (most reliable method in 2026).
Downloads stories, posts, and reels from competitor accounts.

Now uses instagrapi (Mobile API) to bypass Instagram's aggressive web blocks (429/400).
"""

import json
import os
import time
import random
import sys
import logging
from datetime import datetime
from pathlib import Path

# Use instagrapi instead of instaloader to avoid Web API bans
from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nour-scraper")

# ── Load config ────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "config.json"

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        log.error("config.json not found. Please create it from the template.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Auth helpers ────────────────────────────────────────────────────────────────
SESSION_DIR = Path(__file__).parent / ".sessions"
SESSION_DIR.mkdir(exist_ok=True)

def get_session_file(username: str) -> Path:
    return SESSION_DIR / f"instagrapi-{username}.json"

def authenticate(cl: Client, username: str) -> bool:
    """
    Load saved instagrapi session or extract sessionid from Firefox.
    """
    session_file = get_session_file(username)

    if session_file.exists():
        try:
            cl.load_settings(session_file)
            cl.login_by_sessionid(cl.settings.get("authorization_data", {}).get("sessionid"))
            log.info(f"✓ Loaded saved mobile session for @{username}")
            return True
        except Exception as e:
            log.warning(f"Could not load saved session: {e}. Re-authenticating...")

    log.info("Importing cookies from Firefox (make sure you're logged into Instagram in Firefox)...")
    try:
        import browser_cookie3
        cookies = browser_cookie3.firefox(domain_name=".instagram.com")
        
        sessionid = None
        for cookie in cookies:
            if cookie.name == "sessionid":
                sessionid = cookie.value
                break
        
        if not sessionid:
            log.error("No 'sessionid' cookie found in Firefox.")
            return False

        log.info("Verifying mobile session using extracted sessionid...")
        cl.login_by_sessionid(sessionid)
        
        # Verify it works
        me = cl.account_info()
        log.info(f"✓ Authenticated successfully via Mobile API as @{me.username}")
        
        cl.dump_settings(session_file)
        log.info(f"  Session saved to {session_file}")
        return True

    except ImportError:
        log.error("browser_cookie3 is not installed. Run: pip install browser-cookie3")
        return False
    except ClientError as e:
        log.error(f"Mobile API login rejected: {e}")
        return False
    except Exception as e:
        log.error(f"Failed to authenticate: {e}")
        return False

# ── Metadata helper ─────────────────────────────────────────────────────────────
def save_metadata(folder: Path, filename_stem: str, data: dict):
    """Save a JSON sidecar file."""
    meta_path = folder / f"{filename_stem}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

# ── Scrapers ────────────────────────────────────────────────────────────────────
def polite_delay(delay_range: list):
    t = random.uniform(delay_range[0], delay_range[1])
    log.info(f"  Waiting {t:.1f}s before next request...")
    time.sleep(t)

def scrape_stories(cl: Client, user_id: str, username: str, out_dir: Path, delay_range: list):
    stories_dir = out_dir / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"  Fetching stories for @{username}...")
    try:
        stories = cl.user_stories(user_id)
        count = 0
        for story in stories:
            ts = story.taken_at.strftime("%Y%m%d_%H%M%S")
            kind = "video" if story.media_type == 2 else "image"
            stem = f"{ts}_{kind}_{story.pk}"
            
            existing = list(stories_dir.glob(f"{stem}.*"))
            if existing:
                log.info(f"    ↷ Story {stem} already downloaded, skipping")
                continue

            # Download using instagrapi
            if story.media_type == 2:
                downloaded_path = cl.story_download(story.pk, filename=stem, folder=stories_dir)
            else:
                downloaded_path = cl.story_download(story.pk, filename=stem, folder=stories_dir)

            save_metadata(stories_dir, stem, {
                "type": "story",
                "username": username,
                "timestamp": story.taken_at.isoformat(),
                "is_video": story.media_type == 2,
                "id": story.pk
            })
            count += 1
            polite_delay([2, 5])

        log.info(f"    ✓ {count} new stories downloaded for @{username}")
    except Exception as e:
        log.error(f"    Error fetching stories for @{username}: {e}")

def scrape_posts(cl: Client, user_id: str, username: str, out_dir: Path, max_posts: int, delay_range: list):
    posts_dir = out_dir / "posts"
    reels_dir = out_dir / "reels"
    posts_dir.mkdir(parents=True, exist_ok=True)
    reels_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"  Fetching up to {max_posts} recent posts for @{username}...")
    
    try:
        medias = cl.user_medias(user_id, amount=max_posts)
        count_posts = 0
        count_reels = 0
        
        for media in medias:
            ts = media.taken_at.strftime("%Y%m%d_%H%M%S")
            is_reel = media.product_type == "clips"
            target_dir = reels_dir if is_reel else posts_dir
            kind = "reel" if is_reel else ("video" if media.media_type == 2 else "image")
            
            # Using shortcode in the stem so dashboard logic works exactly the same
            stem = f"{ts}_{kind}_{media.code}"
            
            existing = list(target_dir.glob(f"*{media.code}*"))
            if existing:
                log.info(f"    ↷ Post {media.code} already exists, skipping")
                continue

            try:
                # Download logic
                if media.media_type == 1: # Photo
                    cl.photo_download(media.pk, folder=target_dir)
                elif media.media_type == 2: # Video/Reel
                    if is_reel:
                        cl.clip_download(media.pk, folder=target_dir)
                    else:
                        cl.video_download(media.pk, folder=target_dir)
                elif media.media_type == 8: # Carousel (download first item to keep it simple, or all)
                    cl.album_download(media.pk, folder=target_dir)

                # Instagrapi uses {username}_{pk}.jpg/mp4 as default filename when not specified.
                # We rename the downloaded files to match our expected format.
                downloaded_files = list(target_dir.glob(f"{username}_{media.pk}*"))
                for df in downloaded_files:
                    new_name = target_dir / f"{stem}{df.suffix}"
                    if not new_name.exists():
                        df.rename(new_name)
                    else:
                        df.unlink() # Cleanup if somehow duplicate

                save_metadata(target_dir, stem, {
                    "type": kind,
                    "username": username,
                    "shortcode": media.code,
                    "timestamp": media.taken_at.isoformat(),
                    "caption": media.caption_text if media.caption_text else "",
                    "likes": media.like_count,
                    "comments": media.comment_count,
                    "views": getattr(media, 'view_count', 0) or getattr(media, 'play_count', 0) or None,
                    "is_video": media.media_type == 2 or is_reel,
                    "url": f"https://www.instagram.com/p/{media.code}/",
                })
                
                if is_reel: count_reels += 1
                else: count_posts += 1
                
                polite_delay([3, 7])

            except Exception as e:
                log.warning(f"    Could not download post {media.code}: {e}")

        log.info(f"    ✓ {count_posts} posts, {count_reels} reels downloaded for @{username}")
    except Exception as e:
        log.error(f"    Error fetching posts for @{username}: {e}")

# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    config = load_config()
    username = config["instagram_username"]
    competitors = config["competitors"]
    max_posts = config.get("max_posts", 20)
    delay_range = config.get("delay_range", [12, 28])

    auth_only = "--auth-only" in sys.argv

    log.info("=" * 60)
    log.info("  Nour Competitor Monitor — Instagrapi (Mobile API)")
    log.info("=" * 60)

    cl = Client()
    
    # Delay between requests built-in
    cl.delay_range = delay_range

    if not authenticate(cl, username):
        sys.exit(1)

    if auth_only:
        log.info("✓ Authentication successful. Run without --auth-only to start scraping.")
        return

    data_root = Path(__file__).parent / "data" / "instagram"

    for handle in competitors:
        log.info(f"\n{'─' * 50}")
        log.info(f"Processing competitor: @{handle}")
        log.info(f"{'─' * 50}")

        try:
            user_id = cl.user_id_from_username(handle)
            user_info = cl.user_info(user_id)
        except Exception as e:
            log.error(f"  Could not load profile @{handle}: {e}")
            continue

        out_dir = data_root / handle
        out_dir.mkdir(parents=True, exist_ok=True)

        # Save profile info
        profile_meta = {
            "username": user_info.username,
            "full_name": user_info.full_name,
            "biography": user_info.biography,
            "followers": user_info.follower_count,
            "followees": user_info.following_count,
            "posts": user_info.media_count,
            "is_private": user_info.is_private,
            "profile_pic_url": str(user_info.profile_pic_url),
            "last_scraped": datetime.utcnow().isoformat(),
        }
        with open(out_dir / "profile.json", "w", encoding="utf-8") as f:
            json.dump(profile_meta, f, indent=2, default=str)

        if user_info.is_private:
            log.warning(f"  @{handle} is private. Ensure the burner account follows them.")

        scrape_stories(cl, user_id, handle, out_dir, delay_range)
        polite_delay(delay_range)
        scrape_posts(cl, user_id, handle, out_dir, max_posts, delay_range)

    log.info(f"\n{'=' * 60}")
    log.info("  Scrape complete! Run `python server.py` to view the dashboard.")
    log.info(f"{'=' * 60}")

if __name__ == "__main__":
    main()
