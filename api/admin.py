from django.contrib import admin
from django import forms

from .models import Device, EnvironmentVariable, Price


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = ("price_date", "amount", "currency", "video_title", "published_at")
    list_filter = ("currency", "price_date")
    search_fields = ("video_title", "video_id")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "device_name", "platform", "app_version", "last_seen")
    search_fields = ("device_id", "device_name")


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
