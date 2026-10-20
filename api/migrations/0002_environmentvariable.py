from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="EnvironmentVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("value", models.TextField(blank=True)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_secret", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "environment variable",
                "verbose_name_plural": "environment variables",
                "ordering": ["name"],
            },
        ),
    ]
