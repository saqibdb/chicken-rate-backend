from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.urls import reverse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Device, Price
from .configuration import get_runtime_setting
from .daily_price import run_daily_price_fetch
from .youtube import YouTubeImportError, fetch_youtube_prices


API_DESCRIPTIONS = {
    "test-check": {"methods": "GET", "description": "Check whether the API is running.", "parameters": "None"},
    "current-price": {"methods": "GET", "description": "Return the newest saved chicken price and its source video.", "parameters": "None"},
    "price-history": {"methods": "GET", "description": "Return prices from the past 30 days by default.", "parameters": "from and to: optional date bounds in YYYY-MM-DD format. limit: maximum results, 1–365 (default 365)."},
    "fetch-youtube-prices": {"methods": "GET", "description": "Fetch recent channel uploads, download thumbnails, run OCR, parse prices, and save matching rows. Response includes a per-step log.", "parameters": "None"},
    "fetch-todays-price": {"methods": "GET", "description": "Fetch and OCR only today's uploads. Adds today's price only if no price row exists for today; records each call in Django Admin.", "parameters": "None"},
}


@require_GET
def api_docs(request):
    from .urls import urlpatterns

    endpoints = []
    for pattern in urlpatterns:
        if not pattern.name or pattern.name == "api-docs":
            continue
        info = API_DESCRIPTIONS.get(pattern.name, {})
        endpoints.append({
            "path": reverse(pattern.name),
            "methods": info.get("methods", "See endpoint"),
            "description": info.get("description", ""),
            "parameters": info.get("parameters", "None"),
        })
    return render(request, "api/api_docs.html", {"endpoints": endpoints})


def _record_device(request):
    """Update device activity from mobile-app headers on every API call."""
    device_id = request.headers.get("X-Device-ID", "").strip()
    if not device_id:
        return

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",", 1)[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")
    defaults = {
        "device_name": request.headers.get("X-Device-Name", "")[:200],
        "platform": request.headers.get("X-Platform", "")[:64],
        "app_version": request.headers.get("X-App-Version", "")[:64],
        "os_version": request.headers.get("X-OS-Version", "")[:64],
        "last_ip_address": ip_address or None,
    }
    Device.objects.update_or_create(device_id=device_id[:128], defaults=defaults)


def _price_payload(price):
    return {
        "date": price.price_date.isoformat(),
        "amount": str(price.amount),
        "currency": price.currency,
        "video": {
            "id": price.video_id,
            "title": price.video_title,
            "url": price.video_url,
            "published_at": price.published_at.isoformat() if price.published_at else None,
        },
    }


@require_GET
def test(request):
    return JsonResponse({"status": "ok", "message": "Django API is running"})


@api_view(["GET"])
def current_price(request):
    _record_device(request)
    price = Price.objects.first()
    if price is None:
        return Response({"data": None, "message": "No price data is available yet."}, status=404)
    return Response({"data": _price_payload(price)})


@api_view(["GET"])
def price_history(request):
    _record_device(request)
    today = timezone.localdate()
    queryset = Price.objects.filter(price_date__gte=today - timedelta(days=29), price_date__lte=today)
    start_date = request.query_params.get("from")
    end_date = request.query_params.get("to")
    try:
        if start_date:
            queryset = queryset.filter(price_date__gte=date.fromisoformat(start_date))
        if end_date:
            queryset = queryset.filter(price_date__lte=date.fromisoformat(end_date))
    except ValueError:
        return Response({"detail": "Dates must use YYYY-MM-DD format."}, status=400)

    try:
        limit = min(max(int(request.query_params.get("limit", 365)), 1), 365)
    except ValueError:
        return Response({"detail": "limit must be an integer from 1 to 365."}, status=400)

    items = [_price_payload(price) for price in queryset[:limit]]
    return Response({"count": len(items), "results": items})


@api_view(["GET"])
def fetch_prices(request):
    _record_device(request)
    cooldown_value = get_runtime_setting(
        "YOUTUBE_FETCH_COOLDOWN_SECONDS", str(settings.YOUTUBE_FETCH_COOLDOWN_SECONDS)
    )
    try:
        cooldown = max(int(cooldown_value), 0)
    except ValueError:
        cooldown = settings.YOUTUBE_FETCH_COOLDOWN_SECONDS
    if cache.get("youtube-prices-fetched"):
        return Response({"status": "throttled", "message": "Prices were fetched recently; try again later."}, status=429)
    if not cache.add("youtube-prices-fetch-lock", True, timeout=600):
        return Response({"status": "in_progress", "message": "A price fetch is already running."}, status=429)
    try:
        result = fetch_youtube_prices()
    except YouTubeImportError as exc:
        cache.set("youtube-prices-fetched", True, timeout=min(cooldown, 60))
        return Response({"status": "error", "message": str(exc), "logs": exc.logs}, status=502)
    else:
        cache.set("youtube-prices-fetched", True, timeout=cooldown)
    finally:
        cache.delete("youtube-prices-fetch-lock")
    result["message"] = "YouTube thumbnail OCR import finished."
    return Response(result)


@api_view(["GET"])
def fetch_todays_price(request):
    _record_device(request)
    call_log, result = run_daily_price_fetch("api")
    return Response({
        "status": call_log.result,
        "fetch_status": result.get("status"),
        "message": "Today's price fetch finished.",
        "call_id": call_log.pk,
        "called_at": call_log.called_at.isoformat(),
        "error": call_log.error or None,
        "added": result.get("added", 0),
        "amount": result.get("amount"),
        "videos_checked": result.get("videos_checked", 0),
        "logs": result.get("logs", []),
    })
