from datetime import date, timedelta
import logging
import re
import threading

from django.conf import settings
from django.core.cache import cache
from django.core import signing
from django.db import close_old_connections
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import DailyPriceFetchLog, Device, FuelDevice, FuelPrice, OCRDiagnosticLog, Price
from .configuration import get_runtime_setting
from .daily_price import run_daily_price_fetch
from .ocr_diagnostics import run_ocr_diagnostic
from .youtube import YouTubeImportError, fetch_youtube_prices
from .fuel_prices import FuelPriceImportError, fetch_current_fuel_prices, fetch_fuel_price_history, serialize_fuel_price


API_DESCRIPTIONS = {
    "test-check": {"methods": "GET", "description": "Check whether the API is running.", "parameters": "None"},
    "current-price": {"methods": "GET", "description": "Return the newest saved chicken price and its source video.", "parameters": "None"},
    "price-history": {"methods": "GET", "description": "Return prices from the past 30 days by default.", "parameters": "from and to: optional date bounds in YYYY-MM-DD format. limit: maximum results, 1–365 (default 365)."},
    "fetch-youtube-prices": {"methods": "GET", "description": "Fetch recent channel uploads, download thumbnails, run OCR, parse prices, and save matching rows. Response includes a per-step log.", "parameters": "None"},
    "fetch-todays-price": {"methods": "GET", "description": "Start today's upload and OCR import in the background. Returns a call ID and status URL; adds a price only if no row exists for today.", "parameters": "None"},
    "fetch-todays-price-status": {"methods": "GET", "description": "Read the live progress, result, and step logs for a today's price fetch.", "parameters": "Path: call_id (required)."},
    "ocr-diagnostic": {"methods": "GET", "description": "Run a single-thumbnail OCR diagnostic without saving a price. Returns a diagnostic ID and status URL.", "parameters": "Query: video_id (required; 11-character YouTube video ID)."},
    "ocr-diagnostic-status": {"methods": "GET", "description": "Read live stages and result of a one-thumbnail OCR diagnostic.", "parameters": "Query: diagnostic_id and signature (from status_url)."},
    "register-push-device": {"methods": "POST", "description": "Register or refresh an Android device's Firebase push token.", "parameters": "JSON body: device_id (required), fcm_token (required), device_name, platform, app_version, os_version (optional)."},
    "fuel-current-prices": {"methods": "GET", "description": "Return the most recently saved combined petrol and diesel row.", "parameters": "None."},
    "fuel-price-history": {"methods": "GET", "description": "Return saved combined petrol and diesel prices by effective date.", "parameters": "limit: maximum results, 1–365 (default 30)."},
    "fuel-price-history-import": {"methods": "GET", "description": "Import daily provider history; call once per fuel to merge both fuels by date.", "parameters": "fuel: petrol or diesel (required). limit: 1–365 (default 30)."},
    "fuel-fetch-current": {"methods": "GET", "description": "Fetch and save the provider's latest petrol and diesel prices.", "parameters": "None."},
    "fuel-register-push-device": {"methods": "POST", "description": "Register a fuel app Firebase push token.", "parameters": "JSON body: device_id and fcm_token (required); device metadata optional."},
}


