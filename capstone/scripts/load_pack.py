from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from common.config import get_settings
from common.db import execute

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "data" / "claim_packs"


def _pack_id_for_scenario(scenario: str) -> str:
    for candidate in sorted(p.name for p in PACK_ROOT.iterdir() if p.is_dir()):
        claim_path = PACK_ROOT / candidate / "claim.json"
        if claim_path.exists():
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
            if str(payload.get("scenario", "")).lower() == scenario.lower():
                return candidate
    raise FileNotFoundError(f"No pack found for scenario: {scenario}")


def _doc_type_for_file(filename: str) -> str:
    name = filename.lower()
    if "claim_form" in name:
        return "claim_form"
    if "invoice" in name:
        return "invoice"
    if "medical" in name:
        return "medical_report"
    if "police" in name:
        return "police_report"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a claim pack into the local database for document tests.")
    parser.add_argument("pack_id", nargs="?", help="Pack ID, e.g. PACK-0001")
    parser.add_argument("--scenario", help="Load the first pack matching this scenario")
    args = parser.parse_args()

    pack_id = args.pack_id or (_pack_id_for_scenario(args.scenario) if args.scenario else None)
    if pack_id is None:
        raise SystemExit("Provide a pack_id or --scenario <name>")
    if args.scenario and args.pack_id:
        raise SystemExit("Use either pack_id or --scenario, not both")

    claim_path = PACK_ROOT / pack_id / "claim.json"
    if not claim_path.exists():
        raise SystemExit(f"Pack not found: {pack_id}")

    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    case_id = "TEST-" + pack_id
    docs_dir = Path(get_settings().DOCS_DIR) / case_id
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    execute(
        """
        INSERT INTO cases (
            case_id, policy_number, claimant_name, claimant_email, incident_date,
            claim_type, amount, description, status, duplicate_of, created_at, updated_at
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
            case_id,
            payload.get("policy_number"),
            payload.get("claimant_name"),
            payload.get("claimant_email"),
            payload.get("incident_date"),
            payload.get("claim_type"),
            float(payload.get("amount") or 0.0),
            payload.get("description"),
            "REGISTERED",
            None,
        ),
    )

    execute("DELETE FROM documents WHERE case_id = %s", (case_id,))

    doc_ids: list[str] = []
    for file_name in payload.get("documents", []):
        src = PACK_ROOT / pack_id / file_name
        if not src.exists():
            continue
        target = docs_dir / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

        doc_id = f"{case_id}-{Path(file_name).stem}"
        doc_type = _doc_type_for_file(file_name)
        execute(
            """
            INSERT INTO documents (doc_id, case_id, file_path, doc_type, fields, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                case_id = EXCLUDED.case_id,
                file_path = EXCLUDED.file_path,
                doc_type = EXCLUDED.doc_type,
                fields = EXCLUDED.fields,
                created_at = NOW()
            """,
            (doc_id, case_id, str(target), doc_type, "{}"),
        )
        doc_ids.append(doc_id)

    print(f"case_id={case_id}")
    print(f"doc_ids={json.dumps(doc_ids)}")


if __name__ == "__main__":
    main()
