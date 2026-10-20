import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import urlopen

from django.utils.dateparse import parse_datetime

from .configuration import get_runtime_setting
from .models import Price


PRICE_PATTERN = re.compile(
    r"(?:PKR|Rs\.?|Rupees?|روپے)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)


class YouTubeImportError(Exception):
    pass


def fetch_youtube_prices(max_results=50):
    """Fetch recent videos and upsert prices explicitly marked in metadata."""
    api_key = get_runtime_setting("YOUTUBE_API_KEY")
    channel_id = get_runtime_setting("YOUTUBE_CHANNEL_ID")
    if not api_key or not channel_id:
        raise YouTubeImportError("YouTube import is not configured on the server.")
    if not 1 <= max_results <= 50:
        raise YouTubeImportError("max_results must be between 1 and 50.")

    query = urlencode({
        "key": api_key,
        "channelId": channel_id,
        "part": "snippet",
        "type": "video",
        "order": "date",
        "maxResults": max_results,
    })
    url = f"https://www.googleapis.com/youtube/v3/search?{query}"
    try:
        with urlopen(url, timeout=20) as response:
            payload = json.load(response)
    except Exception as exc:
        raise YouTubeImportError(f"YouTube API request failed: {exc}") from exc

    added = updated = skipped = 0
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        title = snippet.get("title", "")[:500]
        match = PRICE_PATTERN.search(f"{title}\n{snippet.get('description', '')}")
        if not match:
            skipped += 1
            continue
        try:
            amount = Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:
            skipped += 1
            continue
        published_at = parse_datetime(snippet.get("publishedAt", ""))
        price_date = published_at.date() if published_at else date.today()
        _, created = Price.objects.update_or_create(
            video_id=video_id,
            defaults={
                "price_date": price_date,
                "amount": amount,
                "currency": "PKR",
                "video_title": title,
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published_at,
            },
        )
        if created:
            added += 1
        else:
            updated += 1

    return {"videos_checked": len(payload.get("items", [])), "added": added, "updated": updated, "skipped": skipped}
