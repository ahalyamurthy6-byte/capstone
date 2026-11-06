from __future__ import annotations

import ui.bootstrap  # noqa: F401
import streamlit as st

from ui.auth import login_form, logout_button

st.set_page_config(page_title="Claims Ops", page_icon="🧾", layout="wide")

if "user" not in st.session_state:
    st.title("Claims processing")
    st.caption("Sign in with the shared lab password.")
    login_form()
    st.stop()

user = st.session_state["user"]
st.sidebar.title("Claims Ops")
st.sidebar.write(f"Signed in as {user['name']}")
st.sidebar.caption(f"Role: {user['role']}")
logout_button()

st.title("Operations dashboard")
st.markdown("Use the left navigation to submit claims, review cases, approve decisions, or ask the supervisor assistant.")
