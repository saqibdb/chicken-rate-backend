from django.apps import AppConfig

import logging
import sys
import threading
import time
from datetime import time as day_time

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
        threading.Thread(target=self._daily_price_scheduler, name="daily-price-scheduler", daemon=True).start()

    @staticmethod
    def _daily_price_scheduler():
        from .configuration import get_runtime_setting
        from .daily_price import run_daily_price_fetch
        from .models import DailyPriceFetchLog

        while True:
            try:
                close_old_connections()
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
                    if created:
                        logger.info("Starting scheduled chicken price fetch for %s", today)
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
