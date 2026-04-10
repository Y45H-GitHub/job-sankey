#!/usr/bin/env python3
"""
job-sankey — Visualise your job application funnel from Gmail.

Usage:
    python main.py              # Full pipeline: fetch → merge → visualise
    python main.py --fetch      # Fetch emails only (no diagram)
    python main.py --visualize  # Regenerate diagram from existing CSV

Configuration:
    Edit config.yaml to customise search keywords, blocked domains,
    portal queries, manual entries, and diagram appearance.

Prerequisites:
    1. Place your Google OAuth credentials.json in this directory
    2. pip install -r requirements.txt
    3. python main.py
"""

import argparse
import os
import sys

import yaml
import pandas as pd

from job_sankey.auth import get_gmail_service
from job_sankey.fetcher import (
    fetch_inbox_emails,
    fetch_portal_emails,
    fetch_sent_emails,
)
from job_sankey.merger import (
    merge_all_sources,
    process_inbox_emails,
    save_csv,
)
from job_sankey.sankey import generate_sankey
from job_sankey.company import extract_company


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate config.yaml."""
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Copy config.yaml.example and edit it.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def step_fetch(config: dict) -> pd.DataFrame:
    """Fetch emails from all sources and return merged DataFrame."""
    service = get_gmail_service()

    blocked = set(config.get("blocked_domains", []))
    personal = set(config.get("personal_domains", []))
    lookback = config.get("lookback_days", 365)
    ghosted_days = config.get("ghosted_threshold_days", 30)

    all_dfs = []

    # 1. Inbox emails
    print("\n[1/3] Fetching inbox emails...")
    raw = fetch_inbox_emails(
        service,
        config.get("search_keywords", []),
        lookback_days=lookback,
    )
    inbox_df = process_inbox_emails(raw, blocked, personal)
    if not inbox_df.empty:
        all_dfs.append(inbox_df)
    print(f"  → {len(inbox_df)} unique companies from inbox")

    # 2. Portal emails (LinkedIn, Workday, etc.)
    portals = config.get("portals", [])
    if portals:
        print("\n[2/3] Fetching portal confirmations...")
        portal_records = fetch_portal_emails(service, portals, lookback)
        if portal_records:
            portal_df = pd.DataFrame(portal_records)
            portal_df = portal_df.drop_duplicates(subset="company", keep="last")
            all_dfs.append(portal_df)
            print(f"  → {len(portal_df)} unique companies from portals")
    else:
        print("\n[2/3] No portals configured, skipping.")

    # 3. Sent emails
    print("\n[3/3] Fetching sent emails...")
    sent_records = fetch_sent_emails(service, lookback)
    if sent_records:
        # Extract company names and classify
        for rec in sent_records:
            rec["company"] = extract_company(rec, personal)
        sent_df = pd.DataFrame(sent_records)
        sent_df = sent_df.drop_duplicates(subset="company", keep="last")
        all_dfs.append(sent_df)
        print(f"  → {len(sent_df)} unique companies from sent mail")

    # Merge everything
    print("\n[Merge] Combining all sources...")
    manual = config.get("manual_entries", [])
    merged = merge_all_sources(all_dfs, manual, ghosted_days)

    return merged


def step_visualize(config: dict, df: pd.DataFrame):
    """Generate the Sankey diagram."""
    output = config.get("output", {})
    html_path = output.get("html_file", "output/job_search_sankey.html")
    title = config.get("sankey", {}).get("title", "Job Application Funnel")
    colors = config.get("sankey", {}).get("colors")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)

    print("\n[Sankey] Generating diagram...")
    generate_sankey(df, html_path, title=title, node_colors=colors)

    # Print summary
    print("\n" + "=" * 55)
    print("  SUMMARY")
    print("=" * 55)
    for status, count in df["status"].value_counts().items():
        print(f"    {status:.<35s} {count}")
    print(f"\n    {'TOTAL':.<35s} {len(df)}")
    print("=" * 55)
    print(f"\n  Open {html_path} in your browser to view the diagram.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Visualise your job application funnel from Gmail.",
    )
    parser.add_argument(
        "--fetch", action="store_true",
        help="Fetch emails only (don't generate diagram)",
    )
    parser.add_argument(
        "--visualize", action="store_true",
        help="Regenerate diagram from existing CSV (don't fetch)",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    output = config.get("output", {})
    csv_path = output.get("csv_file", "output/applications.csv")
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    if args.visualize:
        # Just regenerate from existing CSV
        if not os.path.exists(csv_path):
            print(f"ERROR: {csv_path} not found. Run without --visualize first.")
            sys.exit(1)
        df = pd.read_csv(csv_path)
        step_visualize(config, df)

    elif args.fetch:
        # Fetch only, save CSV
        df = step_fetch(config)
        save_csv(df, csv_path)
        print(f"\n  Fetched and saved. Run with --visualize to generate diagram.")

    else:
        # Full pipeline
        print("=" * 55)
        print("  job-sankey: Gmail Job Application Tracker")
        print("=" * 55)

        df = step_fetch(config)
        save_csv(df, csv_path)
        step_visualize(config, df)


if __name__ == "__main__":
    main()
