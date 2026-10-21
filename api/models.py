from django.db import models


class Price(models.Model):
    """A chicken price published by a source video."""

    price_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="PKR")
    video_id = models.CharField(max_length=32, unique=True)
    video_title = models.CharField(max_length=500)
    video_url = models.URLField(max_length=500)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-price_date", "-published_at"]

    def __str__(self):
        return f"{self.price_date}: {self.currency} {self.amount}"


class Device(models.Model):
    """Latest known metadata and activity for a calling mobile device."""

    device_id = models.CharField(max_length=128, unique=True)
    device_name = models.CharField(max_length=200, blank=True)
    platform = models.CharField(max_length=64, blank=True)
    app_version = models.CharField(max_length=64, blank=True)
    os_version = models.CharField(max_length=64, blank=True)
    fcm_token = models.CharField(max_length=512, blank=True, db_index=True)
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return self.device_name or self.device_id


class EnvironmentVariable(models.Model):
    """Runtime configuration that administrators can change without a deploy."""

    name = models.CharField(max_length=100, unique=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    is_secret = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "environment variable"
        verbose_name_plural = "environment variables"

    def __str__(self):
        return self.name


class DailyPriceFetchLog(models.Model):
    class Trigger(models.TextChoices):
        AUTO = "auto", "Automatic schedule"
        API = "api", "API request"

    class Result(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    called_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    called_by = models.CharField(max_length=8, choices=Trigger.choices, db_index=True)
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.RUNNING, db_index=True)
    error = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    scheduled_date = models.DateField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-called_at"]

    def __str__(self):
        return f"{self.called_by} {self.called_at:%Y-%m-%d %H:%M:%S} ({self.result})"


class PushNotification(models.Model):
    class Status(models.TextChoices):
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partially sent"
        FAILED = "failed", "Failed"

    title = models.CharField(max_length=120, default="Chicken Price")
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENDING)
    devices_targeted = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "push notification"
        verbose_name_plural = "push notifications"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} — {self.status}"


class OCRDiagnosticLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    video_id = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING, db_index=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    ocr_text = models.TextField(blank=True)
    error = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OCR diagnostic log"
        verbose_name_plural = "OCR diagnostic logs"

    def __str__(self):
        return f"OCR {self.video_id} {self.created_at:%Y-%m-%d %H:%M:%S} ({self.status})"
