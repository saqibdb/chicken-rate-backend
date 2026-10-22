from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0007_rapidocr_resource_settings")]

    operations = [
        migrations.CreateModel(
            name="FuelDailyPriceFetchLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scheduled_date", models.DateField(unique=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("success", models.BooleanField(default=False)),
                ("error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-started_at"], "verbose_name": "fuel daily price fetch log", "verbose_name_plural": "fuel daily price fetch logs"},
        ),
        migrations.CreateModel(
            name="FuelDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=128, unique=True)),
                ("device_name", models.CharField(blank=True, max_length=200)),
                ("platform", models.CharField(blank=True, max_length=64)),
                ("app_version", models.CharField(blank=True, max_length=64)),
                ("os_version", models.CharField(blank=True, max_length=64)),
                ("fcm_token", models.CharField(blank=True, db_index=True, max_length=512)),
                ("last_ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="FuelPrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("effective_date", models.DateField(db_index=True, unique=True)),
                ("petrol_price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("petrol_price_difference", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("diesel_price", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("diesel_price_difference", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("price_updated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-effective_date"], "verbose_name": "fuel price", "verbose_name_plural": "fuel prices"},
        ),
        migrations.CreateModel(
            name="FuelPushNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Fuel Prices", max_length=120)),
                ("message", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("sending", "Sending"), ("sent", "Sent"), ("partial", "Partially sent"), ("failed", "Failed")], default="sending", max_length=10)),
                ("devices_targeted", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "fuel push notification", "verbose_name_plural": "fuel push notifications"},
        ),
    ]
