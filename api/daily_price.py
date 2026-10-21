"""Run today's price import with a cross-process database lease and live log progress."""
from datetime import timedelta
from uuid import uuid4

from django.db import OperationalError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import DailyPriceFetchLog, EnvironmentVariable
from .youtube import YouTubeImportError, fetch_todays_price


DAILY_TIME_SETTING = "DAILY_PRICE_FETCH_TIME"
FETCH_LOCK_SETTING = "DAILY_PRICE_FETCH_LOCK"
FETCH_LOCK_BUSY_MESSAGE = "Fetch skipped because another run is already active."
FETCH_LOCK_MINUTES = 5


def _acquire_fetch_lease():
    """Atomically claim the singleton settings row, then release the DB lock."""
    now = timezone.now()
    with transaction.atomic():
        # This existing row serializes lease acquisition across processes/hosts.
        EnvironmentVariable.objects.select_for_update().get(name=DAILY_TIME_SETTING)
        lock = EnvironmentVariable.objects.select_for_update().get(name=FETCH_LOCK_SETTING)
        try:
            current_token, expiry_text = lock.value.split("|", 1)
            expires_at = parse_datetime(expiry_text)
        except (ValueError, AttributeError):
            current_token, expires_at = "", None
        if current_token and expires_at and expires_at > now:
            return None

        token = uuid4().hex
        expires_at = now + timedelta(minutes=FETCH_LOCK_MINUTES)
        lease_value = f"{token}|{expires_at.isoformat()}"
        claimed = EnvironmentVariable.objects.filter(pk=lock.pk, value=lock.value).update(
            value=lease_value,
            updated_at=now,
        )
        if not claimed:
            return None
        return token


def _release_fetch_lease(token):
    # Do not clear a lease that expired and was acquired by a newer fetch.
    with transaction.atomic():
        EnvironmentVariable.objects.select_for_update().get(name=DAILY_TIME_SETTING)
        lock = EnvironmentVariable.objects.select_for_update().get(name=FETCH_LOCK_SETTING)
        if lock.value.startswith(f"{token}|"):
            EnvironmentVariable.objects.filter(pk=lock.pk, value=lock.value).update(
                value="",
                updated_at=timezone.now(),
            )


def _renew_fetch_lease(token):
    lock = EnvironmentVariable.objects.filter(name=FETCH_LOCK_SETTING).first()
    if not lock or not lock.value.startswith(f"{token}|"):
        return
    now = timezone.now()
    expires_at = now + timedelta(minutes=FETCH_LOCK_MINUTES)
    EnvironmentVariable.objects.filter(pk=lock.pk, value=lock.value).update(
        value=f"{token}|{expires_at.isoformat()}",
        updated_at=now,
    )


def run_daily_price_fetch(called_by, scheduled_date=None, call_log=None):
    """Run today's importer once at a time, persisting each step for diagnosis."""
    if call_log is None:
        call_log = DailyPriceFetchLog.objects.create(
            called_by=called_by,
            scheduled_date=scheduled_date if called_by == DailyPriceFetchLog.Trigger.AUTO else None,
        )

    try:
        lease_token = _acquire_fetch_lease()
    except OperationalError:
        result = {"status": "in_progress", "added": 0, "logs": []}
        error = FETCH_LOCK_BUSY_MESSAGE
    except Exception as exc:
        result = {"status": "failure", "logs": []}
        error = f"Could not acquire the daily fetch lock: {exc}"
    else:
        if lease_token is None:
            result = {"status": "in_progress", "added": 0, "logs": []}
            error = FETCH_LOCK_BUSY_MESSAGE
        else:
            def persist_progress(logs):
                _renew_fetch_lease(lease_token)
                DailyPriceFetchLog.objects.filter(pk=call_log.pk).update(
                    details={"status": "running", "logs": logs}
                )

            try:
                result = fetch_todays_price(progress_callback=persist_progress)
                error = ""
            except YouTubeImportError as exc:
                error = str(exc)
                result = {"status": "failure", "logs": exc.logs}
            except Exception as exc:
                error = f"Daily price fetch failed: {exc}"
                result = {"status": "failure", "logs": []}
            finally:
                try:
                    _release_fetch_lease(lease_token)
                except Exception:
                    # Keep the lease's expiry as a crash-recovery backstop.
                    import logging
                    logging.getLogger(__name__).exception("Could not release daily price fetch lease")

    is_success = result.get("status") in {"success", "already_exists"}
    if not is_success and not error:
        error = result.get("error") or "No readable price was found in today's channel uploads."

    call_log.result = DailyPriceFetchLog.Result.SUCCESS if is_success else DailyPriceFetchLog.Result.FAILURE
    call_log.error = error
    call_log.completed_at = timezone.now()
    call_log.details = {key: value for key, value in result.items() if key != "logs"}
    if result.get("logs"):
        call_log.details["logs"] = result["logs"]
    call_log.save(update_fields=["result", "error", "completed_at", "details"])
    return call_log, result
