"""Read the environment's native token-usage SQLite database."""
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import stat
import sys
import time

COUNTERS = ("input", "output", "read", "write")
REQUIRED_COLUMNS = {"id", "stamp", "model", *COUNTERS}
MODEL_LIMIT = 200
PAGE_SIZE = 25
PERIODS = (1, 7, 30, 90)
FIELDS = ", ".join(f'COALESCE(SUM("{field}"), 0) AS "{field}"' for field in COUNTERS)
LOCAL_DAY = "date(stamp, 'unixepoch', 'localtime')"


class UsageError(Exception):
    """A stable, path-free error code for the extension view."""


def native_database():
    if not sys.platform.startswith("linux"):
        raise UsageError("unavailable")
    return Path.home() / ".local/share/cage/token-usage/counters.sqlite3"


def check_files(path):
    if not stat.S_ISDIR(path.parent.lstat().st_mode):
        raise UsageError("unavailable")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise UsageError("unavailable")
    for suffix in ("-journal", "-wal", "-shm"):
        try:
            mode = path.with_name(path.name + suffix).lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise UsageError("unavailable")


def validate(arguments):
    if not isinstance(arguments, dict) or arguments.keys() - {"days", "model", "page"}:
        raise UsageError("invalid_filters")
    days = arguments.get("days", 7)
    model = arguments.get("model", "")
    page = arguments.get("page", 1)
    if (
        type(days) is not int or days not in PERIODS
        or not isinstance(model, str) or len(model) > 128
        or any(not character.isprintable() for character in model)
        or type(page) is not int or not 1 <= page <= 2**31 - 1
    ):
        raise UsageError("invalid_filters")
    return days, model, page


def metrics(row):
    result = dict(row)
    prompt = result["input"] + result["read"] + result["write"]
    result["cache_hit_rate"] = result["read"] / prompt if prompt else None
    return result


def report(db, columns, days, model, page):
    now = time.localtime()
    today = date(now.tm_year, now.tm_mon, now.tm_mday)
    start = today - timedelta(days=days - 1)
    bounds = (start.isoformat(), today.isoformat())
    where = f"{LOCAL_DAY} BETWEEN ? AND ?"
    models = [
        row[0] for row in db.execute(
            f"SELECT DISTINCT model FROM requests WHERE {where} ORDER BY model LIMIT ?",
            (*bounds, MODEL_LIMIT + 1),
        )
    ]
    params = bounds
    if model:
        where += " AND model = ? COLLATE BINARY"
        params += (model,)
    buckets = {
        row["day"]: metrics(row)
        for row in db.execute(
            f"SELECT {LOCAL_DAY} AS day, {FIELDS}, COUNT(*) AS requests "
            f"FROM requests WHERE {where} GROUP BY 1",
            params,
        )
    }
    trend = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        trend.append(buckets.get(day) or {
            "day": day, **dict.fromkeys(COUNTERS, 0), "requests": 0, "cache_hit_rate": None,
        })

    totals = metrics({key: sum(day[key] for day in trend) for key in (*COUNTERS, "requests")})
    client = "COALESCE(NULLIF(client, ''), 'unknown')" if "client" in columns else "'unknown'"
    last_page = max(1, (totals["requests"] + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, last_page)
    rows = [
        dict(row) for row in db.execute(
            "SELECT strftime('%Y-%m-%d %H:%M:%S', stamp, 'unixepoch', 'localtime') AS time, "
            f'model, {client} AS client, input, output, "read", "write" '
            f"FROM requests WHERE {where} ORDER BY stamp DESC, id DESC LIMIT ? OFFSET ?",
            (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE),
        )
    ]
    return {
        "start": start.isoformat(),
        "end": today.isoformat(),
        "timezone": time.strftime("%Z", now),
        "totals": totals,
        "trend": trend,
        "models": models[:MODEL_LIMIT],
        "models_truncated": len(models) > MODEL_LIMIT,
        "rows": rows,
        "page": page,
        "last_page": last_page,
    }


def read_usage(arguments, path=None):
    days, model, page = validate(arguments)
    path = native_database() if path is None else path
    try:
        check_files(path)
        uri = path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0.4)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only = ON")
            db.execute("PRAGMA trusted_schema = OFF")
            deadline = time.monotonic() + 3
            db.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
            db.execute("BEGIN")
            table = db.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'requests'"
            ).fetchone()
            if not table or not table[0].upper().startswith("CREATE TABLE "):
                raise UsageError("unsupported_schema")
            columns = {row[1] for row in db.execute("PRAGMA table_info(requests)")}
            if not REQUIRED_COLUMNS <= columns:
                raise UsageError("unsupported_schema")
            return report(db, columns, days, model, page)
    except FileNotFoundError:
        raise UsageError("missing_database") from None
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 0xFF
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_INTERRUPT):
            raise UsageError("busy") from None
        raise UsageError("unavailable") from None
    except OSError:
        raise UsageError("unavailable") from None
