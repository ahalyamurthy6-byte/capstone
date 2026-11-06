from __future__ import annotations

import json
import sys
from pathlib import Path

from pgvector import Vector

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.db import get_conn
from common.llm import get_embeddings


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def upsert_customers() -> None:
    with (DATA_DIR / "policies.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    with get_conn() as conn:
        cur = conn.cursor()
        for customer in payload["customers"]:
            cur.execute(
                """
                INSERT INTO customers (customer_id, name, email, dob)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (customer_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    dob = EXCLUDED.dob
                """,
                (
                    customer["customer_id"],
                    customer["name"],
                    customer["email"],
                    customer["dob"],
                ),
            )


def upsert_policies() -> None:
    with (DATA_DIR / "policies.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    with get_conn() as conn:
        cur = conn.cursor()
        for policy in payload["policies"]:
            cur.execute(
                """
                INSERT INTO policies (policy_number, customer_id, product, start_date, end_date, sum_insured, exclusions)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (policy_number) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    product = EXCLUDED.product,
                    start_date = EXCLUDED.start_date,
                    end_date = EXCLUDED.end_date,
                    sum_insured = EXCLUDED.sum_insured,
                    exclusions = EXCLUDED.exclusions
                """,
                (
                    policy["policy_number"],
                    policy["customer_id"],
                    policy["product"],
                    policy["start_date"],
                    policy["end_date"],
                    policy["sum_insured"],
                    json.dumps(policy.get("exclusions", [])),
                ),
            )


def upsert_staff() -> None:
    with (DATA_DIR / "staff.json").open("r", encoding="utf-8") as fh:
        staff = json.load(fh)
    with get_conn() as conn:
        cur = conn.cursor()
        for person in staff:
            cur.execute(
                """
                INSERT INTO staff (staff_id, name, email, role, approval_limit)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (staff_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    email = EXCLUDED.email,
                    role = EXCLUDED.role,
                    approval_limit = EXCLUDED.approval_limit
                """,
                (
                    person["staff_id"],
                    person["name"],
                    person["email"],
                    person["role"],
                    person["approval_limit"],
                ),
            )


def insert_prior_case() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO cases (
                case_id, policy_number, claimant_name, claimant_email,
                incident_date, claim_type, amount, description, status,
                duplicate_of, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (case_id) DO UPDATE SET
                policy_number = EXCLUDED.policy_number,
                claimant_name = EXCLUDED.claimant_name,
                claimant_email = EXCLUDED.claimant_email,
                incident_date = EXCLUDED.incident_date,
                claim_type = EXCLUDED.claim_type,
                amount = EXCLUDED.amount,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                duplicate_of = EXCLUDED.duplicate_of,
                updated_at = NOW()
            """,
            (
                "CLM-PRIOR-0001",
                "POL-1006",
                "Emily Davis",
                "emily.davis@example.com",
                "2026-03-12",
                "hospitalisation",
                2800.00,
                "Prior approved case used for duplicate detection.",
                "APPROVED",
                None,
            ),
        )


def chunk_wording_files() -> None:
    wording_dir = DATA_DIR / "policy_wording"
    embeddings = get_embeddings()
    files = sorted(wording_dir.glob("*.md"))

    for wording_file in files:
        content = wording_file.read_text(encoding="utf-8")
        product = wording_file.stem
        chunks: list[dict[str, str]] = []
        current: dict[str, str] | None = None

        for line in content.splitlines():
            if line.startswith("## "):
                if current is not None:
                    chunks.append(current)
                heading = line[3:].strip()
                if " " in heading:
                    clause_id, title = heading.split(" ", 1)
                else:
                    clause_id, title = heading, ""
                current = {"clause_id": clause_id.strip(), "title": title.strip(), "body": [f"## {clause_id.strip()} {title.strip()}".strip()]}
            elif current is not None and line.strip():
                current["body"].append(line.strip())

        if current is not None:
            chunks.append(current)

        for index in range(0, len(chunks), 20):
            batch = chunks[index : index + 20]
            vectors = embeddings.embed_documents([
                "\n".join(chunk["body"]) for chunk in batch
            ])
            with get_conn() as conn:
                cur = conn.cursor()
                for chunk, vector in zip(batch, vectors):
                    clause_text = "\n".join(chunk["body"])
                    cur.execute(
                        """
                        INSERT INTO policy_wording_chunks (product, clause_id, title, text, embedding)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (product, clause_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            text = EXCLUDED.text,
                            embedding = EXCLUDED.embedding
                        """,
                        (
                            product,
                            chunk["clause_id"],
                            chunk["title"],
                            clause_text,
                            Vector(vector),
                        ),
                    )


def count_table(table_name: str) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
        row = cur.fetchone()
        return int(row["count"]) if row is not None else 0


def main() -> None:
    upsert_customers()
    upsert_policies()
    upsert_staff()
    insert_prior_case()
    chunk_wording_files()

    for table_name in ["customers", "policies", "staff", "cases", "policy_wording_chunks"]:
        print(f"{table_name}: {count_table(table_name)}")


if __name__ == "__main__":
    main()
