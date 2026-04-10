"""
Email fetching from Gmail.

Three sources:
  1. Inbox — keyword-based search for application-related emails
  2. Portals — high-precision queries for LinkedIn, Workday, etc.
  3. Sent — outgoing emails that look like job applications
"""

import base64
import email.utils
import re
from datetime import datetime, timedelta, timezone

from .company import get_sender_domain


# ── Inbox fetching ──────────────────────────────────────────────────


def fetch_inbox_emails(
    service,
    search_keywords: list[str],
    lookback_days: int = 365,
    max_results: int = 500,
) -> list[dict]:
    """
    Fetch emails matching any of the search keywords.

    Returns a list of records with: subject, sender, sender_domain,
    body_snippet, date.
    """
    since = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y/%m/%d")

    # Build Gmail query: OR all keywords, exclude sent mail
    keyword_clause = " OR ".join(f'"{kw}"' for kw in search_keywords)
    query = f"({keyword_clause}) -in:sent after:{since}"

    print(f"  Searching inbox (since {since})...")

    msg_ids = _list_all_messages(service, query, max_results)
    print(f"  Found {len(msg_ids)} emails. Fetching details...")

    records = []
    for i, msg_id in enumerate(msg_ids):
        if (i + 1) % 100 == 0:
            print(f"    {i + 1}/{len(msg_ids)}...")
        rec = _get_email_record(service, msg_id)
        if rec:
            records.append(rec)

    print(f"  Fetched {len(records)} email records.")
    return records


# ── Portal fetching ─────────────────────────────────────────────────


def fetch_portal_emails(
    service,
    portals: list[dict],
    lookback_days: int = 365,
) -> list[dict]:
    """
    Fetch application confirmations from known job portals.

    Each portal dict should have: label, query, company_extractor,
    and optionally regex.
    """
    from .company import extract_portal_company

    since = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y/%m/%d")

    records = []

    for portal in portals:
        q = f"{portal['query']} after:{since} -in:sent"
        label = portal["label"]
        extractor = portal["company_extractor"]
        regex = portal.get("regex")

        print(f"  Fetching: {label}...", end=" ", flush=True)
        msg_ids = _list_all_messages(service, q, max_results=500)
        print(f"{len(msg_ids)} emails")

        for msg_id in msg_ids:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = msg.get("payload", {}).get("headers", [])
            subject = _header(headers, "Subject")
            sender = _header(headers, "From")
            date_raw = _header(headers, "Date")

            try:
                parsed_date = email.utils.parsedate_to_datetime(date_raw)
            except Exception:
                parsed_date = None

            company = extract_portal_company(
                extractor, subject, sender, regex
            )

            records.append({
                "date": parsed_date,
                "subject": subject,
                "sender": sender,
                "sender_domain": get_sender_domain(sender),
                "company": company,
                "status": "Applied",
                "source": label,
            })

    return records


# ── Sent mail fetching ──────────────────────────────────────────────


def fetch_sent_emails(
    service,
    lookback_days: int = 365,
    max_results: int = 500,
) -> list[dict]:
    """
    Scan sent mail for outgoing job applications (cold emails,
    submissions, etc.).
    """
    since = (
        datetime.now(timezone.utc) - timedelta(days=lookback_days)
    ).strftime("%Y/%m/%d")

    # Common subject patterns for outgoing applications
    keywords = [
        "application for",
        "applying for",
        "resume",
        "job application",
        "internship application",
        "cover letter",
    ]
    keyword_clause = " OR ".join(f'"{kw}"' for kw in keywords)
    query = f"in:sent ({keyword_clause}) after:{since}"

    print(f"  Searching sent mail (since {since})...")
    msg_ids = _list_all_messages(service, query, max_results)
    print(f"  Found {len(msg_ids)} sent emails. Fetching details...")

    records = []
    for msg_id in msg_ids:
        rec = _get_email_record(service, msg_id)
        if rec:
            # For sent mail, the "company" comes from the recipient
            rec["status"] = "Applied"
            rec["source"] = "Sent"
            records.append(rec)

    return records


# ── Internal helpers ────────────────────────────────────────────────


def _list_all_messages(service, query: str, max_results: int) -> list[str]:
    """List all message IDs matching a Gmail query (handles pagination)."""
    ids = []
    page_token = None

    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(max_results, 500),
            pageToken=page_token,
        ).execute()

        for msg in resp.get("messages", []):
            ids.append(msg["id"])
            if len(ids) >= max_results:
                return ids

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return ids


def _get_email_record(service, msg_id: str) -> dict | None:
    """Fetch a single email and return a normalised record."""
    msg = service.users().messages().get(
        userId="me", id=msg_id, format="full",
    ).execute()

    headers = msg.get("payload", {}).get("headers", [])
    subject = _header(headers, "Subject")
    sender = _header(headers, "From")
    date_raw = _header(headers, "Date")

    try:
        parsed_date = email.utils.parsedate_to_datetime(date_raw)
    except Exception:
        parsed_date = None

    body = _extract_body(msg.get("payload", {}))

    return {
        "subject": subject,
        "sender": sender,
        "sender_domain": get_sender_domain(sender),
        "body_snippet": body[:4000],
        "date": parsed_date,
    }


def _header(headers: list[dict], name: str) -> str:
    """Get a specific header value (case-insensitive)."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _extract_body(payload: dict) -> str:
    """Recursively extract the plain-text body from an email payload."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    # Fall back to HTML if no plain text
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", html)

    return ""
