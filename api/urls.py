from django.urls import path

from .views import (
    api_docs,
    current_price,
    fetch_prices,
    fetch_todays_price,
    fetch_todays_price_status,
    price_history,
    register_push_device,
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
    path("devices/register-push/", register_push_device, name="register-push-device"),
]
