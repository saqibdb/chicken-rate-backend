import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from api.models import Price


# Intentionally require a currency marker to avoid mistaking dates/views for prices.
PRICE_PATTERN = re.compile(
    r"(?:PKR|Rs\.?|Rupees?|روپے)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "Fetch recent videos from the configured YouTube channel and save parsed prices."

    def add_arguments(self, parser):
        parser.add_argument("--max-results", type=int, default=50)

    def handle(self, *args, **options):
        api_key = settings.YOUTUBE_API_KEY
        channel_id = settings.YOUTUBE_CHANNEL_ID
        if not api_key or not channel_id:
            raise CommandError("Set YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID in the server environment.")

        max_results = options["max_results"]
        if not 1 <= max_results <= 50:
            raise CommandError("--max-results must be between 1 and 50.")

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
            raise CommandError(f"YouTube API request failed: {exc}") from exc

        saved = skipped = 0
        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            title = snippet.get("title", "")[:500]
            description = snippet.get("description", "")
            match = PRICE_PATTERN.search(f"{title}\n{description}")
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
            saved += int(created)

        self.stdout.write(self.style.SUCCESS(f"Saved {saved} new prices; skipped {skipped} videos without a marked price."))
