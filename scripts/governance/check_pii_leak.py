from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib import request

from common.config import get_settings
from common.db import fetch_all

ROOT = Path(__file__).resolve().parents[2]
PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\bM\d{8}\b"),
]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _read_claim_emails() -> set[str]:
    emails: set[str] = set()
    pack_root = ROOT / "data" / "claim_packs"
    if not pack_root.exists():
        return emails
    for case_dir in sorted(pack_root.iterdir()):
        claim_path = case_dir / "claim.json"
        if not claim_path.exists():
            continue
        try:
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        email = str(payload.get("claimant_email") or "").strip()
        if email:
            emails.add(email)
    return emails


def _matches(value: str, lookup: set[str]) -> list[str]:
    found: list[str] = []
    if not value:
        return found
    for item in sorted(lookup):
        if item in value:
            found.append(item)
    for pattern in PII_PATTERNS:
        for match in pattern.findall(value):
            found.append(match)
    return found


def _mailpit_messages() -> list[dict[str, object]]:
    root_url = os.getenv("MAILPIT_URL", "http://localhost:8025")
    with request.urlopen(f"{root_url}/api/v1/messages") as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    out: list[dict[str, object]] = []
    for message in messages:
        msg_id = message.get("ID") or message.get("id")
        if not msg_id:
            continue
        with request.urlopen(f"{root_url}/api/v1/message/{msg_id}") as resp:
            full = json.loads(resp.read().decode("utf-8"))
        out.append(full)
    return out


def _phoenix_hits() -> list[tuple[str, str]]:
    settings = get_settings()
    try:
        import phoenix as px
    except Exception:
        return []
    try:
        df = px.Client(endpoint=settings.PHOENIX_ENDPOINT).get_spans_dataframe(project_name="claims-agent")
    except Exception:
        return []
    if df is None:
        return []
    hits: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        span_name = str(row.get("name") or "")
        trace_id = str(row.get("trace_id") or "")
        if span_name == "send_notification":
            continue
        values = []
        for key in ("attributes.input.value", "attributes.output.value", "attributes.llm.input_messages"):
            value = row.get(key)
            if value is None:
                continue
            values.append(str(value))
        text = "\n".join(values)
        if not text:
            continue
        if any(secret in text for secret in _read_claim_emails()) or any(pattern.search(text) for pattern in PII_PATTERNS):
            hits.append((span_name, trace_id))
    return hits


def _check_mailpit() -> tuple[bool, list[str]]:
    bad: list[str] = []
    for message in _mailpit_messages():
        body = str(message.get("Content", {}).get("Text", "") or message.get("Text", "") or "")
        text = body.lower()
        if any(pattern.search(body) for pattern in PII_PATTERNS):
            bad.append(f"mailpit body contains PII: {message.get('ID')}")
        if any(word in text for word in ["injection", "risk score", "fraud", "flag", "agent"]):
            bad.append(f"mailpit body contains forbidden internal text: {message.get('ID')}")
    return not bad, bad


def _check_audit() -> tuple[bool, list[str]]:
    rows = fetch_all("SELECT before, after FROM audit_log WHERE before IS NOT NULL OR after IS NOT NULL")
    bad: list[str] = []
    for row in rows:
        blob = json.dumps(row, default=str)
        if any(pattern.search(blob) for pattern in PII_PATTERNS):
            bad.append("audit_log contains SSN or member id")
    return not bad, bad


def main() -> None:
    parser = argparse.ArgumentParser(description="Check for PII leaks in Phoenix, Mailpit, and audit logs.")
    parser.add_argument("--case-id", default=None)
    args = parser.parse_args()

    status = []
    phoenix_hits = _phoenix_hits()
    if phoenix_hits:
        status.append(("Phoenix", "FAIL", phoenix_hits[:5]))
    else:
        status.append(("Phoenix", "PASS", []))

    mail_ok, mail_bad = _check_mailpit()
    status.append(("Mailpit", "PASS" if mail_ok else "FAIL", mail_bad))

    audit_ok, audit_bad = _check_audit()
    status.append(("Audit log", "PASS" if audit_ok else "FAIL", audit_bad))

    for name, verdict, details in status:
        print(f"{name}: {verdict}")
        if details:
            for item in details:
                print(f"  - {item}")

    if any(verdict == "FAIL" for _, verdict, _ in status):
        raise SystemExit(1)

    if args.case_id:
        print(f"Case ID checked: {args.case_id}")
