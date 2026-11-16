# Code walkthrough

This explains what the two scripts in `code/` do and why, separately from the inline comments.

> The Python code was written by Claude (Anthropic's AI model) in chat sessions and then tested by the repository owner. See the [README](../README.md#how-this-was-made).

## The two scripts

| Script | Purpose | Row 1 | Threshold |
|---|---|---|---|
| `purpleair_to_vestaboard_datetime.py` | The script to schedule | Date and time | `12.1` µg/m³ |
| `purpleair_to_vestaboard_ping.py` | End-to-end test | A fixed label (`SENSOR_LABEL`) | `0` (always updates) |

They share the same structure and differ only in `build_message()` (row 1), the `THRESHOLD_PM25` value, and the docstring. The rest of this document applies to both.

## What happens on each run

Each run is a one-shot process with no memory between runs: **fetch, decide, maybe send, exit.**

1. Check that all three credentials are filled in.
2. Ask PurpleAir for the latest PM2.5 reading.
3. Convert it to AQI.
4. If the reading is below `THRESHOLD_PM25`, print it and stop. Otherwise build a 3-line message and send it to the Vestaboard.

## The board output

```
TUE 07/21 14:32
46.5 UG/M3
AQI 128
```

A Vestaboard Note is 15 characters wide and 3 rows tall. Every line is built to fit that width.

## Walkthrough

### 1. Configuration

| Variable | Meaning |
|---|---|
| `PURPLEAIR_API_KEY` | PurpleAir read key |
| `PURPLEAIR_SENSOR_INDEX` | Numeric ID of the sensor to read (yours, or any public sensor) |
| `VESTABOARD_API_TOKEN` | Vestaboard Cloud API token (write) |
| `THRESHOLD_PM25` | Minimum PM2.5 (µg/m³) that triggers a board update |
| `SENSOR_LABEL` (ping script only) | Text for row 1 |

Each credential uses `os.environ.get("NAME", "fallback")`. If an environment variable with that name exists, its value wins. Otherwise the script uses the fallback string. The shipped fallbacks are `YOUR_...` placeholders. You can set environment variables, or type real values into the fallbacks of a local copy that you never commit.

### 2. `fetch_pm25()`

Sends one HTTP GET to `https://api.purpleair.com/v1/sensors/{sensor_index}` with the key in the `X-API-Key` header, and asks for exactly one field, `pm2.5_atm` (the raw PM2.5 concentration in µg/m³). PurpleAir charges points per field, so one field keeps each call cheap. `raise_for_status()` turns any HTTP error into an exception.

### 3. `pm25_to_aqi()`

The US EPA defines AQI as a piecewise linear function of concentration. Each row of `AQI_BREAKPOINTS` is `(conc_low, conc_high, aqi_low, aqi_high)`. For example, `(35.5, 55.4, 101, 150)` says that 35.5 to 55.4 µg/m³ maps linearly onto AQI 101 to 150. The function finds the matching row and interpolates, clamping the input to 0 to 500.4.

**Nuance:** this is applied to the *raw* value. PurpleAir's map applies a correction first, so the map's AQI can differ from this one. A sample check: 15.9 µg/m³ gives AQI 59, and 46.5 µg/m³ gives AQI 128.

### 4. `build_message()`

Builds three lines joined by `\n`, which the Vestaboard API treats as row breaks:

- **Row 1 (datetime script):** `datetime.now().strftime("%a %m/%d %H:%M").upper()` gives something like `TUE 07/21 14:32`: abbreviated weekday, month/day, 24-hour time, uppercased to match the board. That is exactly 15 characters. It uses the **local clock of the machine running the script**, so a Raspberry Pi needs its time zone set.
- **Row 2:** the PM2.5 value to one decimal place, followed by `UG/M3`.
- **Row 3:** `AQI` and the integer AQI.

### 5. `send_to_vestaboard()`

Sends one HTTP POST to `https://cloud.vestaboard.com/` with `{"text": "..."}` as JSON and the token in the `X-Vestaboard-Token` header. The Vestaboard service converts plain text into the board's character codes.

### 6. `main()`

1. Builds the list of credentials that are **empty or still a `YOUR_...` placeholder**. If any are, it prints which ones to `stderr` and returns `1`.
2. Calls `fetch_pm25()` and `pm25_to_aqi()`.
3. If `pm25 < THRESHOLD_PM25`, it logs the reading and returns `0`. Skipping an update is a normal outcome, not an error, so the exit code is 0.
4. Otherwise it builds the message, prints it, and sends it.

The return value becomes the process exit code (`raise SystemExit(main())`).

## Choices made

- **One API field.** Lower point cost, but no humidity correction.
- **Raw µg/m³ shown next to AQI**, so the difference between the two scales is visible.
- **The date and time are generated only when an update is sent.** During stretches of clean air the board keeps showing its last message, and the time on it does not advance.
- **Credentials live in the script file or the environment.** There is no config file. This is simple, but it means you must keep your edited copy out of version control.

## Known limitations

- No error handling beyond raising on HTTP errors.
- The AQI is uncorrected and can disagree with the PurpleAir map.
- No retries, and no handling of a missing `pm2.5_atm` field in the response.
- Not health advice. See the README disclaimers.
