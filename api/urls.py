from django.urls import path

from .views import current_price, price_history, test

urlpatterns = [
    path("test/", test, name="health-check"),
    path("prices/current/", current_price, name="current-price"),
    path("prices/history/", price_history, name="price-history"),
]
