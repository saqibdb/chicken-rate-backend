"""Fetch and persist current and historical fuel prices from autoones.com."""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from .models import FuelPrice

BASE_URL = "https://api2.autoones.com/api/fuel-prices"


class FuelPriceImportError(Exception):
    pass


def _get_json(url):
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "ChickenRateBackend/1.0"})
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise FuelPriceImportError(f"Fuel price provider request failed: {exc}") from exc
    if not isinstance(data, dict):
        raise FuelPriceImportError("Fuel price provider returned an invalid response.")
    return data


def _decimal(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FuelPriceImportError(f"Invalid {field} value from fuel price provider.") from exc


def _updated_at(value):
    if not value:
        return None
    parsed = parse_datetime(value.replace(" ", "T", 1))
    if parsed is None:
        raise FuelPriceImportError("Invalid price_updated_at value from fuel price provider.")
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def fetch_current_fuel_prices():
    data = _get_json(BASE_URL)
    entries = data.get("prices")
    if not isinstance(entries, list):
        raise FuelPriceImportError("Fuel price provider response is missing prices.")
    saved = []
    with transaction.atomic():
        for item in entries:
            slug = str(item.get("slug", "")).lower()
            if slug not in ("petrol", "diesel"):
                continue
            try:
                effective_date = datetime.strptime(item["effective_date"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError) as exc:
                raise FuelPriceImportError("Invalid effective_date value from fuel price provider.") from exc
            price = _decimal(item.get("price_pkr"), "price_pkr")
            difference = _decimal(item.get("change_pkr"), "change_pkr")
            values = {"price_updated_at": _updated_at(item.get("price_updated_at"))}
            if slug == "petrol":
                values.update(petrol_price=price, petrol_price_difference=difference)
            else:
                values.update(diesel_price=price, diesel_price_difference=difference)
            obj, _ = FuelPrice.objects.get_or_create(effective_date=effective_date)
            for key, value in values.items():
                setattr(obj, key, value)
            obj.save()
            saved.append(obj)
    return {"status": "success", "saved": len(saved), "prices": [serialize_fuel_price(row) for row in saved]}


def fetch_fuel_price_history(fuel, limit=30):
    fuel = fuel.lower()
    if fuel not in ("petrol", "diesel"):
        raise FuelPriceImportError("fuel must be petrol or diesel.")
    data = _get_json(f"{BASE_URL}/history?" + urlencode({"fuel": fuel, "view": "daily", "limit": limit}))
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise FuelPriceImportError("Fuel price provider response is missing rows.")
    saved_dates = []
    with transaction.atomic():
        for item in rows:
            try:
                effective_date = datetime.strptime(item["effective_date"], "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError) as exc:
                raise FuelPriceImportError("Invalid effective_date in fuel price history.") from exc
            values = {}
            prefix = "petrol" if fuel == "petrol" else "diesel"
            values[f"{prefix}_price"] = _decimal(item.get("price_pkr"), "price_pkr")
            values[f"{prefix}_price_difference"] = _decimal(item.get("change_pkr"), "change_pkr")
            obj, _ = FuelPrice.objects.get_or_create(effective_date=effective_date)
            for key, value in values.items():
                setattr(obj, key, value)
            obj.save()
            saved_dates.append(effective_date.isoformat())
    return {"status": "success", "fuel": fuel, "saved": len(saved_dates), "dates": saved_dates}


def serialize_fuel_price(row):
    def text(value):
        return str(value) if value is not None else None
    return {
        "effective_date": row.effective_date.isoformat(),
        "petrol_price": text(row.petrol_price),
        "petrol_price_difference": text(row.petrol_price_difference),
        "diesel_price": text(row.diesel_price),
        "diesel_price_difference": text(row.diesel_price_difference),
        "price_updated_at": row.price_updated_at.isoformat() if row.price_updated_at else None,
    }
