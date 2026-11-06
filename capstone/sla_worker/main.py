from __future__ import annotations

import argparse
import logging
import os
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage

from apscheduler.schedulers.blocking import BlockingScheduler

from common.audit import write_audit
from common.config import get_settings
from common.db import execute, fetch_all


def _send_email(to_addr: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = "claims-bot@claims.local"
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.send_message(message)


def run_sla_job() -> int:
    rows = fetch_all(
        """
        SELECT t.case_id, t.kind, t.due_at
        FROM sla_timers t
        JOIN cases c ON c.case_id = t.case_id
        WHERE t.breached = false AND t.due_at < NOW()
          AND c.status IN ('AWAITING_APPROVAL', 'AWAITING_DOCUMENTS')
        ORDER BY t.due_at ASC
        """
    )
    count = 0
    for row in rows:
        case_id = str(row["case_id"])
        kind = str(row["kind"])
        due_at = row["due_at"]
        supervisors = fetch_all("SELECT email FROM staff WHERE role = 'supervisor'")
        for supervisor in supervisors:
            email = str(supervisor.get("email") or "").strip()
            if email:
                _send_email(email, f"SLA breach: {case_id} ({kind})", f"Case {case_id} has breached the {kind} SLA. Due at {due_at}.")
        execute("UPDATE sla_timers SET breached = true WHERE case_id = %s AND kind = %s AND due_at = %s", (case_id, kind, due_at))
        write_audit(case_id, "sla-worker", "sla_breach", before=None, after={"kind": kind, "due_at": due_at})
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor claim SLAs")
    parser.add_argument("--once", action="store_true", help="Run the SLA check once and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    scheduler = BlockingScheduler()
    poll_seconds = int(os.getenv("SLA_POLL_SECONDS", "60"))
    scheduler.add_job(run_sla_job, "interval", seconds=poll_seconds)
    if args.once:
        run_sla_job()
        return
    scheduler.start()


if __name__ == "__main__":
    main()
