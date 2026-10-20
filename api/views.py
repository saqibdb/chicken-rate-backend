from datetime import date

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Device, Price


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
    queryset = Price.objects.all()
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
        limit = min(max(int(request.query_params.get("limit", 90)), 1), 365)
    except ValueError:
        return Response({"detail": "limit must be an integer from 1 to 365."}, status=400)

    items = [_price_payload(price) for price in queryset[:limit]]
    return Response({"count": len(items), "results": items})
