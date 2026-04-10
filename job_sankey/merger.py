"""
Data merging, deduplication, and ghosted detection.

Takes raw email records from multiple sources and produces a clean
DataFrame with one row per company at its highest funnel stage.
"""

import csv
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd

from .classifier import categorise, is_job_related
from .company import extract_company

# Status ranking — higher = further in the funnel.
# Used for deduplication: if a company appears in multiple sources,
# we keep the record with the highest rank.
STATUS_RANK = {
    "Applied": 0,
    "Ghosted": 1,
    "Online Assessment / Test": 2,
    "Interviewing": 3,
    "Rejected": 4,
    "Offer": 5,
}


def process_inbox_emails(
    raw_emails: list[dict],
    blocked_domains: set[str],
    personal_domains: set[str],
) -> pd.DataFrame:
    """
    From raw inbox emails, produce a cleaned DataFrame with one row
    per company at its highest status.
    """
    records = []
    skipped = 0

    for rec in raw_emails:
        if not is_job_related(rec, blocked_domains):
            skipped += 1
            continue

        company = extract_company(rec, personal_domains)
        status = categorise(rec)

        records.append({
            "date": rec.get("date"),
            "subject": rec.get("subject", ""),
            "sender": rec.get("sender", ""),
            "company": company,
            "status": status,
        })

    print(f"  Skipped {skipped} non-job-related emails")

    df = pd.DataFrame(records)
    if df.empty:
        return df

    return _dedup_by_company(df)


def merge_all_sources(
    dataframes: list[pd.DataFrame],
    manual_entries: list[dict] | None = None,
    ghosted_days: int = 30,
) -> pd.DataFrame:
    """
    Merge multiple DataFrames (inbox, portals, sent), add manual
    entries, deduplicate, and apply ghosted detection.
    """
    # Add manual entries
    if manual_entries:
        manual_df = pd.DataFrame(manual_entries)
        dataframes.append(manual_df)

    # Combine
    combined = pd.concat(dataframes, ignore_index=True)
    if combined.empty:
        return combined

    # Normalise for dedup
    combined["_company_key"] = combined["company"].str.strip().str.lower()
    combined["_rank"] = (
        combined["status"].map(STATUS_RANK).fillna(0).astype(int)
    )

    # Keep the row with the highest rank per company
    idx = combined.groupby("_company_key")["_rank"].idxmax()
    merged = combined.loc[idx].copy()
    merged.drop(columns=["_rank", "_company_key"], inplace=True)
    merged.reset_index(drop=True, inplace=True)

    # Apply ghosted detection
    merged = _apply_ghosted(merged, ghosted_days)

    return merged


def save_csv(df: pd.DataFrame, path: str):
    """Save the application data to CSV."""
    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL)
    print(f"  Saved {len(df)} records to {path}")


# ── Internal helpers ────────────────────────────────────────────────


def _dedup_by_company(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the highest-status row per company."""
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df.sort_values("date", inplace=True)

    df["_rank"] = df["status"].map(STATUS_RANK).fillna(0).astype(int)
    idx = df.groupby("company")["_rank"].idxmax()
    best = df.loc[idx].copy()
    best.drop(columns=["_rank"], inplace=True)
    best.reset_index(drop=True, inplace=True)

    return best


def _apply_ghosted(df: pd.DataFrame, threshold_days: int) -> pd.DataFrame:
    """Mark 'Applied' entries older than threshold_days as 'Ghosted'."""
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    now = datetime.now(timezone.utc)

    for i, row in df.iterrows():
        if row["status"] == "Applied" and pd.notna(row["date"]):
            if (now - row["date"]).days > threshold_days:
                df.at[i, "status"] = "Ghosted"

    return df
