from django.db import migrations, models


def add_daily_fetch_time(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    EnvironmentVariable.objects.get_or_create(
        name="DAILY_PRICE_FETCH_TIME",
        defaults={
            "value": "08:00",
            "description": "Daily automatic chicken price fetch time in Asia/Karachi (HH:MM).",
            "is_secret": False,
        },
    )


def remove_daily_fetch_time(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    EnvironmentVariable.objects.filter(name="DAILY_PRICE_FETCH_TIME").delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0002_environmentvariable")]

    operations = [
        migrations.CreateModel(
            name="DailyPriceFetchLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("called_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("called_by", models.CharField(choices=[("auto", "Automatic schedule"), ("api", "API request")], db_index=True, max_length=8)),
                ("result", models.CharField(choices=[("running", "Running"), ("success", "Success"), ("failure", "Failure")], db_index=True, default="running", max_length=10)),
                ("error", models.TextField(blank=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("scheduled_date", models.DateField(blank=True, null=True, unique=True)),
            ],
            options={"ordering": ["-called_at"]},
        ),
        migrations.RunPython(add_daily_fetch_time, remove_daily_fetch_time),
    ]
