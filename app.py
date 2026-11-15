import csv
import io
import os
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import date, timedelta
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

EARLIEST_DATE = date(2000, 11, 1)
WORLD_BOUNDS = (-180.0, -85.0, 180.0, 85.0)
PRODUCTS = (
    ("MODIS", "MODIS_NRT", "MODIS_SP", date(2000, 11, 1)),
    ("VIIRS", "VIIRS_SNPP_NRT", "VIIRS_SNPP_SP", date(2012, 1, 20)),
    ("VIIRS", "VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP", date(2017, 11, 29)),
    ("VIIRS", "VIIRS_NOAA21_NRT", "VIIRS_NOAA21_SP", date(2022, 11, 10)),
)

_rate_lock = threading.Lock()
_rate_requests = defaultdict(deque)
_last_rate_cleanup = 0
_RATE_LIMITS = {
    "detections": (8, 60),
}


def _rate_limit_response(action):
    global _last_rate_cleanup
    limit, window_seconds = _RATE_LIMITS[action]
    client_ip = request.remote_addr or "unknown"
    now = time.monotonic()
    key = (action, client_ip)

    with _rate_lock:
        if now - _last_rate_cleanup >= 60:
            for old_key, old_timestamps in list(_rate_requests.items()):
                while old_timestamps and old_timestamps[0] <= now - 60:
                    old_timestamps.popleft()
                if not old_timestamps:
                    del _rate_requests[old_key]
            _last_rate_cleanup = now

        timestamps = _rate_requests[key]
        while timestamps and timestamps[0] <= now - window_seconds:
            timestamps.popleft()
        if len(timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - timestamps[0])))
            response = jsonify(error="Too many requests. Please try again shortly.")
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response
        timestamps.append(now)
    return None


def _parse_date(value):
    try:
        selected_date = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None, (jsonify(error="Choose a valid date in YYYY-MM-DD format."), 400)
    if selected_date < EARLIEST_DATE:
        return None, (
            jsonify(error=f"FIRMS date selection starts at {EARLIEST_DATE.isoformat()}."),
            400,
        )
    if selected_date > date.today():
        return None, (jsonify(error="The selected date cannot be in the future."), 400)
    return selected_date, None


@lru_cache(maxsize=1)
def _load_global_detections(date_text):
    map_key = os.getenv("FIRMS_MAP_KEY")
    if not map_key:
        raise RuntimeError("The FIRMS_MAP_KEY environment variable is not configured.")

    selected_date = date.fromisoformat(date_text)
    latest_nrt_start = date.today() - timedelta(days=4)
    west, south, east, north = WORLD_BOUNDS
    records = []

    for sensor, nrt_source, standard_source, first_date in PRODUCTS:
        if selected_date < first_date:
            continue
        source = nrt_source if selected_date >= latest_nrt_start else standard_source
        url = (
            "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
            f"{map_key}/{source}/{west},{south},{east},{north}/1/{date_text}"
        )
        try:
            with urlopen(url, timeout=60) as response:
                csv_text = response.read().decode("utf-8")
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace").strip()
            details = details.replace(map_key, "[redacted]")
            raise RuntimeError(
                f"FIRMS rejected the {source} request for {date_text} "
                f"(HTTP {error.code}): {details or error.reason}"
            ) from error
        except URLError as error:
            raise RuntimeError(f"Could not reach NASA FIRMS: {error.reason}") from error

        for row in csv.DictReader(io.StringIO(csv_text)):
            if row.get("acq_date", "").strip() != date_text:
                continue
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            records.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "date": row.get("acq_date", ""),
                    "time": row.get("acq_time", ""),
                    "sensor": sensor,
                    "source": source,
                    "confidence": row.get("confidence", ""),
                    "frp": row.get("frp", ""),
                }
            )

    return tuple(records)


def _public_record(row):
    return row


@app.get("/")
def home():
    return render_template(
        "index.html",
        earliest_date=EARLIEST_DATE.isoformat(),
        today=date.today().isoformat(),
    )


@app.get("/hotspot_world_report.html")
def world_report():
    response = send_from_directory(app.root_path, "hotspot_world_report.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/api/hotspots")
def hotspots():
    limited = _rate_limit_response("detections")
    if limited:
        return limited

    selected_date, error_response = _parse_date(request.args.get("date"))
    if error_response:
        return error_response

    try:
        records = _load_global_detections(selected_date.isoformat())
    except RuntimeError as error:
        return jsonify(error=str(error)), 502

    counts = Counter(row["sensor"] for row in records)
    response = jsonify(
        date=selected_date.isoformat(),
        total=len(records),
        counts={"MODIS": counts["MODIS"], "VIIRS": counts["VIIRS"]},
        points=[_public_record(row) for row in records],
        note=(
            "Counts are satellite detections, not confirmed individual fires. "
            "MODIS and VIIRS may observe the same event."
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
