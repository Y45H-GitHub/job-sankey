"""
Sankey diagram generation using Plotly.

Produces an interactive HTML file showing the job application funnel:
    Total Applied → OA / Test → Interview → Offer
"""

from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go


def generate_sankey(
    df: pd.DataFrame,
    output_path: str,
    title: str = "Job Application Funnel",
    node_colors: dict[str, str] | None = None,
):
    """Build and save an interactive Plotly Sankey diagram."""
    transitions = _compute_transitions(df)
    if not transitions:
        print("  No transitions to plot.")
        return

    # Build Plotly structures
    labels = []
    label_index = {}

    def _idx(label: str) -> int:
        if label not in label_index:
            label_index[label] = len(labels)
            labels.append(label)
        return label_index[label]

    sources, targets, values = [], [], []
    for src, tgt, val in transitions:
        sources.append(_idx(src))
        targets.append(_idx(tgt))
        values.append(val)

    # Node colours
    default_colors = {
        "Total Applied":      "rgba(31, 119, 180, 0.85)",
        "OA / Test":          "rgba(255, 187, 40, 0.85)",
        "Interview":          "rgba(44, 160, 101, 0.85)",
        "Rejected / Ghosted": "rgba(214, 39, 40, 0.85)",
        "Offer":              "rgba(23, 190, 207, 0.85)",
        "No Offer Yet":       "rgba(255, 152, 48, 0.85)",
        "Awaiting OA Result": "rgba(148, 103, 189, 0.85)",
    }
    colors = node_colors or default_colors
    nc = [colors.get(l, "rgba(127,127,127,0.6)") for l in labels]

    # Link colours (lighter version of target node)
    lc = [nc[t].replace("0.85", "0.35") for t in targets]

    total_applied = len(df)

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=25,
            thickness=30,
            label=[f"{l}  ({v})" if l == "Total Applied" else l
                   for l, v in zip(labels, [total_applied] + [0] * len(labels))],
            color=nc,
            hovertemplate="%{label}<extra></extra>",
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=lc,
            hovertemplate="%{source.label} → %{target.label}: %{value}<extra></extra>",
        ),
    ))

    # Fix label: Total Applied should show its count
    fig.data[0].node.label = [
        f"{l}  ({total_applied})" if l == "Total Applied" else l
        for l in labels
    ]

    fig.update_layout(
        title_text=f"{title}  ({total_applied} applications)",
        font=dict(size=14, family="Inter, sans-serif"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=520,
        margin=dict(l=40, r=40, t=60, b=30),
    )

    fig.write_html(output_path, include_plotlyjs="cdn")
    print(f"  Sankey diagram saved to {output_path}")

    # Also print SankeyMATIC format
    print()
    border = "-" * 55
    print(f"  {border}")
    print("  SankeyMATIC format (paste at https://sankeymatic.com)")
    print(f"  {border}")
    for src, tgt, val in transitions:
        print(f"  {src} [{val}] {tgt}")
    print(f"  {border}")


# ── Internal ────────────────────────────────────────────────────────


def _compute_transitions(df: pd.DataFrame) -> list[tuple[str, str, int]]:
    """
    Compute Sankey transition counts as a sequential funnel.

    The funnel is:
        Applied → OA/Test → Interview → Offer

    Uses the 'stages_reached' column (if present) to determine which
    intermediate stages a company passed through. Otherwise infers
    from the final status.
    """
    counts = defaultdict(int)
    for status in df["status"]:
        counts[status] += 1

    applied_only = counts.get("Applied", 0)
    ghosted = counts.get("Ghosted", 0)
    oa = counts.get("Online Assessment / Test", 0)
    interviewing = counts.get("Interviewing", 0)
    rejected = counts.get("Rejected", 0)
    offer = counts.get("Offer", 0)

    # Transition counters
    applied_to_rejected_ghosted = rejected + ghosted
    applied_to_awaiting = applied_only
    applied_to_oa = 0
    applied_to_interview_direct = 0
    oa_to_interview = 0
    oa_to_rejected = 0
    oa_awaiting = 0
    interview_to_offer = offer
    interview_to_no_offer = 0

    if "stages_reached" in df.columns:
        for _, row in df.iterrows():
            stages = str(row.get("stages_reached", "")).lower()
            status = row["status"]
            has_oa = "oa" in stages or "test" in stages or "assessment" in stages
            has_interview = "interview" in stages

            if has_oa:
                applied_to_oa += 1
                if has_interview:
                    oa_to_interview += 1
                    if status not in ("Offer",):
                        interview_to_no_offer += 1
                else:
                    if status == "Online Assessment / Test":
                        oa_awaiting += 1
                    else:
                        oa_to_rejected += 1
            elif has_interview:
                applied_to_interview_direct += 1
                if status != "Offer":
                    interview_to_no_offer += 1
            # else: stays in applied/ghosted/rejected (already counted)

        # Reconcile: subtract stage-tracked records from the flat counts
        applied_to_rejected_ghosted = (
            (rejected + ghosted) - oa_to_rejected - interview_to_no_offer
        )
        applied_to_rejected_ghosted = max(0, applied_to_rejected_ghosted)
    else:
        applied_to_oa = oa
        oa_awaiting = oa
        applied_to_interview_direct = interviewing + offer
        interview_to_no_offer = interviewing

    # Build transition list (merge Awaiting into Rejected/Ghosted)
    transitions = []
    no_progress = applied_to_rejected_ghosted + applied_to_awaiting
    if no_progress > 0:
        transitions.append(("Total Applied", "Rejected / Ghosted", no_progress))
    if applied_to_oa > 0:
        transitions.append(("Total Applied", "OA / Test", applied_to_oa))
    if applied_to_interview_direct > 0:
        transitions.append(("Total Applied", "Interview", applied_to_interview_direct))

    if oa_to_interview > 0:
        transitions.append(("OA / Test", "Interview", oa_to_interview))
    if oa_to_rejected > 0:
        transitions.append(("OA / Test", "Rejected / Ghosted", oa_to_rejected))
    if oa_awaiting > 0:
        transitions.append(("OA / Test", "Awaiting OA Result", oa_awaiting))

    if interview_to_offer > 0:
        transitions.append(("Interview", "Offer", interview_to_offer))
    if interview_to_no_offer > 0:
        transitions.append(("Interview", "No Offer Yet", interview_to_no_offer))

    return transitions
