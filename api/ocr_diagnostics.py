"""Run an isolated one-thumbnail OCR diagnostic without writing a Price row."""
import logging
import time

from django.db import close_old_connections
from django.utils import timezone

from .daily_price import _acquire_fetch_lease, _release_fetch_lease
from .models import OCRDiagnosticLog
from .youtube import _download_thumbnail, _get_ocr_engine, _recognize_thumbnail


logger = logging.getLogger(__name__)


def run_ocr_diagnostic(diagnostic_id):
    close_old_connections()
    diagnostic = None
    lease_token = None
    logs = []

    def record(step, status, message, **extra):
        entry = {"step": step, "status": status, "message": message, **extra}
        logs.append(entry)
        OCRDiagnosticLog.objects.filter(pk=diagnostic_id).update(
            details={"current_step": step, "logs": logs}
        )

    started = time.monotonic()
    current_step = "prepare"
    try:
        diagnostic = OCRDiagnosticLog.objects.get(pk=diagnostic_id)
        lease_token = _acquire_fetch_lease()
        if lease_token is None:
            current_step = "fetch_lock"
            raise RuntimeError("Another price or OCR operation is currently using the OCR engine. Try again after it finishes.")

        thumbnail_url = f"https://i.ytimg.com/vi/{diagnostic.video_id}/hqdefault.jpg"
        current_step = "download_thumbnail"
        record(current_step, "running", "Downloading the selected YouTube thumbnail.")
        image_bytes = _download_thumbnail(thumbnail_url)
        record(current_step, "ok", "Thumbnail download succeeded.", bytes=len(image_bytes))

        current_step = "initialize_ocr"
        init_started = time.monotonic()
        record(current_step, "running", "Initializing RapidOCR and ONNX Runtime.")
        _get_ocr_engine()
        record(current_step, "ok", "RapidOCR initialized.", duration_ms=int((time.monotonic() - init_started) * 1000))

        current_step = "run_ocr"
        ocr_started = time.monotonic()
        record(current_step, "running", "Running OCR on the thumbnail.")
        text = _recognize_thumbnail(image_bytes)
        duration_ms = int((time.monotonic() - started) * 1000)
        record(current_step, "ok", "OCR completed.", ocr_text=text[:500], duration_ms=int((time.monotonic() - ocr_started) * 1000))
        diagnostic.status = OCRDiagnosticLog.Status.SUCCESS
        diagnostic.ocr_text = text[:2000]
        diagnostic.duration_ms = duration_ms
        diagnostic.error = ""
    except Exception as exc:
        logger.exception("OCR diagnostic %s failed during %s", diagnostic_id, current_step)
        try:
            record(current_step, "error", str(exc)[:1000])
        except Exception:
            logger.exception("Could not persist OCR diagnostic failure stage")
        if diagnostic is None:
            diagnostic = OCRDiagnosticLog.objects.filter(pk=diagnostic_id).first()
        if diagnostic:
            diagnostic.status = OCRDiagnosticLog.Status.FAILURE
            diagnostic.error = f"{current_step}: {exc}"[:2000]
            diagnostic.duration_ms = int((time.monotonic() - started) * 1000)
    finally:
        if diagnostic:
            diagnostic.completed_at = timezone.now()
            diagnostic.details = {"current_step": current_step, "logs": logs}
            diagnostic.save(update_fields=("status", "ocr_text", "error", "duration_ms", "completed_at", "details"))
        if lease_token:
            try:
                _release_fetch_lease(lease_token)
            except Exception:
                logger.exception("Could not release OCR diagnostic lease %s", diagnostic_id)
        close_old_connections()
