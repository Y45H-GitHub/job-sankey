# job-sankey

**Visualise your job application funnel as a Sankey diagram using Gmail.**

Turn hundreds of job application emails scattered across your inbox into a clean, interactive funnel diagram showing exactly where your applications stand.

```
Total Applied (524)
├── Rejected / Ghosted (511)
├── OA / Test (8)
│   ├── Interview (5) → Offer (3)
│   │                 → No Offer Yet (2)
│   └── Awaiting OA Result (3)
```

## Features

- **Automatic email parsing** — Scans your Gmail for application confirmations, rejections, OA invitations, interview schedules, and offer letters
- **Portal support** — Captures LinkedIn Easy Apply, Workday, Greenhouse, and Lever confirmations
- **Smart classification** — Subject-first approach avoids false positives from boilerplate email body text
- **Multi-stage funnel** — Tracks the real journey: Applied → OA → Interview → Offer
- **Fully configurable** — Edit `config.yaml` to customise keywords, blocked domains, and more
- **Manual entries** — Add applications not tracked via email

## Quick Start

### 1. Google Cloud Setup

You need a Google Cloud project with the Gmail API enabled:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library**
4. Search for **Gmail API** and click **Enable**
5. Go to **APIs & Services → Credentials**
6. Click **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: anything (e.g., "job-sankey")
7. Download the JSON file and save it as `credentials.json` in this directory
8. Go to **APIs & Services → OAuth consent screen**
   - Choose **External** user type
   - Fill in the required fields (app name, email)
   - Add scope: `https://www.googleapis.com/auth/gmail.readonly`
   - Under **Test users**, add your own Gmail address

> **Note:** While your app is in "Testing" mode, only the Gmail accounts listed as test users can authenticate. This is normal — you don't need to publish the app.

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Edit `config.yaml` to customise:

- **`search_keywords`** — Gmail search terms for finding application emails
- **`blocked_domains`** — Domains to skip (newsletters, product emails, etc.)
- **`portals`** — Portal-specific queries (LinkedIn, Workday, etc.)
- **`manual_entries`** — Applications not tracked via email
- **`lookback_days`** — How far back to search (default: 365)
- **`ghosted_threshold_days`** — Days before marking as "Ghosted" (default: 30)

### 4. Run

```bash
# Full pipeline: fetch emails → merge → generate diagram
python main.py

# Fetch emails only (saves CSV, no diagram)
python main.py --fetch

# Regenerate diagram from existing CSV (no fetching)
python main.py --visualize
```

On first run, a browser window opens for Google OAuth consent. Subsequent runs reuse the saved token.

### 5. View

Open `output/job_search_sankey.html` in your browser.

## Project Structure

```
job-sankey/
├── main.py                 # CLI entry point
├── config.yaml             # All user-editable settings
├── requirements.txt        # Python dependencies
├── credentials.json        # Your Google OAuth credentials (not committed)
├── job_sankey/             # Core package
│   ├── auth.py             # Gmail OAuth authentication
│   ├── fetcher.py          # Email fetching (inbox + portals + sent)
│   ├── classifier.py       # Email categorisation engine
│   ├── company.py          # Company name extraction
│   ├── merger.py           # Data dedup, ghosted detection, merge
│   └── sankey.py           # Sankey diagram generation
└── output/                 # Generated files (gitignored)
    ├── applications.csv    # Final deduplicated data
    └── job_search_sankey.html
```

## How It Works

1. **Fetch** — Searches Gmail using configurable keywords and portal-specific queries
2. **Filter** — Drops non-job emails using domain blocklist + keyword heuristics
3. **Classify** — Subject-first regex engine categorises each email:
   - `Offer` — "offer letter", "pleased to offer you"
   - `Online Assessment / Test` — "coding assessment", "complete your test"
   - `Interviewing` — "interview invitation", "interview schedule"
   - `Rejected` — "unfortunately", "not moving forward"
   - `Applied` — "thank you for applying", "application received"
4. **Deduplicate** — Keeps the highest-stage status per company
5. **Ghosted detection** — Marks old `Applied` entries as `Ghosted`
6. **Visualise** — Generates an interactive Plotly Sankey diagram

## Customisation

### Adding blocked domains

If you see noise from a specific domain, add it to `blocked_domains` in `config.yaml`:

```yaml
blocked_domains:
  - example-newsletter.com
  - spam-company.io
```

### Adding manual entries

For applications not tracked via email:

```yaml
manual_entries:
  - company: "Acme Corp"
    status: "Offer"
    stages_reached: "applied,oa,interview,offer"
  - company: "Widgets Inc"
    status: "Interviewing"
    stages_reached: "applied,interview"
```

### Adding new portal queries

To support a new job portal:

```yaml
portals:
  - label: "My Portal"
    query: 'from:noreply@myportal.com subject:"application"'
    company_extractor: subject_regex
    regex: 'application to (.+?)(?:\s*$|\s*[-|])'
```

### Modifying classification rules

Edit `job_sankey/classifier.py`. The patterns are well-documented — search for the category you want to modify (e.g., "Offer", "Interviewing") and adjust the regex.

## License

MIT
