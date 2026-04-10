"""Company name extraction from email sender and subject."""

import re
import email.utils


def extract_company(record: dict, personal_domains: set[str]) -> str:
    """
    Determine the company name from the sender's domain or subject line.

    Priority:
      1. Sender domain (most reliable)
      2. Subject line patterns (fallback)
    """
    domain = record.get("sender_domain", "")
    company = _from_domain(domain, personal_domains)
    if not company:
        company = _from_subject(record.get("subject", ""))
    return company


def get_sender_domain(sender: str) -> str:
    """Extract the domain from a raw 'From' header value."""
    _, addr = email.utils.parseaddr(sender)
    return addr.split("@")[-1].lower() if "@" in addr else ""


def _from_domain(domain: str, personal_domains: set[str]) -> str:
    """Extract company name from the email domain."""
    if not domain or domain in personal_domains:
        return ""

    # Strip common prefixes: no-reply.company.com → company.com
    parts = domain.split(".")
    if len(parts) > 2:
        prefixes = {
            "mail", "email", "emails", "notify", "notifications",
            "noreply", "no-reply", "careers", "jobs", "talent",
            "hr", "info", "support", "updates", "calendar",
            "recruiting", "donotreply",
        }
        while len(parts) > 2 and parts[0] in prefixes:
            parts = parts[1:]

    # Use the first meaningful part as the company name
    company = parts[0] if parts else ""
    return company.title() if company else ""


def _from_subject(subject: str) -> str:
    """Try to extract a company name from the email subject line."""
    patterns = [
        re.compile(
            r"(?:applying|application|applied)\s+(?:to|at|for|with)\s+"
            r"([A-Z][\w\s&.'-]+?)(?:\s*[-–|!.,]|\s+for\s|\s*$)",
            re.I,
        ),
        re.compile(
            r"(?:at|from|with)\s+([A-Z][\w\s&.'-]{2,25}?)(?:\s*[-–|!.,]|\s*$)",
            re.I,
        ),
    ]
    for pat in patterns:
        m = pat.search(subject)
        if m:
            return m.group(1).strip().title()
    return "Unknown"


# ── Portal-specific extractors ──────────────────────────────────────


def extract_portal_company(
    extractor: str,
    subject: str,
    sender: str,
    regex: str | None = None,
) -> str:
    """
    Extract company name using a portal-specific strategy.

    Extractor types:
        linkedin_sent  — "your application was sent to <Company>"
        workday_sender — company from <company>@myworkday.com
        subject_regex  — custom regex on the subject line
        static:<Name>  — always returns <Name>
    """
    if extractor == "linkedin_sent":
        m = re.search(r"was sent to (.+)$", subject, re.I)
        return m.group(1).strip().title() if m else "Unknown"

    if extractor == "workday_sender":
        _, addr = email.utils.parseaddr(sender)
        local = addr.split("@")[0] if "@" in addr else ""
        # Remove workday boilerplate from local part
        clean = re.sub(
            r"(workday[\.\-]?(do[\.\-]?not[\.\-]?reply|support|noreply)?)",
            "", local, flags=re.I,
        )
        clean = clean.strip("-. ")
        if clean:
            return clean.title()
        return "Unknown"

    if extractor == "subject_regex" and regex:
        m = re.search(regex, subject, re.I)
        return m.group(1).strip().title() if m else "Unknown"

    if extractor.startswith("static:"):
        return extractor.split(":", 1)[1]

    return "Unknown"
