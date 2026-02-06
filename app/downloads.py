"""
Content download utilities for social media posts.
Supports X/Twitter, YouTube, TikTok with yt-dlp (Python API; no CLI required).
Fallback for Twitter image-only: fetch page og:image or thumbnail from extractor.
"""
import re
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

try:
    import yt_dlp
    _YT_DLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    _YT_DLP_AVAILABLE = False


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
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
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

    if not _YT_DLP_AVAILABLE or yt_dlp is None:
        return False, "yt-dlp not installed on server", None

    output_template = str(output_dir / "%(uploader)s_%(id)s.%(ext)s")
    ydl_opts = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "format": "bestvideo+bestaudio/best/all",
        "merge_output_format": None,
        "http_headers": {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        "writethumbnail": True,
        "convertthumbnails": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        error_msg = str(e)
        if is_twitter and ("no video" in error_msg.lower() or "no video could be found" in error_msg.lower()):
            # Try thumbnail from extractor (no download)
            img_url = _twitter_image_from_extractor(url)
            if not img_url:
                img_url = _fetch_twitter_og_image(url)
            if img_url:
                ok, msg, path = _download_direct_image(img_url, output_dir)
                if ok:
                    return True, "Image downloaded (from tweet)", path
            return False, "This post has images only; the downloader could not extract them. Try a post with video or paste a direct image link (right‑click image → Copy image address).", None
        if "impersonation" in error_msg.lower() or "WARNING" in error_msg:
            return False, "Unsupported URL or content. Try X, YouTube, TikTok, or Instagram.", None
        return False, f"Download failed: {error_msg[:200]}", None

    downloaded_files = list(output_dir.glob("*"))
    if not downloaded_files:
        if is_twitter:
            img_url = _twitter_image_from_extractor(url) or _fetch_twitter_og_image(url)
            if img_url:
                ok, msg, path = _download_direct_image(img_url, output_dir)
                if ok:
                    return True, "Image downloaded (from tweet)", path
        return False, "Download failed: no file produced", None

    media_files = []
    thumbnail_files = []
    for file in downloaded_files:
        try:
            size = file.stat().st_size
        except OSError:
            continue
        if file.suffix.lower() in (".jpg", ".jpeg", ".webp", ".png", ".gif") and size < 200000:
            thumbnail_files.append(file)
        else:
            media_files.append(file)

    if media_files:
        media_files.sort(key=lambda f: f.stat().st_size, reverse=True)
        return True, "Download successful", media_files[0]
    if thumbnail_files:
        thumbnail_files.sort(key=lambda f: f.stat().st_size, reverse=True)
        return True, "Image downloaded", thumbnail_files[0]
    downloaded_files.sort(key=lambda f: f.stat().st_size if f.exists() else 0, reverse=True)
    return True, "Content downloaded", downloaded_files[0]


def _twitter_image_from_extractor(tweet_url: str) -> Optional[str]:
    """Use yt-dlp extract_info(download=False) to get thumbnail URL for image-only tweets."""
    if not _YT_DLP_AVAILABLE or yt_dlp is None:
        return None
    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "http_headers": {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(tweet_url, download=False)
        if not info:
            return None
        # Prefer thumbnail (often best quality for image-only)
        url = info.get("thumbnail")
        if not url and info.get("thumbnails"):
            url = info["thumbnails"][-1].get("url") if isinstance(info["thumbnails"][-1], dict) else None
        if url:
            return url
        # Some extractors put image in url when it's a single image
        if info.get("url") and _is_direct_image_url(info["url"]):
            return info["url"]
        return None
    except Exception:
        return None


def check_yt_dlp_available() -> bool:
    """Check if yt-dlp is available (Python package; no CLI required)."""
    return _YT_DLP_AVAILABLE
