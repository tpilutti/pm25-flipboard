#!/usr/bin/env python3
"""
purpleair_to_vestaboard_datetime.py

NOTE: This code was written by Claude (an AI model made by Anthropic) during
an interactive chat session, then tested and deployed by the repository owner.
It is not affiliated with or endorsed by PurpleAir or Vestaboard, and the AQI
it displays is not health advice. See the project README for details.

Reads the latest raw PM2.5 reading from a PurpleAir sensor and publishes it
to a Vestaboard Note flipboard using the Vestaboard Cloud (Read/Write) API.
The board shows the current date/time, the raw PM2.5 concentration (ug/m3),
and its direct AQI-scale equivalent (via the standard EPA breakpoint table,
with no humidity correction applied). This uses just one PurpleAir field
(pm2.5_atm), keeping API point usage low. Note: because no correction is
applied, this AQI number may differ somewhat from the value shown on
PurpleAir's own map, which applies an additional correction formula.

The board is only updated when PM2.5 is at or above THRESHOLD_PM25 (set in
the CONFIG section below). If the reading is below that threshold, the
script logs the reading and skips the Vestaboard update, so future updates
only appear once air quality actually crosses the threshold you care about.
THRESHOLD_PM25 = 12.1 ug/m3 is where AQI crosses from Good (50) into Moderate (51+).

Board output looks like:

    TUE 07/21 14:32
    46.5 UG/M3
    AQI 128

SETUP
-----
1. Install dependency:
       pip install requests --break-system-packages   (or just `pip install requests`)

2. Get a PurpleAir API read key:
   - Email contact@purpleair.com (or use the developer key form linked from
     https://community.purpleair.com/c/data/api/18) to request a key.
   - Find your sensor's index by going to https://map.purpleair.com, clicking
     your sensor, and reading the number after "select=" in the URL.

3. Get a Vestaboard Cloud API token:
   - web.vestaboard.com -> Developer/API tab (or mobile app -> Settings ->
     Advanced Settings) -> Create New Token -> enable "Write" permission.

4. Fill in the three values in the CONFIG section below, either directly or
   (recommended) via environment variables of the same name.

5. Run it once to test:
       python3 purpleair_to_vestaboard_datetime.py

6. Schedule it to run on whatever interval you want (PurpleAir sensors
   update roughly every 2 minutes, but every 10-15 minutes is plenty for a
   flipboard, and keeps PurpleAir API point usage low):
   - macOS/Linux: add a cron entry, e.g. every 10 minutes:
         */10 * * * * /usr/bin/python3 /path/to/purpleair_to_vestaboard_datetime.py >> /tmp/aq_vestaboard.log 2>&1
   - Windows: use Task Scheduler to run the script on a repeating trigger.
   - Raspberry Pi: same as macOS/Linux via cron, or run as a systemd timer.
"""

import os
import sys
from datetime import datetime
import requests

# ----------------------------- CONFIG ------------------------------------
# Prefer setting these as environment variables rather than hardcoding them:
#   export PURPLEAIR_API_KEY="xxxx"
#   export PURPLEAIR_SENSOR_INDEX="12345"
#   export VESTABOARD_API_TOKEN="xxxx"
PURPLEAIR_API_KEY = os.environ.get("PURPLEAIR_API_KEY", "YOUR_PURPLEAIR_API_KEY")
PURPLEAIR_SENSOR_INDEX = os.environ.get("PURPLEAIR_SENSOR_INDEX", "YOUR_SENSOR_INDEX")
VESTABOARD_API_TOKEN = os.environ.get("VESTABOARD_API_TOKEN", "YOUR_VESTABOARD_TOKEN")

# Only update the board if PM2.5 is at or above this value (ug/m3). Set to 0
# to always update. 12.1 ug/m3 is the EPA breakpoint where AQI crosses from
# "Good" (AQI 50) into "Moderate" (AQI 51+).
THRESHOLD_PM25 = 12.1
# ---------------------------------------------------------------------------


def fetch_pm25(sensor_index: str, api_key: str) -> float:
    """Fetch the latest raw pm2.5 reading for a sensor."""
    url = f"https://api.purpleair.com/v1/sensors/{sensor_index}"
    params = {"fields": "pm2.5_atm"}
    headers = {"X-API-Key": api_key}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()["sensor"]["pm2.5_atm"]


# Standard EPA breakpoints: (Clow, Chigh, Ilow, Ihigh)
# US EPA table for converting PM2.5 (ug/m3) to the 0-500 AQI scale. It is applied
# here to the raw sensor value; the PurpleAir map applies an extra correction
# first, so its AQI can differ from the one this script shows.
AQI_BREAKPOINTS = [
    (0.0, 12.0, 0, 50),
    (12.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 150.4, 151, 200),
    (150.5, 250.4, 201, 300),
    (250.5, 350.4, 301, 400),
    (350.5, 500.4, 401, 500),
]


def pm25_to_aqi(pm25: float) -> int:
    pm25 = max(0.0, min(pm25, 500.4))
    for c_low, c_high, i_low, i_high in AQI_BREAKPOINTS:
        if c_low <= pm25 <= c_high:
            return round(((i_high - i_low) / (c_high - c_low)) * (pm25 - c_low) + i_low)
    return 500


def build_message(pm25: float) -> str:
    # Vestaboard Note is 15 characters wide x 3 rows.
    aqi = pm25_to_aqi(pm25)
    line1 = datetime.now().strftime("%a %m/%d %H:%M").upper()  # e.g. TUE 07/21 14:32
    line2 = f"{pm25:.1f} UG/M3"
    line3 = f"AQI {aqi}"
    return f"{line1}\n{line2}\n{line3}"


def send_to_vestaboard(text: str, token: str) -> None:
    resp = requests.post(
        "https://cloud.vestaboard.com/",
        headers={"X-Vestaboard-Token": token, "Content-Type": "application/json"},
        json={"text": text},
        timeout=15,
    )
    resp.raise_for_status()
    print("Vestaboard response:", resp.json())


def main() -> int:
    missing = [
        name
        for name, val in [
            ("PURPLEAIR_API_KEY", PURPLEAIR_API_KEY),
            ("PURPLEAIR_SENSOR_INDEX", PURPLEAIR_SENSOR_INDEX),
            ("VESTABOARD_API_TOKEN", VESTABOARD_API_TOKEN),
        ]
        if not val or val.startswith("YOUR_")
    ]
    if missing:
        print(f"Please set the following before running: {', '.join(missing)}", file=sys.stderr)
        return 1

    pm25 = fetch_pm25(PURPLEAIR_SENSOR_INDEX, PURPLEAIR_API_KEY)
    aqi = pm25_to_aqi(pm25)

    if pm25 < THRESHOLD_PM25:
        print(f"PM2.5: {pm25:.1f} ug/m3 (AQI {aqi}) — below threshold ({THRESHOLD_PM25} ug/m3), skipping board update")
        return 0

    message = build_message(pm25)

    print(f"PM2.5: {pm25:.1f} ug/m3  AQI: {aqi}")
    print("Sending message:\n" + message)

    send_to_vestaboard(message, VESTABOARD_API_TOKEN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
