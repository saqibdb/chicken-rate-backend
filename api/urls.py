from django.urls import path

from .views import api_docs, current_price, fetch_prices, fetch_todays_price, price_history, test

urlpatterns = [
    path("", api_docs, name="api-docs"),
    path("test/", test, name="test-check"),
    path("prices/current/", current_price, name="current-price"),
    path("prices/history/", price_history, name="price-history"),
    path("prices/fetch/", fetch_prices, name="fetch-youtube-prices"),
    path("prices/fetch/today/", fetch_todays_price, name="fetch-todays-price"),
]
