from django.contrib import admin
from django.contrib import messages
from django import forms
from django.http import HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .models import DailyPriceFetchLog, Device, EnvironmentVariable, OCRDiagnosticLog, Price, PushNotification
from .push_notifications import send_broadcast


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ("price_date", "amount", "currency", "video_title", "published_at")
    list_filter = ("currency", "price_date")
    search_fields = ("video_title", "video_id")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "device_name", "platform", "app_version", "last_seen")
    search_fields = ("device_id", "device_name")
    list_filter = ("platform",)

    def get_readonly_fields(self, request, obj=None):
        return ("first_seen", "last_seen") if obj else ()


class EnvironmentVariableForm(forms.ModelForm):
    class Meta:
        model = EnvironmentVariable
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.is_secret:
            self.fields["value"].widget = forms.PasswordInput(render_value=False)
            self.fields["value"].help_text = "Leave blank to keep the current secret. Enter a value to replace it."


@admin.register(EnvironmentVariable)
class EnvironmentVariableAdmin(admin.ModelAdmin):
    form = EnvironmentVariableForm
    list_display = ("name", "masked_value", "is_secret", "description", "updated_at")
    list_filter = ("is_secret",)
    search_fields = ("name", "description")
    fields = ("name", "value", "description", "is_secret", "updated_at")
    readonly_fields = ("updated_at",)

    @admin.display(description="Value")
    def masked_value(self, obj):
        return "••••••••" if obj.is_secret and obj.value else obj.value

    def save_model(self, request, obj, form, change):
        if change and obj.is_secret and not form.cleaned_data.get("value"):
            obj.value = EnvironmentVariable.objects.get(pk=obj.pk).value
        super().save_model(request, obj, form, change)


@admin.register(DailyPriceFetchLog)
class DailyPriceFetchLogAdmin(admin.ModelAdmin):
    list_display = ("called_at", "called_by", "result", "completed_at")
    list_filter = ("called_by", "result", "called_at")
    search_fields = ("error",)
    readonly_fields = ("called_at", "completed_at", "called_by", "result", "error", "details", "scheduled_date")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class PushNotificationForm(forms.Form):
    title = forms.CharField(max_length=120, initial="Chicken Price")
    message = forms.CharField(max_length=2000, widget=forms.Textarea(attrs={"rows": 5}), label="Message")


@admin.register(PushNotification)
class PushNotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "title", "status", "devices_targeted", "sent_count", "failure_count")
    list_filter = ("status", "created_at")
    search_fields = ("title", "message", "error")
    change_list_template = "admin/api/pushnotification/change_list.html"
    readonly_fields = ("created_at", "sent_at", "status", "devices_targeted", "sent_count", "failure_count", "error")
    fields = ("title", "message", *readonly_fields)

    def get_urls(self):
        return [path("send/", self.admin_site.admin_view(self.send_view), name="api_pushnotification_send")] + super().get_urls()

    def send_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            form = PushNotificationForm(request.POST)
            if form.is_valid():
                notification = PushNotification.objects.create(
                    title=form.cleaned_data["title"], message=form.cleaned_data["message"]
                )
                notification = send_broadcast(notification)
                if notification.sent_count:
                    messages.success(
                        request,
                        f"Notification processed: sent to {notification.sent_count} device(s); "
                        f"{notification.failure_count} failure(s).",
                    )
                else:
                    messages.error(request, notification.error or "No notifications were sent.")
                return HttpResponseRedirect(reverse("admin:api_pushnotification_changelist"))
        else:
            form = PushNotificationForm()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Send push notification",
        }
        return TemplateResponse(request, "admin/api/pushnotification/send.html", context)


@admin.register(OCRDiagnosticLog)
class OCRDiagnosticLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "video_id", "status", "duration_ms", "completed_at")
    list_filter = ("status", "created_at")
    search_fields = ("video_id", "ocr_text", "error")
    readonly_fields = ("video_id", "created_at", "completed_at", "status", "duration_ms", "ocr_text", "error", "details")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
