from __future__ import annotations

import json

import streamlit as st

from common.db import fetch_all, fetch_one
from ui.auth import require_role

require_role("adjuster", "approver", "supervisor")

st.title("Ask supervisor")
case_id = st.text_input("Case ID")
question = st.text_area("Question")

if st.button("Send to supervisor assistant") and case_id:
    case = fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,))
    documents = fetch_all("SELECT * FROM documents WHERE case_id = %s ORDER BY created_at ASC", (case_id,))
    summary = fetch_one("SELECT * FROM summaries WHERE case_id = %s", (case_id,))

    if case is None:
        st.warning("No case found for that ID.")
        st.stop()

    context = {
        "case": case,
        "documents": documents,
        "summary": summary.get("summary") if summary else None,
        "question": question or "Summarize the case and list the main risks.",
    }

    st.subheader("Context snapshot")
    st.json(context)
    st.caption("This page is designed to support a supervisor assistant using the claim case data and document records as the trusted context source.")
