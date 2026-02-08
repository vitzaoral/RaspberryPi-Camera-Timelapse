# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Low-power Raspberry Pi timelapse camera system. Captures images on a schedule, optionally detects humans (YOLOv4-tiny), overlays metadata (timestamp, temperature, camera number), uploads to Cloudinary, and reports status to Blynk. Power-managed via WittyPi 4 Mini for battery-efficient operation in remote locations.

Target hardware: Raspberry Pi Zero 2 WH + Arducam 8MP IMX219 + WittyPi 4 Mini.

## Architecture

All application code lives in `camera/`. The system runs as a systemd service (`camera.service`) that executes `camera/main.py` on boot.

**Execution flow** (`main.py`):
1. Load `config.json` → check internet → sync RTC time via WittyPi
2. Fetch remote settings from Blynk (working hours, sleep interval, OTA flag)
3. If outside working hours → schedule next WittyPi wakeup → shutdown via GPIO pin 4
4. If OTA update flagged → `git pull` and restart via `os.execv()`
5. Capture photo with `rpicam-still` → optional YOLOv4-tiny person detection
6. Overlay text (PIL) → upload to Cloudinary → update Blynk dashboard
7. If person detected → restart script immediately (continuous monitoring at 1-min intervals)
8. Otherwise → schedule WittyPi deep sleep → shutdown via GPIO pin 4

**Module responsibilities:**
- `main.py` — Orchestration, Blynk settings retrieval, flow control
- `camera.py` — Photo capture (`rpicam-still` subprocess), text overlay with PIL
- `blynk.py` — Blynk REST API (get/set pin values, batch updates)
- `cloudinary.py` — Image upload to Cloudinary via REST API
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
