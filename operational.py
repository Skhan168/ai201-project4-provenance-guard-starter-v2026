"""Request-level operational records, separate from the authorship audit."""

import json
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import g, request

import config

LOG_PATH = config.LOG_DIR / "operational.jsonl"
_lock = threading.Lock()


def append_record(record):
    """Append one structured request record without changing old records."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
    with _lock:
        with LOG_PATH.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


def install(app):
    """Register once, before rate limiting is initialized."""
    @app.before_request
    def start_operational_request():
        g.operational_started = time.perf_counter()
        g.operational_timestamp = datetime.now(timezone.utc).isoformat()
        supplied_id = request.headers.get("X-Request-ID", "")
        g.operational_request_id = supplied_id[:128] or str(uuid.uuid4())
        parsed = request.get_json(silent=True)
        g.operational_input = (
            parsed if request.is_json and parsed is not None
            else request.get_data(as_text=True)
        )

    @app.after_request
    def finish_operational_request(response):
        started = getattr(g, "operational_started", None)
        if started is None:
            return response

        response.headers["X-Request-ID"] = g.operational_request_id
        output = response.get_json(silent=True)
        if output is None:
            output = response.get_data(as_text=True)

        record = {
            "timestamp": g.operational_timestamp,
            "request_id": g.operational_request_id,
            "method": request.method,
            "path": request.path,
            "query": request.query_string.decode("utf-8", errors="replace"),
            "input": g.operational_input,
            "output": output,
            "http_status": response.status_code,
            "duration_seconds": time.perf_counter() - started,
        }
        try:
            append_record(record)
        except (OSError, ValueError, TypeError):
            app.logger.exception(
                "Operational logging failed for request %s",
                g.operational_request_id,
            )
        return response