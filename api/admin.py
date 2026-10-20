from django.contrib import admin
from .models import Device, Price


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ("price_date", "amount", "currency", "video_title", "published_at")
    list_filter = ("currency", "price_date")
    search_fields = ("video_title", "video_id")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "device_name", "platform", "app_version", "last_seen")
    search_fields = ("device_id", "device_name")
