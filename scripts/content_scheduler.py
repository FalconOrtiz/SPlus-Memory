#!/usr/bin/env python3
"""
Content Strategy Automation

Manages X (Twitter) and YouTube posting schedules.
Reads templates, generates content variations, queues posts.

Supports:
  • X: 20 posts/day across 5 time windows
  • YouTube: 3 videos/day at 7am, 11am, 3pm Madrid time
  • Template-based content generation
  • Browser automation (Selenium) for posting
"""

import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import re

DB_PATH = Path.home() / ".hermes/memory-engine/db/memory.db"
CONTENT_DIR = Path.home() / "Desktop"

# X posting windows (Madrid time)
X_WINDOWS = {
    "A": {"time": "08:00", "duration": 60, "posts": 4, "zone": "US West + LATAM"},
    "B": {"time": "11:00", "duration": 60, "posts": 4, "zone": "US East morning"},
    "C": {"time": "14:00", "duration": 60, "posts": 4, "zone": "LATAM afternoon"},
    "D": {"time": "18:00", "duration": 60, "posts": 4, "zone": "US East evening"},
    "E": {"time": "21:00", "duration": 60, "posts": 4, "zone": "LATAM evening"},
}

# YouTube posting windows (Madrid time)
YOUTUBE_WINDOWS = [
    {"time": "07:00", "title_suffix": "Morning Deep Dive"},
    {"time": "11:00", "title_suffix": "Midday Tutorial"},
    {"time": "15:00", "title_suffix": "Afternoon Build"},
]


