from django.db import migrations


def add_price_limits(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    settings = [
        (
            "CHICKEN_PRICE_MIN_AMOUNT",
            "5000",
            "Ignore OCR candidates below this live chicken wholesale price amount.",
        ),
        (
            "CHICKEN_PRICE_MAX_AMOUNT",
            "100000",
            "Ignore OCR candidates above this live chicken wholesale price amount.",
        ),
    ]
    for name, value, description in settings:
        EnvironmentVariable.objects.get_or_create(
            name=name,
            defaults={"value": value, "description": description, "is_secret": False},
        )


def remove_price_limits(apps, schema_editor):
    apps.get_model("api", "EnvironmentVariable").objects.filter(
        name__in=("CHICKEN_PRICE_MIN_AMOUNT", "CHICKEN_PRICE_MAX_AMOUNT")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0007_rapidocr_resource_settings")]

    operations = [migrations.RunPython(add_price_limits, remove_price_limits)]
