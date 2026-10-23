from django.db import migrations, models


def create_fuel_schedule_setting(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    EnvironmentVariable.objects.get_or_create(
        name="FUEL_DAILY_PRICE_FETCH_TIME",
        defaults={
            "value": "08:00",
            "description": "Daily 24-hour HH:MM time (Asia/Karachi) to fetch fuel prices and notify fuel app devices.",
            "is_secret": False,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("api", "0008_fuel_prices_devices_notifications")]

    operations = [
        migrations.AddField(
            model_name="fueldailypricefetchlog",
            name="scheduled_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.RunPython(create_fuel_schedule_setting, migrations.RunPython.noop),
    ]