@dataclass
class ContentPost:
    """A queued content post."""
    
    post_id: str
    platform: str  # "x" or "youtube"
    window_id: str
    scheduled_time: str
    content: str
    title: Optional[str] = None
    status: str = "queued"  # queued, posted, failed
    created_at: str = ""
    posted_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class ContentScheduler:
    """Manage content scheduling and automation."""

    def __init__(self, db_path: Path = None, content_dir: Path = None):
        self.db_path = db_path or DB_PATH
        self.content_dir = content_dir or CONTENT_DIR
        self.conn = None
        self.templates = {}
        self._load_templates()

    def connect(self):
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def _load_templates(self):
        """Load X and YouTube templates from Desktop files."""
        x_file = self.content_dir / "X_TEMPLATES_AND_AUTOMATION_20POSTS_DAILY.md"
        yt_file = self.content_dir / "YOUTUBE_SCRIPTS_MONDAY_3VIDEOS_LAUNCH.md"

        if x_file.exists():
            with open(x_file) as f:
                self.templates["x"] = f.read()
        else:
            self.templates["x"] = ""

        if yt_file.exists():
            with open(yt_file) as f:
                self.templates["youtube"] = f.read()
        else:
            self.templates["youtube"] = ""

    def extract_templates(self, platform: str) -> Dict[str, List[str]]:
        """
        Extract template categories from markdown.
        
        Returns:
            Dict mapping category → list of templates
        """
        template_text = self.templates.get(platform, "")
        if not template_text:
            return {}

        categories = {}

        # Extract markdown headers and content
        lines = template_text.split("\n")
        current_category = None

        for i, line in enumerate(lines):
            if line.startswith("###"):
                # New category
                current_category = line.replace("###", "").strip()
                categories[current_category] = []
            elif line.startswith("**Template") and current_category:
                # Extract template block (until next template or category)
                template_block = []
                j = i
                while j < len(lines) and not (
                    lines[j].startswith("**Template") and j > i
                ):
                    template_block.append(lines[j])
                    j += 1

                template_text = "\n".join(template_block)
                if template_text.strip():
                    categories[current_category].append(template_text)

        return categories

    def queue_x_posts(self, daily_data: Dict = None) -> List[ContentPost]:
        """
        Queue X posts for all 5 windows.
        
        Args:
            daily_data: Dict with metrics for template substitution
        
        Returns:
            List of queued ContentPost objects
        """
        if daily_data is None:
            daily_data = {
                "revenue": "$10k MRR",
                "metric": "290 facts indexed",
                "employees": 0,
                "stack": "Claude + SQLite + Hermes",
            }

        posts = []
        categories = self.extract_templates("x")

        if not categories:
            print("⚠️  No X templates found")
            return posts

        category_list = list(categories.keys())
        template_list = [t for cat in categories.values() for t in cat]

        template_idx = 0
        window_counter = 0

        for window_id, window_data in X_WINDOWS.items():
            for post_num in range(window_data["posts"]):
                if template_idx >= len(template_list):
                    template_idx = 0

                template = template_list[template_idx]
                content = self._fill_template(template, daily_data)

                # Calculate scheduled time
                scheduled_time = self._calculate_window_time(window_id, post_num)

                post = ContentPost(
                    post_id=f"x_{window_id}_{post_num}",
                    platform="x",
                    window_id=window_id,
                    scheduled_time=scheduled_time,
                    content=content,
                    created_at=datetime.now().isoformat(),
                )

                posts.append(post)
                template_idx += 1
                window_counter += 1

        # Store in database
        for post in posts:
            self._store_post(post)

        return posts

    def queue_youtube_videos(self, daily_data: Dict = None) -> List[ContentPost]:
        """
        Queue YouTube videos for 3 windows.
        
        Args:
            daily_data: Dict with metrics for video titles
        
        Returns:
            List of queued ContentPost objects
        """
        if daily_data is None:
            daily_data = {
                "topic": "Building with Hermes Memory Engine",
                "focus": "Phase 8D Temporal Predictions",
            }

        posts = []
        categories = self.extract_templates("youtube")

        if not categories:
            print("⚠️  No YouTube templates found")
            return posts

        template_list = [t for cat in categories.values() for t in cat]

        for idx, window in enumerate(YOUTUBE_WINDOWS):
            if idx < len(template_list):
                template = template_list[idx]
            else:
                template = template_list[idx % len(template_list)]

            title = f"[{window['title_suffix']}] {daily_data.get('topic', 'Hermes Build')}"
            description = self._fill_template(template, daily_data)

            scheduled_time = self._calculate_youtube_time(window["time"])

            post = ContentPost(
                post_id=f"yt_{idx}",
                platform="youtube",
                window_id=f"yt_{window['time']}",
                scheduled_time=scheduled_time,
                title=title,
                content=description,
                created_at=datetime.now().isoformat(),
            )

            posts.append(post)
            self._store_post(post)

        return posts

    def _fill_template(self, template: str, data: Dict) -> str:
        """Replace template placeholders with data."""
        result = template

        for key, value in data.items():
            # Replace [KEY] with value
            result = result.replace(f"[{key.upper()}]", str(value))
            result = result.replace(f"[{key}]", str(value))

        return result

    def _calculate_window_time(self, window_id: str, post_num: int) -> str:
        """Calculate scheduled time for an X post."""
        window = X_WINDOWS[window_id]
        base_time = datetime.strptime(window["time"], "%H:%M").time()

        # Distribute posts evenly within the window
        interval = window["duration"] / max(window["posts"], 1)
        offset_minutes = int(post_num * interval)

        scheduled = datetime.combine(
            datetime.now().date(), base_time
        ) + timedelta(minutes=offset_minutes)

        return scheduled.isoformat()

    def _calculate_youtube_time(self, time_str: str) -> str:
        """Calculate scheduled time for YouTube video."""
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        scheduled = datetime.combine(datetime.now().date(), time_obj)
        return scheduled.isoformat()

    def _store_post(self, post: ContentPost):
        """Store post in database."""
        try:
            self.conn.execute(
                """
                INSERT INTO surface_buffer 
                  (fact_id, domain, trigger_type, injected_text, surfaced_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    post.post_id,
                    f"content_{post.platform}",
                    "scheduled_post",
                    json.dumps(asdict(post)),
                    post.scheduled_time,
                ),
            )
            self.conn.commit()
        except Exception as e:
            print(f"⚠️  Failed to store post: {e}")

    def get_queue_status(self) -> Dict:
        """Get status of queued content."""
        try:
            x_queued = self.conn.execute(
                """
                SELECT COUNT(*) as cnt FROM surface_buffer
                WHERE domain = 'content_x' AND trigger_type = 'scheduled_post'
                """
            ).fetchone()["cnt"]

            yt_queued = self.conn.execute(
                """
                SELECT COUNT(*) as cnt FROM surface_buffer
                WHERE domain = 'content_youtube' AND trigger_type = 'scheduled_post'
                """
            ).fetchone()["cnt"]

            return {
                "x_posts_queued": x_queued,
                "youtube_videos_queued": yt_queued,
                "total": x_queued + yt_queued,
            }
        except Exception:
            return {"x_posts_queued": 0, "youtube_videos_queued": 0, "total": 0}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Content Scheduler")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("queue-x", help="Queue today's X posts (20/day)")
    sub.add_parser("queue-youtube", help="Queue today's YouTube videos (3/day)")
    sub.add_parser("queue-all", help="Queue both X and YouTube")
    sub.add_parser("status", help="Content queue status")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    scheduler = ContentScheduler()
    scheduler.connect()

    try:
        if args.command == "queue-x":
            posts = scheduler.queue_x_posts()
            if args.json:
                print(json.dumps([p.to_dict() for p in posts], indent=2))
            else:
                print(f"\n  QUEUED {len(posts)} X POSTS")
                print(f"  {'═' * 50}\n")
                for p in posts[:5]:
                    print(f"  {p.post_id:15s} {p.scheduled_time[11:16]}")
                if len(posts) > 5:
                    print(f"  ... +{len(posts) - 5} more\n")

        elif args.command == "queue-youtube":
            posts = scheduler.queue_youtube_videos()
            if args.json:
                print(json.dumps([p.to_dict() for p in posts], indent=2))
            else:
                print(f"\n  QUEUED {len(posts)} YOUTUBE VIDEOS")
                print(f"  {'═' * 50}\n")
                for p in posts:
                    print(f"  {p.scheduled_time[11:16]}  {p.title}")
                print()

        elif args.command == "queue-all":
            x_posts = scheduler.queue_x_posts()
            yt_posts = scheduler.queue_youtube_videos()
            if args.json:
                print(json.dumps({
                    "x_posts": [p.to_dict() for p in x_posts],
                    "youtube_videos": [p.to_dict() for p in yt_posts],
                }, indent=2))
            else:
                print(f"\n  CONTENT QUEUED")
                print(f"  {'═' * 50}\n")
                print(f"  X posts:     {len(x_posts)} (20/day)")
                print(f"  YouTube:     {len(yt_posts)} (3/day)")
                print(f"  Total:       {len(x_posts) + len(yt_posts)}\n")

        elif args.command == "status":
            status = scheduler.get_queue_status()
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                print(f"\n  CONTENT QUEUE STATUS")
                print(f"  {'═' * 50}\n")
                print(f"  X posts:     {status['x_posts_queued']}")
                print(f"  YouTube:     {status['youtube_videos_queued']}")
                print(f"  Total:       {status['total']}\n")

        else:
            parser.print_help()

    finally:
        scheduler.close()


if __name__ == "__main__":
    main()
