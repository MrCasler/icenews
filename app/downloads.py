"""
Content download utilities for X/Twitter posts.
Based on yt-dlp functionality from smol_skripts.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def download_x_content(url: str, output_dir: Optional[Path] = None) -> tuple[bool, str, Optional[Path]]:
    """
    Download media from an X/Twitter post URL.
    
    Args:
        url: X/Twitter post URL
        output_dir: Directory to save downloads (uses temp dir if None)
    
    Returns:
        Tuple of (success: bool, message: str, file_path: Optional[Path])
    """
    if not url or not any(domain in url.lower() for domain in ['twitter.com', 'x.com']):
        return False, "Invalid X/Twitter URL", None
    
    # Use temp directory if no output dir specified
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp())
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure yt-dlp command for X/Twitter
    output_template = str(output_dir / '%(uploader)s_%(id)s.%(ext)s')
    
    cmd = [
        'yt-dlp',
        '--no-check-certificate',  # Bypass SSL issues
        '--user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        '--write-thumbnail',
        '-o', output_template,
        url
    ]
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        # Find the downloaded file(s)
        downloaded_files = list(output_dir.glob('*'))
        
        if not downloaded_files:
            return False, "Download completed but no files found", None
        
        # Return the first media file (not thumbnail)
        for file in downloaded_files:
            if not file.name.endswith('.jpg') or file.stat().st_size > 100000:
                return True, "Download successful", file
        
        # If only thumbnails, return the first one
        return True, "Only thumbnail available", downloaded_files[0]
        
    except subprocess.TimeoutExpired:
        return False, "Download timeout (60s)", None
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return False, f"Download failed: {error_msg}", None
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
