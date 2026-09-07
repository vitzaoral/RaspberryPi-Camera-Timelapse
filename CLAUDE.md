# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Low-power Raspberry Pi timelapse camera system. Captures images on a schedule, optionally detects humans (YOLOv4-tiny), overlays metadata (timestamp, temperature, camera number), uploads to Cloudinary, and reports status to Blynk. Power-managed via WittyPi 4 Mini for battery-efficient operation in remote locations.

Target hardware: Raspberry Pi Zero 2 WH + Arducam 8MP IMX219 + WittyPi 4 Mini.

## Architecture

All application code lives in `camera/`. The system runs as a systemd service (`camera.service`) that executes `camera/main.py` on boot.

**Execution flow** (`main.py`, v3.6+):
1. Load `config.json` → **capture photo first** with `rpicam-still` (one retry after 5 s — exit 255 right after an OTA restart; + optional YOLOv4-tiny person detection) — nothing network-related can block the picture
2. Wait for internet (with wlan0 re-kicks) → disable Wi-Fi power save and lower wlan0 MTU to 800 for the cycle (`wifi_mtu` in config.json overrides; big frames die on the marginal hotspot link — telemetry showed ReadTimeouts with working pings and TCP connects) → put public resolvers (8.8.8.8, 1.1.1.1, short timeouts) first in `/etc/resolv.conf` for the cycle (hotspot DNS forwarder is the prime suspect for stalled requests)
3. GET beeSys outdoor temperature; its HTTP `Date` header is the clock reference — if the system clock is off by > 60 s, set it and write the WittyPi RTC (`clock.py`; fixes frozen RTC after a power cut on a dead supercap, no manual force-sync needed)
4. Read all cycle settings from Blynk in ONE multi-pin request with retries (working hours, sleep interval, OTA flag, last sync, force sync); window + interval fall back to `settings_cache.json` on the SD card when Blynk is unreachable (status `OK [cache]` / `OK [bez Blynku]`) — the cycle never aborts without a photo just because Blynk is down
5. RTC sync via WittyPi (skipped when the clock was just fixed, or when Blynk is down but the clock verified OK)
6. If OTA update flagged → `git reset --hard origin/main` and restart via `os.execv()`
7. Outside working hours → still upload this photo, but sleep until the next window start
8. Overlay text (PIL; timestamp = capture moment on the corrected clock) → upload to Cloudinary (3 attempts; status `upload_fail` when all fail) → update Blynk dashboard → POST cycle telemetry to beeSys; the log's `error` carries network diagnostics (DNS note, which request failed and how: `ConnectTimeout`, `ConnectionError/resolve`, …)
9. If person detected → restart script immediately (continuous monitoring at 1-min intervals)
10. Otherwise → schedule WittyPi deep sleep → shutdown via GPIO pin 4

Any unhandled exception inside the cycle is reported as status `crash` (with traceback) and the camera still schedules its wake-up and powers off — it must never stay on draining the battery.

**Module responsibilities:**
- `main.py` — Orchestration, Blynk settings retrieval, flow control
- `camera.py` — Photo capture (`rpicam-still` subprocess), text overlay with PIL
- `blynk.py` — Blynk REST API (multi-pin get with retries, set pin values, batch updates) + beeSys public GET; all through the keep-alive session in `net.py`
- `clock.py` — clock check against the beeSys `Date` header, system + RTC fix
- `settings_cache.py` — last known working window / interval on SD (fallback when Blynk is down)
- `cloudinary.py` — Image upload to Cloudinary via REST API
- `telemetry.py` — Per-cycle phase timings POSTed to beeSys (`/api/public/cameras/cycle-log`, auth via Blynk token); offline cycles queue to `pending_telemetry.json` on SD and flush next online cycle
- `human_detection.py` — YOLOv4-tiny person detection via OpenCV DNN (conditionally imported)
- `witty_sheduler.py` — RTC time sync and deep sleep scheduling via WittyPi shell scripts
- `utils.py` — Text generation, WiFi/IP info, time interval parsing, GPIO shutdown, file cleanup
- `update_repository.py` — OTA updates via git fetch/pull with automatic script restart

**Key design patterns:**
- Shutdown is performed by setting GPIO pin 4, which triggers WittyPi daemon to cut power
- Person detection is conditionally imported based on `use_person_detection` config flag
- WittyPi scheduling uses retry logic (up to 5 attempts) with verification
- Time sync checks against last sync date stored in Blynk to avoid redundant syncs
- All errors are reported to Blynk error pin for remote monitoring

## Configuration

`camera/config.json` contains all runtime configuration: camera number, feature flags (`use_person_detection`, `use_tuning_file`), Cloudinary credentials, Blynk auth tokens and pin mappings, WittyPi path, and repo path. This file is not committed with real credentials.

`camera/configs.txt` has reference configurations for multiple camera deployments.

## Dependencies

No `requirements.txt` exists. Python dependencies (installed via apt on the Pi):
- `python3-pil` (Pillow) — image processing
- `python3-opencv` (cv2) — person detection with YOLOv4-tiny
- `python3-requests` — HTTP for Blynk and Cloudinary APIs

System dependencies: `rpicam-apps` (camera capture), WittyPi 4 Mini software (power management).

## Deployment

The application is deployed to `/home/timelapse/` on the Raspberry Pi and runs as a systemd service. Key commands on the Pi:

```bash
sudo systemctl enable camera.service    # enable at boot
sudo systemctl start camera.service     # start
sudo systemctl status camera.service    # check status
sudo journalctl -u camera.service       # view logs
```

OTA updates are triggered remotely via Blynk pin v20, which causes the script to `git pull` and restart.

## YOLO Model Files

`camera/yolo/` contains YOLOv4-tiny config and weights for person detection (COCO class 0). The weights file is ~23MB.

## Camera Tuning

`camera/imx219_160d.json` is a tuning file for the Arducam IMX219 wide-angle lens to correct purple color tint. Enabled via `use_tuning_file` in config.
