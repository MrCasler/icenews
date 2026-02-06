"""
Content download utilities for social media posts.
Supports X/Twitter, YouTube, TikTok with yt-dlp.
Fallback for Twitter image-only: fetch page og:image or accept direct image URLs.
"""
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None


def _is_direct_image_url(url: str) -> bool:
    """True if URL looks like a direct image (e.g. pbs.twimg.com/media, imgur, cdn)."""
    if not url:
        return False
    u = url.lower()
    return any(
        x in u
        for x in (
            "pbs.twimg.com/media",
            "twimg.com/media",
            "/media/",
            "i.imgur.com",
            "imgur.com/",
            "cdn.",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
        )
    ) and ("twitter.com" in u or "x.com" in u or "imgur" in u or "twimg" in u or "cdn" in u or u.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")))


def _download_direct_image(url: str, output_dir: Path) -> tuple[bool, str, Optional[Path]]:
    """Download a direct image URL with requests. Returns (success, message, path)."""
    if not requests:
        return False, "requests not installed", None
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; ICENews/1.0)"})
        r.raise_for_status()
        if len(r.content) > 20 * 1024 * 1024:
            return False, "Image too large", None
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix or ".jpg"
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        out = output_dir / f"image{ext}"
        out.write_bytes(r.content)
        return True, "Image downloaded", out
    except Exception as e:
        return False, str(e)[:150], None


def _fetch_twitter_og_image(tweet_url: str) -> Optional[str]:
    """Fetch tweet page and return og:image or twitter:image URL if found."""
    if not requests:
        return None
    try:
        r = requests.get(
            tweet_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
        r.raise_for_status()
        html = r.text
        # og:image
        m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if m:
            return m.group(1).strip()
        m = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']', html, re.I)
        if m:
            return m.group(1).strip()
        # twitter:image
        m = re.search(r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        if m:
            return m.group(1).strip()
        m = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']twitter:image["\']', html, re.I)
        if m:
            return m.group(1).strip()
        # Fallback: any pbs.twimg.com/media URL in the page (images embedded in tweet)
        m = re.search(r'https?://pbs\.twimg\.com/media/[A-Za-z0-9_-]+(?:\?[^"\'\s]*)?', html)
        if m:
            return m.group(0).split("?")[0] + "?format=jpg&name=large"
    except Exception:
        pass
    return None


def download_x_content(url: str, output_dir: Optional[Path] = None) -> tuple[bool, str, Optional[Path]]:
    """
    Download media from a social media post URL (X/Twitter, YouTube, TikTok).
    
    Args:
        url: Post URL from supported platform
        output_dir: Directory to save downloads (uses temp dir if None)
    
    Returns:
        Tuple of (success: bool, message: str, file_path: Optional[Path])
    """
    if not url:
        return False, "No URL provided", None

    url_lower = url.lower().strip()
    is_twitter = "twitter.com" in url_lower or "x.com" in url_lower

    # Use temp directory if no output dir specified
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp())
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Direct image URL: download with requests (e.g. pbs.twimg.com/media/..., imgur)
    if _is_direct_image_url(url):
        ok, msg, path = _download_direct_image(url, output_dir)
        if ok:
            return True, msg, path
        return False, f"Direct image download failed: {msg}", None

    # Configure yt-dlp command for best compatibility
    output_template = str(output_dir / '%(uploader)s_%(id)s.%(ext)s')
    
    # Don't use -f best: for image-only tweets yt-dlp fails with "No video could be found".
    # Try with -f "all" first so image-only tweets can still yield thumbnails/images if the extractor provides them.
    cmd = [
        'yt-dlp',
        '--no-check-certificate',
        '--no-warnings',  # avoid surfacing WARNING (e.g. WSJ impersonation) as user-facing error
        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        '--write-thumbnail',
        '--convert-thumbnails', 'jpg',
        '--no-playlist',
        '--ignore-errors',  # don't abort so we can still get any written files
        '-f', 'all',
        '-o', output_template,
        url
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout for larger files
        )
        
        # Find the downloaded file(s) (ignore-errors may leave us with partial success)
        downloaded_files = list(output_dir.glob('*'))
        
        if not downloaded_files:
            error_msg = (result.stderr or result.stdout or "")
            if is_twitter and ("No video could be found" in error_msg or "no video" in error_msg.lower()):
                # Fallback: try to get og:image / twitter:image from the tweet page
                og_url = _fetch_twitter_og_image(url)
                if og_url:
                    ok, msg, path = _download_direct_image(og_url, output_dir)
                    if ok:
                        return True, "Image downloaded (from tweet preview)", path
                return False, "This post has images only; the downloader could not extract them. Try a post with video or paste a direct image link (right‑click image → Copy image address).", None
            # Don't surface yt-dlp WARNING (e.g. WSJ impersonation) as the main error
            if "WARNING" in error_msg or "impersonation" in error_msg.lower():
                return False, "Unsupported URL or content. Try X, YouTube, TikTok, or Instagram.", None
            return False, f"Download failed: {error_msg[:200]}" if error_msg else "Download failed", None
        
        # Prioritize video/media files over small thumbnails
        media_files = []
        thumbnail_files = []
        
        for file in downloaded_files:
            try:
                size = file.stat().st_size
            except OSError:
                continue
            if file.suffix.lower() in ['.jpg', '.jpeg', '.webp', '.png', '.gif'] and size < 200000:
                thumbnail_files.append(file)
            else:
                media_files.append(file)
        
        # Prefer largest media file; otherwise use any image/thumbnail
        if media_files:
            media_files.sort(key=lambda f: f.stat().st_size, reverse=True)
            return True, "Download successful", media_files[0]
        if thumbnail_files:
            thumbnail_files.sort(key=lambda f: f.stat().st_size, reverse=True)
            return True, "Image downloaded", thumbnail_files[0]
        # Fallback: any file
        downloaded_files.sort(key=lambda f: f.stat().st_size if f.exists() else 0, reverse=True)
        return True, "Content downloaded", downloaded_files[0]
        
    except subprocess.TimeoutExpired:
        return False, "Download timeout (2 minutes) - file may be too large", None
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        if "No video could be found" in error_msg or "no video" in error_msg.lower():
            return False, "This post has no downloadable video (images-only tweets may not be supported).", None
        if "Unsupported URL" in error_msg or "Unsupported platform" in error_msg:
            return False, "Platform not supported or URL is private", None
        if "Video unavailable" in error_msg or "This video is unavailable" in error_msg:
            return False, "Video unavailable or private", None
        if "Sign in" in error_msg or "login" in error_msg.lower():
            return False, "Content requires authentication (private account)", None
        return False, f"Download failed: {error_msg[:200]}", None
    except FileNotFoundError:
        return False, "yt-dlp not installed on server", None
    except Exception as e:
        return False, f"Unexpected error: {str(e)}", None


def check_yt_dlp_available() -> bool:
    """Check if yt-dlp is installed and available."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
