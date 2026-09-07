"""Clock sanity check against the HTTP Date header of a beeSys response.

Witty Pi 4 Mini keeps its RTC alive on a supercap. When that is dead (camera
1) a power cut freezes the RTC and the next boot runs on yesterday's time:
photos get wrong names and the daily sync is skipped because "already synced
today". Every cycle already talks to beeSys, and its Date header is a free
time reference — the same trick Witty Pi's own net_to_system uses. When the
system clock is off by more than CLOCK_FIX_THRESHOLD_S it is set from the
header and written to the RTC right away.
"""
import subprocess
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from witty_sheduler import ACCEPTABLE_DRIFT_SECONDS, read_times

CLOCK_FIX_THRESHOLD_S = 60


def clock_offset_from_response(response):
    """Seconds to add to the local clock to match the server; None if unknown."""
    if response is None:
        return None
    header = response.headers.get("Date")
    if not header:
        return None
    try:
        server_time = parsedate_to_datetime(header)
    except Exception as e:
        print(f"Unparseable Date header {header!r}: {e}")
        return None
    if server_time.tzinfo is None:
        server_time = server_time.replace(tzinfo=timezone.utc)
    return round((server_time - datetime.now(timezone.utc)).total_seconds(), 1)


def format_offset(offset_s):
    """'+15 h 11 min', '-3 min 20 s', '+48 s' — for logs and the dashboard."""
    sign = "+" if offset_s >= 0 else "-"
    total = int(round(abs(offset_s)))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        hours, minutes = divmod(int(round(total / 60)), 60)
        return f"{sign}{hours} h {minutes} min"
    if minutes:
        return f"{sign}{minutes} min {seconds} s"
    return f"{sign}{seconds} s"


def fix_system_clock(offset_s, wittypi_path):
    """Shift the system clock by offset_s and write it to the Witty Pi RTC.
    Returns (ok, error_message); verified by re-reading both clocks."""
    target = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    try:
        subprocess.run(
            ["date", "-u", "-s", f"@{int(target.timestamp())}"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        return False, f"date -s selhalo: {e}"
    try:
        subprocess.run(
            ["bash", "-c", f"cd {wittypi_path} && . ./utilities.sh >/dev/null 2>&1 && system_to_rtc"],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        return False, f"system_to_rtc selhalo: {e}"

    sys_time, rtc_time = read_times(wittypi_path)
    if sys_time is None or rtc_time is None:
        return False, "nelze ověřit čas RTC"
    drift = abs((sys_time - rtc_time).total_seconds())
    if drift >= ACCEPTABLE_DRIFT_SECONDS:
        return False, f"RTC po zápisu stále mimo o {drift:.0f} s"
    print(f"⏰ Clock set from server (Δ {format_offset(offset_s)}), RTC verified (drift {drift}s).")
    return True, ""
