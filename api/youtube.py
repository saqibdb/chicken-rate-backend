import json
import re
import shutil
import subprocess
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .configuration import get_runtime_setting
from .models import Price


PRICE_PATTERN = re.compile(r"(?<![0-9])([0-9]{1,3})\s*,\s*([0-9]{3})")
DEFAULT_CHANNEL_HANDLE = "Mianshahzadsaeed786"
MAX_THUMBNAIL_BYTES = 12 * 1024 * 1024


class YouTubeImportError(Exception):
    def __init__(self, message, logs=None):
        super().__init__(message)
        self.logs = logs or []


def _log(logs, step, status, message, **details):
    entry = {"step": step, "status": status, "message": message}
    entry.update(details)
    logs.append(entry)


def _youtube_get(path, params, api_key):
    query = urlencode({**params, "key": api_key})
    url = f"https://www.googleapis.com/youtube/v3/{path}?{query}"
    try:
        with urlopen(url, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = body.get("error", {}).get("message", str(exc))
        except Exception:
            detail = str(exc)
        raise YouTubeImportError(f"YouTube API request failed: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise YouTubeImportError(f"YouTube API request failed: {exc}") from exc


def _channel_uploads_playlist(api_key, channel_id, channel_handle):
    params = {"part": "contentDetails"}
    if channel_id:
        params["id"] = channel_id
    else:
        params["forHandle"] = f"@{channel_handle.lstrip('@')}"
    result = _youtube_get("channels", params, api_key)
    channels = result.get("items", [])
    if not channels:
        raise YouTubeImportError("YouTube channel could not be found.")
    return channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _recent_first_uploads(api_key, uploads_playlist, logs, max_results):
    today = timezone.localdate()
    cutoff = today - timedelta(days=29)
    videos_by_day = {}
    page_token = None

    page_count = min((max_results + 49) // 50, 4)
    for page_number in range(1, page_count + 1):
        params = {"part": "snippet", "playlistId": uploads_playlist, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        page = _youtube_get("playlistItems", params, api_key)
        items = page.get("items", [])
        _log(logs, "list_uploads", "ok", "Loaded upload page.", page=page_number, items=len(items))
        older_than_window = False
        remaining = max_results - (page_number - 1) * 50
        for item in items[:remaining]:
            snippet = item.get("snippet", {})
            published_at = parse_datetime(snippet.get("publishedAt", ""))
            if published_at is None:
                _log(logs, "read_upload", "skipped", "Upload has no valid publication timestamp.")
                continue
            if timezone.is_naive(published_at):
                published_at = timezone.make_aware(published_at, timezone.get_current_timezone())
            local_published = timezone.localtime(published_at)
            price_date = local_published.date()
            if price_date < cutoff:
                older_than_window = True
                continue

            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id:
                _log(logs, "read_upload", "skipped", "Upload has no video ID.")
                continue
            thumbnails = snippet.get("thumbnails", {})
            thumbnail = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default")
            thumbnail_url = thumbnail.get("url") if thumbnail else None
            video = {
                "video_id": video_id,
                "title": snippet.get("title", "YouTube Short")[:500],
                "published_at": local_published,
                "price_date": price_date,
                "thumbnail_url": thumbnail_url or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            }
            videos_by_day.setdefault(price_date, []).append(video)

        if older_than_window:
            _log(logs, "list_uploads", "ok", "Reached uploads older than the 30-day window.")
            break
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    first_uploads = []
    for price_date, videos in videos_by_day.items():
        videos.sort(key=lambda video: video["published_at"])
        first_uploads.append(videos[0])
    first_uploads.sort(key=lambda video: video["published_at"], reverse=True)
    _log(
        logs,
        "select_daily_videos",
        "ok",
        "Selected the first upload for each date in the last 30 days.",
        uploads_seen=sum(len(videos) for videos in videos_by_day.values()),
        videos_selected=len(first_uploads),
    )
    return first_uploads


def _download_thumbnail(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    trusted_host = host in {"ytimg.com", "youtube.com", "ggpht.com"} or host.endswith(
        (".ytimg.com", ".youtube.com", ".ggpht.com")
    )
    if parsed.scheme != "https" or not trusted_host:
        raise ValueError("Thumbnail URL is not a trusted YouTube image URL.")
    request = Request(url, headers={"User-Agent": "ChickenRateBackend/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"Thumbnail download returned HTTP {response.status}.")
        image_bytes = response.read(MAX_THUMBNAIL_BYTES + 1)
    if not image_bytes:
        raise ValueError("Thumbnail response was empty.")
    if len(image_bytes) > MAX_THUMBNAIL_BYTES:
        raise ValueError("Thumbnail exceeded the 12 MB download limit.")
    return image_bytes


def _recognize_thumbnail(image_bytes):
    configured_cmd = get_runtime_setting("TESSERACT_CMD", "tesseract").strip() or "tesseract"
    executable = shutil.which(configured_cmd)
    if not executable:
        raise FileNotFoundError(
            "Tesseract OCR executable is not installed or TESSERACT_CMD is incorrect."
        )
    with tempfile.TemporaryDirectory(prefix="chicken-rate-ocr-") as temp_dir:
        image_path = Path(temp_dir) / "thumbnail"
        image_path.write_bytes(image_bytes)
        result = subprocess.run(
            [executable, str(image_path), "stdout", "--psm", "6", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
    if result.returncode != 0:
        error = result.stderr.strip() or f"Tesseract exited with code {result.returncode}."
        raise RuntimeError(error[:500])
    return result.stdout


def _price_from_ocr(text):
    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:2]
    first_two_lines = " ".join(first_lines)
    amounts = {
        int(f"{match.group(1)}{match.group(2)}")
        for match in PRICE_PATTERN.finditer(first_two_lines)
    }
    return (next(iter(amounts)), first_lines) if len(amounts) == 1 else (None, first_lines)


def fetch_youtube_prices(max_results=200):
    """Mirror the Flutter app's first-upload-per-day thumbnail OCR process."""
    logs = []
    api_key = get_runtime_setting("YOUTUBE_API_KEY")
    channel_id = get_runtime_setting("YOUTUBE_CHANNEL_ID")
    channel_handle = get_runtime_setting("YOUTUBE_CHANNEL_HANDLE", DEFAULT_CHANNEL_HANDLE)
    if not api_key:
        _log(logs, "configuration", "error", "YOUTUBE_API_KEY is not configured.")
        raise YouTubeImportError("YOUTUBE_API_KEY is not configured.", logs)
    if not channel_id and not channel_handle:
        _log(logs, "configuration", "error", "No YouTube channel ID or handle is configured.")
        raise YouTubeImportError("Set YOUTUBE_CHANNEL_ID or YOUTUBE_CHANNEL_HANDLE.", logs)
    if not 1 <= max_results <= 200:
        _log(logs, "configuration", "error", "max_results is outside the supported range.")
        raise YouTubeImportError("max_results must be between 1 and 200.", logs)

    _log(logs, "configuration", "ok", "YouTube API key and channel configuration are present.")
    try:
        uploads_playlist = _channel_uploads_playlist(api_key, channel_id, channel_handle)
        _log(logs, "resolve_channel", "ok", "Resolved channel uploads playlist.")
        videos = _recent_first_uploads(api_key, uploads_playlist, logs, max_results)
    except Exception as exc:
        if not isinstance(exc, YouTubeImportError):
            exc = YouTubeImportError(f"YouTube channel or uploads request failed: {exc}")
        _log(logs, "youtube_api", "error", str(exc))
        _log(logs, "complete", "error", "Import stopped before thumbnail processing.")
        raise YouTubeImportError(str(exc), logs) from exc

    counts = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}
    for video in videos:
        context = {"video_id": video["video_id"], "title": video["title"], "date": video["price_date"].isoformat()}
        _log(logs, "video_selected", "ok", "Selected this date's first upload.", **context)
        try:
            thumbnail_bytes = _download_thumbnail(video["thumbnail_url"])
            _log(logs, "download_thumbnail", "ok", "Downloaded video thumbnail.", bytes=len(thumbnail_bytes), **context)
        except Exception as exc:
            counts["errors"] += 1
            counts["skipped"] += 1
            _log(logs, "download_thumbnail", "error", str(exc), **context)
            continue

        try:
            ocr_text = _recognize_thumbnail(thumbnail_bytes)
            ocr_lines = [line.strip() for line in ocr_text.splitlines() if line.strip()][:2]
            _log(logs, "thumbnail_ocr", "ok" if ocr_lines else "warning", "OCR completed.", ocr_text=" | ".join(ocr_lines)[:300], **context)
        except FileNotFoundError as exc:
            _log(logs, "thumbnail_ocr", "error", str(exc), **context)
            _log(logs, "complete", "error", "Import stopped because OCR is unavailable.", **counts)
            raise YouTubeImportError(str(exc), logs) from exc
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as exc:
            counts["errors"] += 1
            counts["skipped"] += 1
            _log(logs, "thumbnail_ocr", "error", str(exc), **context)
            continue

        amount, first_lines = _price_from_ocr(ocr_text)
        if amount is None:
            counts["skipped"] += 1
            reason = "No comma-grouped amount was found in the first two OCR lines." if first_lines else "No readable text was found in the thumbnail."
            _log(logs, "parse_price", "skipped", reason, **context)
            continue
        _log(logs, "parse_price", "ok", "Found one unambiguous comma-grouped price.", amount=amount, **context)

        try:
            _, created = Price.objects.update_or_create(
                video_id=video["video_id"],
                defaults={
                    "price_date": video["price_date"],
                    "amount": Decimal(amount),
                    "currency": "PKR",
                    "video_title": video["title"],
                    "video_url": f"https://www.youtube.com/watch?v={video['video_id']}",
                    "published_at": video["published_at"],
                },
            )
        except Exception as exc:
            counts["errors"] += 1
            _log(logs, "save_price", "error", f"Database save failed: {exc}", amount=amount, **context)
            continue
        if created:
            counts["added"] += 1
            action = "added"
        else:
            counts["updated"] += 1
            action = "updated"
        _log(logs, "save_price", "ok", f"Price row {action}.", amount=amount, **context)

    status = "ok" if counts["added"] or counts["updated"] else "no_prices"
    if counts["errors"]:
        status = "partial" if counts["added"] or counts["updated"] else "error"
    _log(logs, "complete", status, "Thumbnail price import finished.", **counts)
    return {"status": status, "videos_checked": len(videos), **counts, "logs": logs}
