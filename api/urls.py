from django.urls import path

from .views import (
    api_docs,
    current_price,
    fetch_prices,
    fetch_todays_price,
    fetch_todays_price_status,
    fuel_api_docs,
    fuel_current_prices,
    fuel_fetch_current,
    fuel_price_history,
    import_fuel_price_history,
    ocr_diagnostic_status,
    price_history,
    register_push_device,
    register_fuel_push_device,
    start_ocr_diagnostic,
    test,
)

urlpatterns = [
    path("", api_docs, name="api-docs"),
    path("test/", test, name="test-check"),
    path("prices/current/", current_price, name="current-price"),
    path("prices/history/", price_history, name="price-history"),
    path("prices/fetch/", fetch_prices, name="fetch-youtube-prices"),
    path("prices/fetch/today/", fetch_todays_price, name="fetch-todays-price"),
    path("prices/fetch/today/<int:call_id>/", fetch_todays_price_status, name="fetch-todays-price-status"),
    path("ocr/diagnostic/", start_ocr_diagnostic, name="ocr-diagnostic"),
    path("ocr/diagnostic/status/", ocr_diagnostic_status, name="ocr-diagnostic-status"),
    path("devices/register-push/", register_push_device, name="register-push-device"),
    path("fuel/", fuel_api_docs, name="fuel-api-docs"),
    path("fuel/prices/current/", fuel_current_prices, name="fuel-current-prices"),
    path("fuel/prices/fetch/", fuel_fetch_current, name="fuel-fetch-current"),
    path("fuel/prices/history/", fuel_price_history, name="fuel-price-history"),
    path("fuel/prices/history/import/", import_fuel_price_history, name="fuel-price-history-import"),
    path("fuel/devices/register-push/", register_fuel_push_device, name="fuel-register-push-device"),
]
