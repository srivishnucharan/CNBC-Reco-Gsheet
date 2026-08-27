import sys
import subprocess
import json

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def get_recent_cnbc_videos():
    print("Fetching recent CNBC Awaaz streams...", flush=True)
    cmd = ["yt-dlp", "--flat-playlist", "--playlist-items", "1:6", "-J", "https://www.youtube.com/@cnbcawaaz/streams"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 0 and res.stdout.strip():
        data = json.loads(res.stdout)
        entries = data.get('entries', [])
        print(f"Found {len(entries)} recent streams:", flush=True)
        for idx, e in enumerate(entries, 1):
            vid = e.get('id')
            title = e.get('title')
            print(f"[{idx}] {title} -> https://www.youtube.com/watch?v={vid}", flush=True)

if __name__ == "__main__":
    get_recent_cnbc_videos()
