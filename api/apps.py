from django.apps import AppConfig

import logging
import os
import sys
import threading
import time
from datetime import time as day_time, timedelta

from django.db import close_old_connections
from django.utils import timezone


logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        command_line = " ".join(sys.argv).lower()
        server_process = any(name in command_line for name in ("gunicorn", "runserver", "uvicorn", "daphne", "uwsgi"))
        if not server_process:
            return
        # Django's autoreloader imports the app in both parent and child processes.
        # Only start the scheduler in the child that serves requests.
        if (
            "runserver" in command_line
            and "--noreload" not in sys.argv
            and os.environ.get("RUN_MAIN") != "true"
        ):
            return
        threading.Thread(target=self._daily_price_scheduler, name="daily-price-scheduler", daemon=True).start()

    @staticmethod
    def _daily_price_scheduler():
        from .configuration import get_runtime_setting
        from .daily_price import FETCH_LOCK_MINUTES, FETCH_LOCK_BUSY_MESSAGE, run_daily_price_fetch
        from .models import DailyPriceFetchLog
        from django.utils.dateparse import parse_datetime

        while True:
            try:
                close_old_connections()
                now_utc = timezone.now()
                stale_api_call = DailyPriceFetchLog.objects.filter(
                    called_by=DailyPriceFetchLog.Trigger.API,
                    result=DailyPriceFetchLog.Result.RUNNING,
                    called_at__lt=now_utc - timedelta(minutes=FETCH_LOCK_MINUTES),
                ).order_by("called_at").first()
                if stale_api_call:
                    lock_value = get_runtime_setting("DAILY_PRICE_FETCH_LOCK", "")
                    try:
                        _, lock_expiry_text = lock_value.split("|", 1)
                        lock_expiry = parse_datetime(lock_expiry_text)
                    except (ValueError, AttributeError):
                        lock_expiry = None
                    if not lock_expiry or lock_expiry <= now_utc:
                        logger.warning("Retrying interrupted API price fetch %s", stale_api_call.pk)
                        run_daily_price_fetch(DailyPriceFetchLog.Trigger.API, call_log=stale_api_call)
                        continue
                target = day_time.fromisoformat(
                    get_runtime_setting("DAILY_PRICE_FETCH_TIME", "08:00").strip()
                )
                now = timezone.localtime()
                if now.time().replace(tzinfo=None) >= target:
                    today = timezone.localdate()
                    call_log, created = DailyPriceFetchLog.objects.get_or_create(
                        scheduled_date=today,
                        defaults={
                            "called_by": DailyPriceFetchLog.Trigger.AUTO,
                            "result": DailyPriceFetchLog.Result.RUNNING,
                        },
                    )
                    retry_busy_fetch = (
                        not created
                        and call_log.result == DailyPriceFetchLog.Result.FAILURE
                        and call_log.error == FETCH_LOCK_BUSY_MESSAGE
                    )
                    retry_crashed_fetch = (
                        not created
                        and call_log.result == DailyPriceFetchLog.Result.RUNNING
                        and call_log.called_at < timezone.now() - timedelta(minutes=FETCH_LOCK_MINUTES)
                    )
                    if created or retry_busy_fetch or retry_crashed_fetch:
                        logger.info("Starting scheduled chicken price fetch for %s", today)
                        call_log.result = DailyPriceFetchLog.Result.RUNNING
                        call_log.error = ""
                        call_log.completed_at = None
                        call_log.save(update_fields=("result", "error", "completed_at"))
                        run_daily_price_fetch(
                            DailyPriceFetchLog.Trigger.AUTO,
                            scheduled_date=today,
                            call_log=call_log,
                        )
            except Exception:
                logger.exception("Daily chicken price scheduler tick failed")
            finally:
                close_old_connections()
            time.sleep(30)
