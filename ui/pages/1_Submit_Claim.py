from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from common.ids import new_case_id
from common.db import execute, fetch_all
from ui.auth import require_role

require_role("adjuster", "supervisor")

st.title("Submit a claim")

root = Path(__file__).resolve().parents[2]
examples_path = root / "data" / "golden.jsonl"
examples: list[dict] = []
if examples_path.exists():
    with examples_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    examples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

sample_names = [item.get("pack_id", "Custom") for item in examples]
selected_pack = st.selectbox("Fast-fill template", ["Custom", *sample_names])

claim = {
    "policy_number": "POL-1001",
    "claimant_name": "",
    "claimant_email": "",
    "incident_date": "",
    "claim_type": "hospitalisation",
    "amount": 0,
    "description": "",
}

if selected_pack != "Custom":
    for item in examples:
        if item.get("pack_id") == selected_pack:
            claim = {
                "policy_number": str(item.get("policy_number", claim["policy_number"])),
                "claimant_name": str(item.get("claimant_name", "")),
                "claimant_email": str(item.get("claimant_email", "")),
                "incident_date": str(item.get("incident_date", "")),
                "claim_type": str(item.get("claim_type", claim["claim_type"])),
                "amount": float(item.get("amount", 0) or 0),
                "description": str(item.get("description", "")),
            }
            break

with st.form("claim_form"):
    claim["claimant_name"] = st.text_input("Claimant name", value=claim["claimant_name"])
    claim["claimant_email"] = st.text_input("Claimant email", value=claim["claimant_email"])
    claim["policy_number"] = st.text_input("Policy number", value=claim["policy_number"])
    claim["incident_date"] = st.date_input("Incident date", value=None if not claim["incident_date"] else __import__("datetime").date.fromisoformat(claim["incident_date"]))
    claim["claim_type"] = st.selectbox("Claim type", ["hospitalisation", "outpatient", "dental", "other"], index=["hospitalisation", "outpatient", "dental", "other"].index(claim["claim_type"]))
    claim["amount"] = st.number_input("Claim amount", min_value=0.0, value=float(claim["amount"]))
    claim["description"] = st.text_area("Description", value=claim["description"], height=150)
    uploaded = st.file_uploader("Upload supporting documents", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

    submitted = st.form_submit_button("Create case")

if submitted:
    if not claim["claimant_name"] or not claim["claimant_email"]:
        st.error("Claimant name and email are required.")
        st.stop()

    case_id = new_case_id()
    try:
        execute(
            """
            INSERT INTO cases (case_id, policy_number, claimant_name, claimant_email, incident_date, claim_type, amount, description, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'NEW')
            ON CONFLICT (case_id) DO NOTHING
            """,
            (
                case_id,
                claim["policy_number"],
                claim["claimant_name"],
                claim["claimant_email"],
                str(claim["incident_date"]),
                claim["claim_type"],
                float(claim["amount"]),
                claim["description"],
            ),
        )
        upload_summary = []
        for index, file in enumerate(uploaded or [], 1):
            file_name = f"{case_id}-{index}-{file.name}"
            target = root / "data" / "uploads" / case_id
            target.mkdir(parents=True, exist_ok=True)
            (target / file.name).write_bytes(file.read())
            upload_summary.append(f"{file.name} saved under {target / file.name}")

        st.success(f"Case created: {case_id}")
        st.code(json.dumps({"case_id": case_id, "claim": claim, "uploads": upload_summary}, indent=2, default=str))
    except Exception as exc:  # pragma: no cover - demo resilience
        st.warning("Database connection unavailable; showing a local preview instead.")
       
        st.code(json.dumps({"case_id": case_id, "claim": claim, "uploads": [f.name for f in uploaded or []]}, indent=2, default=str))
        st.caption(f"DB error: {exc}")

st.caption("Templates are loaded from the sample golden dataset for quick claim intake.")
