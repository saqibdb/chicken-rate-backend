from django.db import migrations


def add_rapidocr_settings(apps, schema_editor):
    EnvironmentVariable = apps.get_model("api", "EnvironmentVariable")
    settings = [
        (
            "RAPIDOCR_MODEL_SIZE",
            "tiny",
            "RapidOCR detector and recognizer size: tiny (lowest memory), small, or medium. Restart the server after changing.",
            False,
        ),
        (
            "RAPIDOCR_MAX_SIDE_LEN",
            "640",
            "Maximum detector image side length in pixels; values are bounded to 320-1600. Restart the server after changing.",
            False,
        ),
    ]
    for name, value, description, is_secret in settings:
        EnvironmentVariable.objects.get_or_create(
            name=name,
            defaults={"value": value, "description": description, "is_secret": is_secret},
        )


def remove_rapidocr_settings(apps, schema_editor):
    apps.get_model("api", "EnvironmentVariable").objects.filter(
        name__in=("RAPIDOCR_MODEL_SIZE", "RAPIDOCR_MAX_SIDE_LEN")
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0006_ocrdiagnosticlog")]

    operations = [migrations.RunPython(add_rapidocr_settings, remove_rapidocr_settings)]
