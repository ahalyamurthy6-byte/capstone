from __future__ import annotations

from typing import Any

import streamlit as st


def status_badge(status: str) -> None:
    colors = {
        "NEW": "secondary",
        "REGISTERED": "blue",
        "DOCS_PROCESSED": "orange",
        "DOCS_VALIDATED": "green",
        "SUMMARISED": "violet",
        "ROUTED": "blue",
        "AWAITING_DOCUMENTS": "orange",
        "AWAITING_APPROVAL": "orange",
        "MANUAL_REVIEW": "red",
        "APPROVED": "green",
        "REJECTED": "red",
        "MORE_INFO": "yellow",
    }
    st.badge(status or "UNKNOWN", color=colors.get(status, "secondary"))


def flags_badges(flags: dict[str, Any] | None) -> None:
    if not flags:
        st.caption("No flags")
        return
    chips: list[str] = []
    for key, value in flags.items():
        if value in (None, False, [], {}):
            continue
        chips.append(f"{key}")
    if not chips:
        st.caption("No active flags")
        return
    st.markdown(" ".join(f"<span style='padding:2px 8px;border-radius:999px;background:#eef2ff;color:#312e81;font-size:12px'>{item}</span>" for item in chips), unsafe_allow_html=True)


def risk_list(risks: list[dict[str, Any]] | None) -> None:
    if not risks:
        st.caption("No risks")
        return
    for risk in risks:
        clause = risk.get("clause_id") or "-"
        text = risk.get("text") or risk.get("description") or str(risk)
        st.markdown(f"- **{clause}**: {text}")


def render_streamed_text(chunks: list[str], placeholder: Any) -> str:
    text = "".join(chunks)
    placeholder.markdown(text)
    return text