@require_GET
def api_docs(request):
    from .urls import urlpatterns

    endpoints = []
    for pattern in urlpatterns:
        if not pattern.name or pattern.name == "api-docs":
            continue
        info = API_DESCRIPTIONS.get(pattern.name, {})
        try:
            endpoint_path = reverse(pattern.name)
        except Exception:
            if pattern.name == "fetch-todays-price-status":
                endpoint_path = reverse(pattern.name, kwargs={"call_id": 1})
                endpoint_path = endpoint_path.rsplit("/1/", 1)[0] + "/{call_id}/"
            else:
                continue
        endpoints.append({
            "path": endpoint_path,
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
    call_log = DailyPriceFetchLog.objects.create(called_by="api")
    worker = threading.Thread(
        target=_run_daily_fetch_in_background,
        args=(call_log.pk,),
        name=f"today-price-fetch-{call_log.pk}",
        daemon=True,
    )
    worker.start()
    return Response({
        "status": "running",
        "message": "Today's price fetch was started. Poll status_url for progress and the result.",
        "call_id": call_log.pk,
        "called_at": call_log.called_at.isoformat(),
        "status_url": request.build_absolute_uri(
            reverse("fetch-todays-price-status", kwargs={"call_id": call_log.pk})
            + "?"
            + urlencode({"signature": signing.dumps(call_log.pk, salt="daily-price-fetch-status")})
        ),
    }, status=202)


def _run_daily_fetch_in_background(call_log_id):
    close_old_connections()
    try:
        call_log = DailyPriceFetchLog.objects.get(pk=call_log_id)
        run_daily_price_fetch("api", call_log=call_log)
    except Exception:
        logging.getLogger(__name__).exception("Background daily price fetch %s failed", call_log_id)
        DailyPriceFetchLog.objects.filter(pk=call_log_id).update(
            result="failure",
            error="The background price fetch failed. Check server logs for details.",
            completed_at=timezone.now(),
        )
    finally:
        close_old_connections()


@api_view(["GET"])
def fetch_todays_price_status(request, call_id):
    try:
        signed_call_id = signing.loads(
            request.query_params.get("signature", ""),
            salt="daily-price-fetch-status",
            max_age=60 * 60 * 24,
        )
    except signing.BadSignature:
        return Response({"detail": "A valid status_url signature is required."}, status=403)
    if signed_call_id != call_id:
        return Response({"detail": "Status URL does not match the requested call."}, status=403)
    _record_device(request)
    call_log = get_object_or_404(DailyPriceFetchLog, pk=call_id)
    details = call_log.details or {}
    return Response({
        "status": call_log.result,
        "fetch_status": details.get("status", call_log.result),
        "call_id": call_log.pk,
        "called_by": call_log.called_by,
        "called_at": call_log.called_at.isoformat(),
        "completed_at": call_log.completed_at.isoformat() if call_log.completed_at else None,
        "error": call_log.error or None,
        "added": details.get("added", 0),
        "amount": details.get("amount"),
        "videos_checked": details.get("videos_checked", 0),
        "logs": details.get("logs", []),
    })


@api_view(["GET"])
def start_ocr_diagnostic(request):
    _record_device(request)
    video_id = request.query_params.get("video_id", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return Response({"detail": "Provide an 11-character YouTube video_id."}, status=400)
    diagnostic = OCRDiagnosticLog.objects.create(video_id=video_id)
    worker = threading.Thread(
        target=run_ocr_diagnostic,
        args=(diagnostic.pk,),
        name=f"ocr-diagnostic-{diagnostic.pk}",
        daemon=True,
    )
    worker.start()
    signature = signing.dumps(diagnostic.pk, salt="ocr-diagnostic-status")
    status_url = request.build_absolute_uri(
        reverse("ocr-diagnostic-status") + "?" + urlencode({"diagnostic_id": diagnostic.pk, "signature": signature})
    )
    return Response({
        "status": "running",
        "message": "OCR diagnostic started; poll status_url for its stages and result.",
        "diagnostic_id": diagnostic.pk,
        "video_id": video_id,
        "status_url": status_url,
    }, status=202)


@api_view(["GET"])
def ocr_diagnostic_status(request):
    try:
        diagnostic_id = int(request.query_params.get("diagnostic_id", ""))
        signed_id = signing.loads(
            request.query_params.get("signature", ""),
            salt="ocr-diagnostic-status",
            max_age=60 * 60 * 24,
        )
    except (ValueError, signing.BadSignature):
        return Response({"detail": "A valid diagnostic status_url is required."}, status=403)
    if signed_id != diagnostic_id:
        return Response({"detail": "Status URL does not match the diagnostic."}, status=403)
    diagnostic = get_object_or_404(OCRDiagnosticLog, pk=diagnostic_id)
    details = diagnostic.details or {}
    return Response({
        "status": diagnostic.status,
        "diagnostic_id": diagnostic.pk,
        "video_id": diagnostic.video_id,
        "created_at": diagnostic.created_at.isoformat(),
        "completed_at": diagnostic.completed_at.isoformat() if diagnostic.completed_at else None,
        "duration_ms": diagnostic.duration_ms,
        "ocr_text": diagnostic.ocr_text or None,
        "error": diagnostic.error or None,
        "current_step": details.get("current_step"),
        "logs": details.get("logs", []),
    })


@api_view(["POST"])
def register_push_device(request):
    device_id = str(request.data.get("device_id", "")).strip()
    token = str(request.data.get("fcm_token", "")).strip()
    if not device_id or not token:
        return Response({"status": "error", "message": "device_id and fcm_token are required."}, status=400)
    if len(device_id) > 128 or len(token) > 512:
        return Response({"status": "error", "message": "device_id or fcm_token is too long."}, status=400)
    defaults = {
        "fcm_token": token,
        "device_name": str(request.data.get("device_name", ""))[:200],
        "platform": str(request.data.get("platform", "android"))[:64],
        "app_version": str(request.data.get("app_version", ""))[:64],
        "os_version": str(request.data.get("os_version", ""))[:64],
    }
    Device.objects.update_or_create(device_id=device_id, defaults=defaults)
    return Response({"status": "ok", "message": "Push token registered."})


@api_view(["GET"])
def fuel_current_prices(request):
    _record_fuel_device(request)
    row = FuelPrice.objects.first()
    if row is None:
        return Response({"data": None, "message": "No fuel price data is available yet."}, status=404)
    return Response({"data": serialize_fuel_price(row)})


@api_view(["GET"])
def fuel_fetch_current(request):
    _record_fuel_device(request)
    try:
        return Response(fetch_current_fuel_prices())
    except FuelPriceImportError as exc:
        return Response({"status": "error", "message": str(exc)}, status=502)


@api_view(["GET"])
def fuel_price_history(request):
    _record_fuel_device(request)
    try:
        limit = min(max(int(request.query_params.get("limit", 30)), 1), 365)
    except ValueError:
        return Response({"detail": "limit must be an integer from 1 to 365."}, status=400)
    items = [serialize_fuel_price(row) for row in FuelPrice.objects.all()[:limit]]
    return Response({"count": len(items), "results": items})


@api_view(["GET"])
def import_fuel_price_history(request):
    _record_fuel_device(request)
    fuel = request.query_params.get("fuel", "").strip().lower()
    if fuel not in ("petrol", "diesel"):
        return Response({"detail": "fuel must be petrol or diesel."}, status=400)
    try:
        limit = min(max(int(request.query_params.get("limit", 30)), 1), 365)
    except ValueError:
        return Response({"detail": "limit must be an integer from 1 to 365."}, status=400)
    try:
        result = fetch_fuel_price_history(fuel, limit)
    except FuelPriceImportError as exc:
        return Response({"status": "error", "message": str(exc)}, status=502)
    rows = [serialize_fuel_price(row) for row in FuelPrice.objects.filter(
        effective_date__in=result["dates"]
    )]
    result["results"] = rows
    return Response(result)


def _record_fuel_device(request):
    device_id = request.headers.get("X-Device-ID", "").strip()
    if not device_id:
        return
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",", 1)[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")
    FuelDevice.objects.update_or_create(device_id=device_id[:128], defaults={
        "device_name": request.headers.get("X-Device-Name", "")[:200],
        "platform": request.headers.get("X-Platform", "")[:64],
        "app_version": request.headers.get("X-App-Version", "")[:64],
        "os_version": request.headers.get("X-OS-Version", "")[:64],
        "last_ip_address": ip_address or None,
    })


@api_view(["POST"])
def register_fuel_push_device(request):
    device_id = str(request.data.get("device_id", "")).strip()
    token = str(request.data.get("fcm_token", "")).strip()
    if not device_id or not token:
        return Response({"status": "error", "message": "device_id and fcm_token are required."}, status=400)
    if len(device_id) > 128 or len(token) > 512:
        return Response({"status": "error", "message": "device_id or fcm_token is too long."}, status=400)
    FuelDevice.objects.update_or_create(device_id=device_id, defaults={
        "fcm_token": token,
        "device_name": str(request.data.get("device_name", ""))[:200],
        "platform": str(request.data.get("platform", "android"))[:64],
        "app_version": str(request.data.get("app_version", ""))[:64],
        "os_version": str(request.data.get("os_version", ""))[:64],
    })
    return Response({"status": "ok", "message": "Fuel app push token registered."})


@require_GET
def fuel_api_docs(request):
    return render(request, "api/fuel_api_docs.html", {
        "base_url": f"{request.scheme}://{request.get_host()}/api/v1/fuel/",
    })
