from django.db import migrations


def add_runtime_settings(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    settings = [
        ("DAILY_PRICE_FETCH_LOCK", "", "Internal lease used to prevent overlapping scheduled and API price fetches.", True),
        ("RAPIDOCR_INTRA_OP_THREADS", "1", "ONNX threads per RapidOCR operation; use 1 on small hosting plans.", False),
        ("RAPIDOCR_INTER_OP_THREADS", "1", "ONNX parallel operation threads for RapidOCR; use 1 on small hosting plans.", False),
    ]
    for name, value, description, is_secret in settings:
        EnvironmentVariable.objects.get_or_create(
            name=name,
            defaults={"value": value, "description": description, "is_secret": is_secret},
        )


def remove_fetch_lock(apps, schema_editor):
    apps.get_model("api", "EnvironmentVariable").objects.filter(
        name__in=("DAILY_PRICE_FETCH_LOCK", "RAPIDOCR_INTRA_OP_THREADS", "RAPIDOCR_INTER_OP_THREADS")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0004_pushnotifications")]

    operations = [migrations.RunPython(add_runtime_settings, remove_fetch_lock)]
