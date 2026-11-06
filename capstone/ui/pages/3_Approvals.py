from __future__ import annotations

import streamlit as st

from common.db import execute, fetch_all, fetch_one
from ui.auth import require_role

require_role("approver", "supervisor")

st.title("Approvals")

try:
    cases = fetch_all(
        """
        SELECT c.case_id, c.claimant_name, c.amount, c.status, a.approver_id
        FROM cases c
        LEFT JOIN assignments a ON a.case_id = c.case_id
        WHERE c.status IN ('AWAITING_APPROVAL', 'MANUAL_REVIEW', 'MORE_INFO')
        ORDER BY c.created_at DESC
        """
    )
except Exception as exc:  # pragma: no cover - local demo mode
    st.warning("Database unavailable; there are no pending approvals to review in demo mode.")
    st.caption(str(exc))
    st.stop()

if not cases:
    st.info("No pending decisions.")
    st.stop()

selected = st.selectbox("Case", [row["case_id"] for row in cases])
case = fetch_one("SELECT * FROM cases WHERE case_id = %s", (selected,))
if case:
    st.subheader(f"{case['case_id']} - {case['claimant_name']}")
    col1, col2 = st.columns(2)
    col1.metric("Amount", f"${case['amount']:.2f}")
    col2.metric("Status", case["status"])
    st.json({k: case[k] for k in ["policy_number", "claim_type", "incident_date", "description"] if k in case})

    with st.form("approval_decision"):
        action = st.radio("Decision", ["approved", "rejected", "more_info"], horizontal=True)
        rationale = st.text_area("Rationale")
        submitted = st.form_submit_button("Submit decision")

    if submitted:
        execute(
            """
            INSERT INTO approvals (case_id, approver_id, status, rationale, decided_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (selected, st.session_state["user"]["staff_id"], action, rationale or ""),
        )
        execute("UPDATE cases SET status = %s, updated_at = NOW() WHERE case_id = %s", ("APPROVED" if action == "approved" else "REJECTED" if action == "rejected" else "MORE_INFO", selected))
        st.success(f"Decision recorded for {selected}: {action}")
