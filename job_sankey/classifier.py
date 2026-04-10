"""
Email classification engine.

Determines whether an email is job-related, and if so, which stage
of the application funnel it belongs to.

Classification strategy (subject-first):
  1. Check the SUBJECT LINE for strong signals (high confidence).
  2. Fall back to BODY TEXT only for rejection patterns.
  3. Never classify based on body mentions of "interview" or
     "congratulations" — these appear in boilerplate footers and
     cause massive false positives.
"""

import re


# ── Public API ──────────────────────────────────────────────────────


def is_job_related(
    record: dict,
    blocked_domains: set[str],
) -> bool:
    """
    Pre-filter: return True only if this email is likely about a job
    application. Skips product emails, newsletters, certificates, etc.
    """
    domain = record.get("sender_domain", "")

    # Check domain and all parent domains against the blocklist
    parts = domain.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in blocked_domains:
            return False

    # Check full sender address (for entries like user@specific.com)
    sender = record.get("sender", "")
    for blocked in blocked_domains:
        if "@" in blocked and sender == blocked:
            return False

    # Keyword heuristic: must contain at least one job-related term
    subject = record.get("subject", "").lower()
    body = record.get("body_snippet", "").lower()[:1000]
    text = f"{subject} {body}"

    job_signals = [
        "application", "applying", "applied", "apply",
        "role", "position", "job", "career", "hiring",
        "intern", "engineer", "developer", "software",
        "interview", "assessment", "candidacy", "candidate",
        "offer letter", "offer", "recruit", "resume",
        "shortlist", "reject", "unfortunately", "regret",
        "coding challenge", "coding test", "hackerrank",
        "thank you for", "thanks for applying",
        "received your", "we received",
    ]
    return any(signal in text for signal in job_signals)


def categorise(record: dict) -> str:
    """
    Classify an email into one of:
        Applied | Online Assessment / Test | Interviewing | Rejected | Offer

    "Ghosted" is computed later by the merger (applied > N days with no
    follow-up).

    Approach:
      PASS 1 — subject line only (high confidence)
      PASS 2 — body text (only rejection + offer-letter patterns)
    """
    subject = record.get("subject", "")
    body = record.get("body_snippet", "")

    # ═════════════════════════════════════════════════════════════════
    # PASS 1: SUBJECT LINE (high confidence)
    # ═════════════════════════════════════════════════════════════════

    # ── Offer (very strict: actual offer letters only) ──────────────
    if re.search(r"offer\s*letter", subject, re.I):
        if not re.search(r"(free|opportunity|invitation|apply)", subject, re.I):
            return "Offer"
    if re.search(r"pleased\s+to\s+offer\s+you", subject, re.I):
        return "Offer"
    if re.search(r"(job|employment)\s+offer\b", subject, re.I):
        return "Offer"
    if re.search(r"offer\s+for\s+.{0,30}(role|position)", subject, re.I):
        if not re.search(r"(free|opportunity|invitation|apply)", subject, re.I):
            return "Offer"

    # ── Online Assessment / Test ────────────────────────────────────
    if re.search(
        r"(online|coding|technical)\s+(assessment|test|challenge)", subject, re.I
    ):
        if not re.search(
            r"(certificate|registration|status|confirmed|result)", subject, re.I
        ):
            return "Online Assessment / Test"
    if re.search(
        r"complete\s+(the|this|a|your|an)\s+(assessment|test)", subject, re.I
    ):
        return "Online Assessment / Test"
    if re.search(
        r"invite\w*\s+to\s+(complete|take)\s+.{0,20}(assessment|test)",
        subject, re.I,
    ):
        return "Online Assessment / Test"
    if re.search(
        r"(OA|online\s+assessment)\s*(invitation|invite|link|round)",
        subject, re.I,
    ):
        return "Online Assessment / Test"
    if re.search(r"coding\s+assessment\s+for", subject, re.I):
        return "Online Assessment / Test"

    # ── Interviewing (explicit invitations only) ────────────────────
    if re.search(
        r"interview\s*(invitation|invite|schedule|confirm|round)", subject, re.I
    ):
        return "Interviewing"
    if re.search(
        r"(invitation|invite|schedule|confirm)\s*.{0,15}interview", subject, re.I
    ):
        return "Interviewing"
    if re.search(r"shortlist\w*\s+(for|to|\u2013|-)\s", subject, re.I):
        if not re.search(
            r"(hackathon|competition|contest|challenge|coding)", subject, re.I
        ):
            return "Interviewing"
    if re.search(r"phone\s*screen", subject, re.I):
        return "Interviewing"

    # ── Rejected (in subject) ───────────────────────────────────────
    if re.search(r"unfortunately", subject, re.I):
        return "Rejected"
    if re.search(r"not\s+(be\s+)?mov(e|ing)\s+forward", subject, re.I):
        return "Rejected"
    if re.search(r"position\s+(has\s+been|was)\s+filled", subject, re.I):
        return "Rejected"
    if re.search(r"regret\s+to\s+inform", subject, re.I):
        return "Rejected"

    # ── Applied (in subject) ────────────────────────────────────────
    if re.search(
        r"(thank\s*(you|s))\s+for\s+(applying|your\s+(application|interest))",
        subject, re.I,
    ):
        return "Applied"
    if re.search(
        r"application\s+(received|submitted|confirmed|recorded|update|status)",
        subject, re.I,
    ):
        return "Applied"
    if re.search(r"(received|submitted)\s+(your\s+)?application", subject, re.I):
        return "Applied"
    if re.search(r"you\s+have\s+applied", subject, re.I):
        return "Applied"
    if re.search(r"application\s+(for|to|at|with)\s+", subject, re.I):
        return "Applied"
    if re.search(r"applied\s+to\s+", subject, re.I):
        return "Applied"

    # ═════════════════════════════════════════════════════════════════
    # PASS 2: BODY TEXT (low confidence — rejection signals only)
    # ═════════════════════════════════════════════════════════════════

    if re.search(
        r"unfortunately.{0,50}(not|unable|regret).{0,50}"
        r"(application|position|role|candidacy)",
        body, re.I,
    ):
        return "Rejected"
    if re.search(r"we\s+regret\s+to\s+inform", body, re.I):
        return "Rejected"
    if re.search(
        r"not\s+(be\s+)?mov(e|ing)\s+forward\s+with\s+(your|the)", body, re.I
    ):
        return "Rejected"
    if re.search(r"decided\s+not\s+to\s+(proceed|continue|move)", body, re.I):
        return "Rejected"
    if re.search(r"unable\s+to\s+(offer|extend|proceed)", body, re.I):
        return "Rejected"

    if re.search(
        r"(thank\s*(you|s))\s+for\s+(applying|your\s+(application|interest))",
        body, re.I,
    ):
        return "Applied"
    if re.search(r"(received|submitted)\s+(your\s+)?application", body, re.I):
        return "Applied"

    # Default: passed relevance filter but uncategorised → Applied
    return "Applied"
