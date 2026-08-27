"""
Ingestion Service for CNBC Awaaz YouTube Broadcasts.
Uses embedded ffmpeg and yt-dlp to capture audio streams and transcripts.
"""

import os
import subprocess
import logging
import tempfile
import time
import re
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

DEFAULT_LIVE_URL = "https://www.youtube.com/@cnbcawaaz/live"


def get_ffmpeg_path() -> str:
    """Retrieves path to ffmpeg executable on Linux and Windows."""
    import shutil
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    local_exe = os.path.join(os.getcwd(), "ffmpeg.exe")
    if os.path.exists(local_exe):
        return local_exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def extract_video_id(url: str) -> Optional[str]:
    """Extracts YouTube video ID from various URL formats."""
    match = re.search(r"(?:v=|\/live\/|\/watch\?v=|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


class YouTubeFetcher:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(os.getcwd(), "downloads")
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_path = get_ffmpeg_path()
        if self.ffmpeg_path:
            logger.debug(f"Using ffmpeg at: {self.ffmpeg_path}")

    def fetch_transcript(self, video_url: str) -> Optional[str]:
        """
        Attempts to fetch closed-captions / automated Hindi/English transcripts.
        Returns text transcript with segment timestamps if available.
        """
        video_id = extract_video_id(video_url)
        if not video_id:
            logger.debug(f"Could not extract video ID from {video_url}")
            return None

        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            logger.info(f"Attempting to fetch transcript for video ID: {video_id}...")
            
            items = None
            try:
                items = YouTubeTranscriptApi.get_transcript(video_id, languages=['hi', 'en', 'hi-IN'])
            except Exception:
                try:
                    items = YouTubeTranscriptApi.get_transcript(video_id)
                except Exception as ex:
                    logger.debug(f"Transcript fallback: {ex}")

            if items:
                text_lines = []
                for item in items:
                    start_sec = int(item.get('start', 0))
                    mins = start_sec // 60
                    secs = start_sec % 60
                    text = item.get('text', '').strip()
                    text_lines.append(f"[{mins:02d}:{secs:02d}] {text}")
                
                full_text = "\n".join(text_lines)
                logger.info(f"Successfully retrieved transcript ({len(text_lines)} cues).")
                return full_text
        except Exception as e:
            logger.info(f"Transcript not available for {video_id}: {e}.")

        return None

    def download_video_audio(
        self,
        video_url: str,
        output_prefix: str = "video_audio",
        duration_minutes: int = 30
    ) -> str:
        """
        Downloads audio stream from a YouTube video using yt-dlp + embedded ffmpeg.
        """
        timestamp = int(time.time())
        output_template = os.path.join(self.output_dir, f"{output_prefix}_{timestamp}.%(ext)s")

        logger.info(f"Downloading direct audio segment ({duration_minutes} mins) from video: {video_url}")
        ffmpeg_exe = get_ffmpeg_path()
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--extractor-args", "youtube:player_client=android,web",
            "-f", "ba[ext=m4a]/ba/b",
            "--downloader", "ffmpeg",
            "--downloader-args", f"ffmpeg_i:-t {duration_minutes * 60}",
            "-o", output_template,
            video_url
        ]
        if ffmpeg_exe and os.path.dirname(ffmpeg_exe):
            cmd.insert(6, os.path.dirname(ffmpeg_exe))
            cmd.insert(6, "--ffmpeg-location")

        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            logger.warning(f"Download timed out for {video_url}, attempting to recover partial chunk...")
        
        # Look for the generated mp3/m4a/mp4 file (including .part recovery)
        for fname in os.listdir(self.output_dir):
            if fname.startswith(f"{output_prefix}_{timestamp}"):
                full_p = os.path.join(self.output_dir, fname)
                if fname.endswith(".part") and os.path.getsize(full_p) > 300 * 1024:
                    final_p = full_p[:-5]
                    if os.path.exists(final_p):
                        os.remove(final_p)
                    os.rename(full_p, final_p)
                    logger.info(f"Recovered and finalized audio chunk: {final_p} (Size: {os.path.getsize(final_p)} bytes)")
                    return final_p
                elif not fname.endswith(".part") and os.path.getsize(full_p) > 300 * 1024:
                    return full_p

        raise FileNotFoundError(f"Could not locate downloaded audio in {self.output_dir}")

    def fetch_live_trailing_audio(
        self,
        live_url: str = DEFAULT_LIVE_URL,
        duration_minutes: int = 25,
        output_prefix: str = "live_chunk"
    ) -> str:
        """
        Captures the trailing N minutes of audio buffer from a live YouTube stream.
        """
        duration_seconds = int(duration_minutes * 60)
        timestamp = int(time.time())
        output_filename = f"{output_prefix}_{timestamp}.mp3"
        output_path = os.path.join(self.output_dir, output_filename)

        logger.info(
            f"Capturing trailing {duration_minutes} mins ({duration_seconds}s) from {live_url}..."
        )

        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--extractor-args", "youtube:player_client=android,web",
            "--live-from-start=false",
            "--downloader", "ffmpeg",
            "--downloader-args", f"ffmpeg_i:-t {duration_seconds}",
            "-f", "ba/b",
            "-x",
            "--audio-format", "mp3",
            "-o", output_path,
            live_url
        ]

        if self.ffmpeg_path:
            cmd.extend(["--ffmpeg-location", os.path.dirname(self.ffmpeg_path)])

        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=duration_seconds + 120)

        if not os.path.exists(output_path):
            raise RuntimeError(f"Failed to capture live audio buffer from {live_url}.")

        logger.info(f"Audio chunk saved to: {output_path} (Size: {os.path.getsize(output_path)} bytes)")
        return output_path

    def cleanup(self, file_path: str):
        """Removes temporary audio chunk file."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up temporary audio: {file_path}")
        except Exception as e:
            logger.warning(f"Could not remove temporary file {file_path}: {e}")
