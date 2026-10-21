from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0005_daily_price_fetch_lock")]

    operations = [
        migrations.CreateModel(
            name="OCRDiagnosticLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("video_id", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failure", "Failure")], db_index=True, default="running", max_length=10)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("ocr_text", models.TextField(blank=True)),
                ("error", models.TextField(blank=True)),
                ("details", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "OCR diagnostic log", "verbose_name_plural": "OCR diagnostic logs"},
        ),
    ]
