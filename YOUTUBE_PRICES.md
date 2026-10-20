# YouTube price feed

## Server configuration

Set these environment variables on the deployed Django service:

- `YOUTUBE_API_KEY`: a YouTube Data API v3 key with YouTube Data API v3 enabled.
- `YOUTUBE_CHANNEL_ID`: the channel ID whose uploads contain the chicken prices.
- `YOUTUBE_FETCH_COOLDOWN_SECONDS`: minimum delay between manual fetch requests (default `3600`, one hour).

The importer searches the newest 50 videos on that channel and extracts the first price explicitly marked with `PKR`, `Rs`/`Rupees`, or `روپے` from its title or description. Videos without a marked price are skipped. Run it on a schedule (for example, hourly) using the server's scheduler:

```sh
python manage.py fetch_youtube_prices
```

Each video is upserted by YouTube video ID, so repeated runs do not create duplicate price rows. After deploying the schema, run `python manage.py migrate` before enabling the scheduler.

## Mobile API

- `GET /api/v1/prices/current/` returns the newest stored price.
- `GET /api/v1/prices/history/` returns prices from the past 30 days by default. Optional query parameters: `from=YYYY-MM-DD`, `to=YYYY-MM-DD`, and `limit=1..365`.
- `GET /api/v1/prices/fetch/` triggers an import and returns `added`, `updated`, `skipped`, and `videos_checked` counts. It returns HTTP 429 during the cooldown or while another import is running.
- `GET /api/v1/` is the HTML API reference, generated from the registered API URL patterns.

The price endpoints include the date, amount, currency, and source video details. History is ordered newest first. A current price request returns HTTP 404 until the first import has stored data. The fetch endpoint is rate limited to protect the YouTube API quota; repeated calls within the cooldown do not make another YouTube request.

Send device metadata as headers on either request:

```http
X-Device-ID: stable-installation-id
X-Device-Name: Pixel 8
X-Platform: Android
X-App-Version: 1.0.0
X-OS-Version: 15
```

Only `X-Device-ID` is required. The backend stores one device row per ID and refreshes its metadata, last-seen time, and request IP on each call. Use an app-generated installation identifier rather than hardware identifiers such as IMEI.
