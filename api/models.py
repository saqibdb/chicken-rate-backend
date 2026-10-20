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
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True, db_index=True)

    def __str__(self):
        return self.device_name or self.device_id
