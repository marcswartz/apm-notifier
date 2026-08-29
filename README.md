# APM Notifier

APM Notifier watches official company career searches and sends a one-time phone alert when it finds a new:

- Associate Product Manager or Rotational Product Manager role
- Bachelor-eligible Graduate Product Manager role
- Product Manager / Product Management internship or co-op
- Technical or Growth Product Manager internship
- Product Marketing or Product Marketing Manager internship
- Summer marketing internships and junior marketing associate/specialist/coordinator roles at
  Mastercard, Wealthsimple, OpenAI, Lime, Uber, and Stripe

The configuration monitors 36 company and job-network targets, including Google, Meta, Amazon, Microsoft, Apple, TikTok, Electronic Arts, Shopify, Instacart, Patreon, Mastercard, Wealthsimple, OpenAI, Lime, Stripe, Uber, Airbnb, Databricks, Salesforce, Adobe, Spotify, Netflix, and several others. Wellfound is present but disabled because its job pages require an interactive session. A separate US-wide [Summer 2027 community tracker](https://github.com/sndsh404/summer-2027-internships) is monitored as an independent back-check, so matching roles from companies outside that fixed list can also be detected. The original target list was seeded from the [Extern Summer 2027 PM guide](https://www.extern.com/post/product-management-internships-summer-2027-guide).

## What it does

- Checks the configured career searches every five minutes by default.
- Accepts titles mentioning 2027 or no year and rejects explicitly older-year titles.
- Rejects roles explicitly labeled fall, winter, spring, or autumn unless the title also says summer.
- Only alerts for roles with a recognizable US, Canadian, or UK location. Ambiguous `Remote` or missing locations are excluded.
- Checks the official description of graduate PM matches from configured sources and excludes roles whose minimum qualifications explicitly require a master's degree.
- Stores a fingerprint for every match in SQLite, so a role alerts only once.
- Retries temporary HTTP failures and checks sources concurrently.
- Uses headless Chromium only for the few JavaScript-only searches; official JSON/HTML stays on the faster path.
- Rejects empty JavaScript career shells instead of counting them as healthy job feeds.
- Warns only after a source remains unavailable for six hours, then at most weekly during that outage.
- Keeps undelivered roles pending if your phone notification provider is temporarily down.

## Quick start with Docker

Docker is the easiest way to leave the service running on a Mac, home server, or small cloud host.

1. Create your local settings file:

   ```bash
   cp .env.example .env
   ```

2. Configure either Telegram or ntfy in `.env` using one of the sections below.

3. Verify the phone notification:

   ```bash
   docker compose run --rm notifier test-notification
   ```

4. Preview currently matching jobs without notifying or changing state:

   ```bash
   docker compose run --rm notifier check
   ```

5. Start the monitor:

   ```bash
   docker compose up --build -d
   docker compose logs -f notifier
   ```

The SQLite history lives in the persistent `notifier-state` Docker volume. Restarting or rebuilding the container does not cause duplicate alerts.

## Phone alerts

### Option A: Telegram

Telegram is private and gives each alert a tappable application link.

The easiest and safest setup is the interactive command below. It hides the token while you type, discovers your chat ID, stores the credentials in a user-readable-only `.env` file, and sends a test alert:

```bash
python3 -m apm_notifier setup-telegram
```

1. In Telegram, message `@BotFather`, run `/newbot`, and copy the bot token into `TELEGRAM_BOT_TOKEN` in `.env`.
2. Open the new bot and send it `/start`.
3. In a browser, open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and copy the numeric `message.chat.id` into `TELEGRAM_CHAT_ID`.
4. Run the test-notification command above.

### Option B: ntfy

ntfy requires no bot account. Topics on the public ntfy server are reachable by anyone who knows their name, so use a long random topic.

1. Generate a topic name, for example with `openssl rand -hex 20`, and put it in `NTFY_TOPIC` in `.env`.
2. Install the ntfy app on your phone.
3. Subscribe in the app to `https://ntfy.sh/<YOUR_RANDOM_TOPIC>`.
4. Run the test-notification command above.

You can configure both; the service will send through both channels and considers an alert delivered if at least one succeeds.

## Run without Docker

The monitor uses only the Python standard library and needs Python 3.11 or newer.

```bash
cp .env.example .env
python3 -m apm_notifier test-notification
python3 -m apm_notifier check
python3 -m apm_notifier run
```

Your computer must remain awake and connected. For genuine 24/7 coverage, run the same Docker container on an always-on server or cloud container service with persistent storage.

## Free cloud monitoring with GitHub Actions

Cloudflare dispatches the included `.github/workflows/monitor.yml` every five minutes, while GitHub's own schedule provides an hourly backup. The repository may be public, but `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be stored as encrypted repository secrets under **Settings → Secrets and variables → Actions**. Never commit `.env`.

The workflow restores and saves the SQLite notification history through the Actions cache. Its first run establishes a silent baseline, then later runs alert only for newly discovered roles. Public-repository scheduled workflows may be disabled after 60 days without repository activity and should be checked periodically.

## Useful commands

```bash
# One real check: persists results and sends any pending alerts
python3 -m apm_notifier run --once

# Continuous check every two minutes
python3 -m apm_notifier run --interval 120

# Read-only live preview
python3 -m apm_notifier check

# Source health and notification backlog
python3 -m apm_notifier status

# Show all configured companies
python3 -m apm_notifier sources

# Run automated tests
python3 -m unittest discover -s tests -v
```

## Customize the targets

Edit [`config/sources.json`](config/sources.json). Each source needs a stable `id`, display `name`, official `career_url`, and one or more searchable `urls`.

```json
{
  "id": "example",
  "name": "Example Company",
  "career_url": "https://example.com/careers",
  "urls": [
    "https://example.com/careers?query=product%20manager%20intern",
    "https://example.com/careers?query=product%20marketing%20intern"
  ]
}
```

The extractor reads normal job links, JSON job APIs, JSON-LD `JobPosting` data, and embedded application state used by many JavaScript career sites. Career providers change their markup occasionally; the persisted `status` report and throttled phone health warning make those changes visible.

## First-run behavior

`ALERT_ON_FIRST_RUN=true` sends any matching role already live when the monitor first starts. Set it to `false` if you want the first successful check to establish a silent baseline and only alert for later additions.

Deleting the SQLite state intentionally resets deduplication and may alert for every currently matching job again.

## Location filtering

`ALLOWED_COUNTRIES=US,CA,UK` is the default. A posting must identify at least one allowed country, constituent region, province/state, or recognizable city. Multi-location roles qualify when at least one listed location is allowed. Generic `Remote`, worldwide, and missing-location postings are rejected because their eligibility cannot be confirmed.
