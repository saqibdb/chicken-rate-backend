# YouTube price feed

## Server configuration

The importer reads runtime configuration from **Django Admin → Environment variables**. Add these rows there after running migrations. When no admin row exists, the matching process environment variable is used as a fallback:

- `YOUTUBE_API_KEY`: a YouTube Data API v3 key with YouTube Data API v3 enabled. Mark as secret.
- `YOUTUBE_CHANNEL_ID`: optional channel ID. If omitted, the importer uses `YOUTUBE_CHANNEL_HANDLE` (default: `Mianshahzadsaeed786`, matching the Flutter app).
- `YOUTUBE_CHANNEL_HANDLE`: optional YouTube handle to process when no channel ID is set.
- `YOUTUBE_FETCH_COOLDOWN_SECONDS`: minimum delay between manual fetch requests (default `3600`, one hour).
- `DAILY_PRICE_FETCH_TIME`: daily automatic fetch time, `HH:MM` in the server's `Asia/Karachi` timezone. A migration creates this setting with default `08:00`.
- `RAPIDOCR_INTRA_OP_THREADS` and `RAPIDOCR_INTER_OP_THREADS`: ONNX CPU thread counts; both default to `1` to limit CPU contention on small hosts.
- `RAPIDOCR_MODEL_SIZE`: detector and recognizer model size (`tiny`, `small`, or `medium`); defaults to `tiny` to reduce memory use.
- `RAPIDOCR_MAX_SIDE_LEN`: maximum detector image side length; defaults to `640` pixels. The importer does not upscale small thumbnails. Restart the server after changing either OCR setting.
- `CHICKEN_PRICE_MIN_AMOUNT` and `CHICKEN_PRICE_MAX_AMOUNT`: accepted live wholesale price range, defaulting to `5000`–`100000`. Adjust these in Admin if the source's price range changes.

Run `python manage.py migrate` to create the environment variables table. Secret values are masked in the admin list and edit form; leaving a secret's edit field blank preserves its current value. The OCR engine and its ONNX Runtime dependency are installed from `requirements.txt`; no Tesseract executable or `TESSERACT_CMD` setting is needed.

The importer resolves the channel uploads playlist, checks up to 200 recent uploads in the last 30 days, selects the first upload for each date, downloads its thumbnail, and runs RapidOCR with the configured compact model and bounded input size. YouTube API requests retry transient connection and server errors up to three times. It reads the first two OCR lines and accepts one unambiguous price in the configured range, whether OCR returns `16,200`, `16-200`, `16 200`, or `16200`. It also normalizes common `O`/`0` and `I`/`1` OCR confusions and Unicode digits. If multiple distinct plausible prices remain, it skips the video and records the candidates in the fetch logs rather than guessing. When a fetch inserts today's price, the backend sends a push notification with the 40 kg live rate and the app's estimated whole chicken with giblets price per kg. Push delivery results appear in the daily fetch logs and Django Admin → Push notifications. Set `DAILY_PRICE_FETCH_TIME` to `07:50` for the server fetch; the Flutter app keeps its separate local notification scheduled for `08:00`. Run the importer on a schedule (for example, hourly) using the server's scheduler:

```sh
python manage.py fetch_youtube_prices
```

Each video is upserted by YouTube video ID, so repeated runs do not create duplicate price rows. After deploying the schema, run `python manage.py migrate` before enabling the scheduler.

## Mobile API

- `GET /api/v1/prices/current/` returns the newest stored price.
- `GET /api/v1/prices/history/` returns prices from the past 30 days by default. Optional query parameters: `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, and `limit=1..365`.
- `GET /api/v1/prices/fetch/` triggers the thumbnail OCR import and returns `added`, `updated`, `skipped`, `errors`, and `videos_checked` counts plus a `logs` array. Each log entry contains a `step`, `status`, and explanation; video-related entries also include the title, video ID, date, OCR text, or extracted amount. It returns HTTP 429 during the cooldown or while another import is running.
- `GET /api/v1/prices/fetch/today/` starts today's import in the background and returns HTTP 202 with a `call_id` and `status_url`. Poll the returned URL for step logs and the final result. Calls and progress are also saved in Django Admin → Daily price fetch logs.
- `GET /api/v1/prices/fetch/today/<call_id>/` returns the current progress and final result for a fetch started above.
- `GET /api/v1/ocr/diagnostic/?video_id=<11-character-id>` runs one thumbnail through download, RapidOCR initialization, and OCR without inserting a price. It returns a signed `status_url`; poll it to see the last completed stage. Results are also listed in Django Admin → OCR diagnostic logs.
- `POST /api/v1/devices/register-push/` registers an Android installation with its FCM token. JSON body: `device_id`, `fcm_token`, and optional `device_name`, `platform`, `app_version`, `os_version`.
- `GET /api/v1/` is the HTML API reference, generated from the registered API URL patterns.

## Android push notifications

Install `firebase-admin` from `requirements.txt`, then run `python manage.py migrate`. Add either `FIREBASE_SERVICE_ACCOUNT_JSON` (compact service-account JSON; mark the Environment Variable as secret) or `FIREBASE_SERVICE_ACCOUNT_FILE` (server path to a service-account JSON file) in Django Admin → Environment Variables. The Android app must be connected to the same Firebase project and register each device token at `/api/v1/devices/register-push/`. In Django Admin → Push notifications, choose **Send notification**, enter the title and message, and press **Send**. The admin log records counts and errors; a successful FCM submission means FCM accepted the message, not that the device displayed it.

The price endpoints include the date, amount, currency, and source video details. History is ordered newest first. A current price request returns HTTP 404 until the first import has stored data. The all-history fetch endpoint is rate limited to protect the YouTube API quota; repeated calls within the cooldown do not make another YouTube request. The daily scheduler skips Django's runserver autoreloader parent, coordinates runs with a database lease, and retries scheduled work interrupted by a process restart.

Send device metadata as headers on either request:

```http
X-Device-ID: stable-installation-id
X-Device-Name: Pixel 8
X-Platform: Android
X-App-Version: 1.0.0
X-OS-Version: 15
```

Only `X-Device-ID` is required. The backend stores one device row per ID and refreshes its metadata, last-seen time, and request IP on each call. Use an app-generated installation identifier rather than hardware identifiers such as IMEI.
