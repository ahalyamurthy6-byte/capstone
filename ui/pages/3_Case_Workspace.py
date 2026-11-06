from __future__ import annotations

import asyncio
import json

import streamlit as st

from common.db import fetch_all, fetch_one
from graph.runner import graph_session, replay
from ui.auth import require_role

require_role("adjuster", "approver", "supervisor")

st.title("Case workspace")
case_id = st.text_input("Case ID")
if st.button("Load case") and case_id:
    case = fetch_one("SELECT * FROM cases WHERE case_id = %s", (case_id,))
    if case is None:
        st.warning("No case found for that ID.")
        st.stop()

    documents = fetch_all("SELECT * FROM documents WHERE case_id = %s ORDER BY created_at ASC", (case_id,))
    summary = fetch_one("SELECT * FROM summaries WHERE case_id = %s", (case_id,))
    timeline = fetch_all(
        """
        SELECT * FROM audit_with_checkpoint WHERE case_id = %s ORDER BY ts ASC
        """,
        (case_id,),
    )

    tabs = st.tabs(["Case", "Timeline"])
    with tabs[0]:
        st.subheader(f"Case {case_id}")
        st.json(case)

        st.subheader("Documents")
        if not documents:
            st.caption("No documents attached.")
        else:
            for doc in documents:
                st.markdown(f"- **{doc['doc_id']}** ({doc.get('doc_type', 'other')})")
                st.json(doc.get('fields') or {})

        st.subheader("Summary")
        if summary:
            st.json(summary.get("summary") or {})
        else:
            st.caption("No summary recorded yet.")

    with tabs[1]:
        if not timeline:
            st.caption("No activity yet.")
        else:
            st.dataframe(timeline)
            if st.session_state["user"]["role"] == "supervisor":
                checkpoint_id = timeline[-1].get("linked_checkpoint_id")
                if checkpoint_id and st.button("Replay from here"):
                    async def _replay() -> None:
                        async with graph_session() as graph:
                            await replay(graph, case_id, checkpoint_id)
                    try:
                        asyncio.run(_replay())
                        st.success(f"Replay requested from checkpoint {checkpoint_id}.")
                    except Exception as exc:  # pragma: no cover
                        st.warning(f"Replay failed: {exc}")

    with st.expander("Raw JSON"):
        st.code(json.dumps({"case": case, "documents": documents, "summary": summary, "timeline": timeline}, indent=2, default=str))
