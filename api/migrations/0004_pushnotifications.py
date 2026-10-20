from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0003_dailypricefetchlog")]

    operations = [
        migrations.AddField(
            model_name="device",
            name="fcm_token",
            field=models.CharField(blank=True, db_index=True, max_length=512),
        ),
        migrations.CreateModel(
            name="PushNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Chicken Price", max_length=120)),
                ("message", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("sending", "Sending"), ("sent", "Sent"), ("partial", "Partially sent"), ("failed", "Failed")], default="sending", max_length=10)),
                ("devices_targeted", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "push notification", "verbose_name_plural": "push notifications"},
        ),
    ]
