"""
Search all recent CNBC Awaaz uploads and live streams for market recommendations.
"""
import subprocess
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

def main():
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", "20",
        "https://www.youtube.com/@cnbcawaaz/streams"
    ]
    print("Fetching last 20 streams from CNBC Awaaz...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    videos = []
    for line in result.stdout.splitlines():
        if line.strip():
            try:
                data = json.loads(line)
                vid_id = data.get("id")
                title = data.get("title", "")
                url = f"https://www.youtube.com/watch?v={vid_id}"
                videos.append((vid_id, title, url))
            except Exception:
                pass

    print(f"\nFound {len(videos)} videos:")
    for i, (vid_id, title, url) in enumerate(videos, 1):
        print(f"[{i}] {title}\n    URL: {url}\n")

if __name__ == "__main__":
    main()
