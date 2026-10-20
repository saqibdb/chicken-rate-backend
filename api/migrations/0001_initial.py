# Generated for the initial API schema.
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=128, unique=True)),
                ("device_name", models.CharField(blank=True, max_length=200)),
                ("platform", models.CharField(blank=True, max_length=64)),
                ("app_version", models.CharField(blank=True, max_length=64)),
                ("os_version", models.CharField(blank=True, max_length=64)),
                ("last_ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="Price",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price_date", models.DateField(db_index=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="PKR", max_length=3)),
                ("video_id", models.CharField(max_length=32, unique=True)),
                ("video_title", models.CharField(max_length=500)),
                ("video_url", models.URLField(max_length=500)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-price_date", "-published_at"]},
        ),
    ]
