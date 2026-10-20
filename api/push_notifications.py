"""Firebase Cloud Messaging delivery for Android app installations."""
import json

from django.utils import timezone

from .configuration import get_runtime_setting
from .models import Device, PushNotification


def send_broadcast(notification):
    """Send a notification to every registered token, in FCM's 500-token batches."""
    devices = list(Device.objects.exclude(fcm_token="").only("id", "fcm_token"))
    notification.devices_targeted = len(devices)
    if not devices:
        notification.status = PushNotification.Status.FAILED
        notification.error = "No devices have registered a push token yet."
        notification.sent_at = timezone.now()
        notification.save(update_fields=("devices_targeted", "status", "error", "sent_at"))
        return notification

    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        app = _firebase_app(firebase_admin, credentials)
        sent = failures = 0
        errors = []
        tokens = [device.fcm_token for device in devices]
        for offset in range(0, len(tokens), 500):
            batch_tokens = tokens[offset:offset + 500]
            response = messaging.send_each_for_multicast(
                messaging.MulticastMessage(
                    notification=messaging.Notification(title=notification.title, body=notification.message),
                    data={"notification_id": str(notification.pk)},
                    tokens=batch_tokens,
                ),
                app=app,
            )
            sent += response.success_count
            failures += response.failure_count
            for token, result in zip(batch_tokens, response.responses):
                if result.success:
                    continue
                code = getattr(result.exception, "code", "")
                if code in ("messaging/registration-token-not-registered", "messaging/invalid-registration-token"):
                    Device.objects.filter(fcm_token=token).update(fcm_token="")
                if len(errors) < 10:
                    errors.append(str(result.exception))
        notification.sent_count = sent
        notification.failure_count = failures
        notification.status = (
            PushNotification.Status.SENT if failures == 0 else
            PushNotification.Status.PARTIAL if sent else PushNotification.Status.FAILED
        )
        notification.error = "\n".join(errors)
    except Exception as exc:
        notification.sent_count = 0
        notification.failure_count = len(devices)
        notification.status = PushNotification.Status.FAILED
        notification.error = str(exc)
    notification.sent_at = timezone.now()
    notification.save(update_fields=(
        "devices_targeted", "sent_count", "failure_count", "status", "error", "sent_at"
    ))
    return notification


def _firebase_app(firebase_admin, credentials):
    try:
        return firebase_admin.get_app()
    except ValueError:
        raw_json = get_runtime_setting("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        file_path = get_runtime_setting("FIREBASE_SERVICE_ACCOUNT_FILE", "").strip()
        if raw_json:
            credential = credentials.Certificate(json.loads(raw_json))
        elif file_path:
            credential = credentials.Certificate(file_path)
        else:
            raise RuntimeError(
                "Set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_FILE in Environment Variables."
            )
        return firebase_admin.initialize_app(credential)
