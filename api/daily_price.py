from django.db import transaction
from django.utils import timezone

from .models import DailyPriceFetchLog, EnvironmentVariable
from .youtube import YouTubeImportError, fetch_todays_price


DAILY_TIME_SETTING = "DAILY_PRICE_FETCH_TIME"


def run_daily_price_fetch(called_by, scheduled_date=None, call_log=None):
    """Run today's importer once at a time and persist an audit record."""
    if call_log is None:
        call_log = DailyPriceFetchLog.objects.create(
            called_by=called_by,
            scheduled_date=scheduled_date if called_by == DailyPriceFetchLog.Trigger.AUTO else None,
        )

    result = None
    error = ""
    try:
        with transaction.atomic():
            # Serialize API-triggered and scheduled runs, including the first-price case.
            EnvironmentVariable.objects.select_for_update().get(name=DAILY_TIME_SETTING)
            result = fetch_todays_price()
    except YouTubeImportError as exc:
        error = str(exc)
        result = {"status": "failure", "logs": exc.logs}
    except Exception as exc:
        error = f"Daily price fetch failed: {exc}"
        result = {"status": "failure", "logs": []}

    is_success = result.get("status") in {"success", "already_exists"}
    if not is_success and not error:
        error = result.get("error") or "No readable price was found in today's channel uploads."

    call_log.result = DailyPriceFetchLog.Result.SUCCESS if is_success else DailyPriceFetchLog.Result.FAILURE
    call_log.error = error
    call_log.completed_at = timezone.now()
    call_log.details = {key: value for key, value in result.items() if key != "logs"}
    call_log.save(update_fields=["result", "error", "completed_at", "details"])
    return call_log, result
