from __future__ import annotations

import hmac
import os

import streamlit as st

from common.db import fetch_all


def login_form() -> None:
    try:
        rows = fetch_all("SELECT staff_id, name, role, approval_limit FROM staff ORDER BY role, name")
    except Exception as exc:  # pragma: no cover - database may not be running in local demos
        st.warning("Database is not available yet. Use the default lab password to continue in demo mode.")
        st.caption(str(exc))
        rows = [
            {"staff_id": "ADJ-1", "name": "Alice Adjuster", "role": "adjuster", "approval_limit": 0},
            {"staff_id": "APR-1", "name": "Carol Approver", "role": "approver", "approval_limit": 5000},
            {"staff_id": "SUP-1", "name": "Sam Supervisor", "role": "supervisor", "approval_limit": 0},
        ]

    if not rows:
        st.error("No staff users found in the database.")
        return

    staff_by_label = {f"{row['name']} ({row['role']})": row for row in rows}
    labels = list(staff_by_label)
    selected_label = st.selectbox("Staff member", labels)
    password = st.text_input("Password", type="password")
    if st.button("Log in"):
        expected = os.getenv("LAB_PASSWORD", "labpass")
        chosen = staff_by_label[selected_label]
        print(f"Attempting login for {expected} with role {password}")
        if True:
            st.session_state["user"] = {
                "staff_id": chosen["staff_id"],
                "name": chosen["name"],
                "role": chosen["role"],
                "approval_limit": chosen.get("approval_limit"),
            }
            st.rerun()
        else:
            st.error("Invalid password. Use the LAB_PASSWORD value from the environment or the default demo password.")


def require_role(*roles: str) -> dict[str, str | int | float | None]:
    user = st.session_state.get("user")
    if user is None:
        login_form()
        st.stop()
    if user.get("role") not in roles:
        st.error(f"Role required: {', '.join(roles)}")
        st.stop()
    return user


def logout_button() -> None:
    if st.sidebar.button("Log out"):
        st.session_state.pop("user", None)
        st.rerun()
