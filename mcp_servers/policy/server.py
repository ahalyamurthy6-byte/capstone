from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any

from mcp.server.fastmcp import FastMCP

from common.db import fetch_all, fetch_one
from common.models import CoverageResult, Policy, ToolError, WordingHit
from common.rag import search_wording
from common.tracing import init_tracing

mcp = FastMCP(
    "policy-mcp",
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT") or os.getenv("POLICY_MCP_PORT") or os.getenv("POLICY_PORT") or "8002"),
)


def _tool_error(error: str, hint: str | None = None) -> ToolError:
    return ToolError(error=error, hint=hint)


def _resolve_clause(query: str, product: str | None) -> str | None:
    hits = search_wording(query, product=product, k=1)
    if not hits:
        return None
    return hits[0].clause_id


@mcp.tool()
def get_policy(policy_number: str) -> Policy | ToolError:
    row = fetch_one("SELECT * FROM policies WHERE policy_number = %s", (policy_number,))
    if row is None:
        return _tool_error(f"Unknown policy_number: {policy_number}", "Use a policy that exists in the PostgreSQL policies table.")
    return Policy.model_validate(row)


@mcp.tool()
def check_coverage(policy_number: str, incident_date: date, amount: float, claim_type: str) -> CoverageResult | ToolError:
    row = fetch_one("SELECT * FROM policies WHERE policy_number = %s", (policy_number,))
    if row is None:
        return _tool_error(f"Unknown policy_number: {policy_number}", "Use a policy that exists in the PostgreSQL policies table.")

    policy = Policy.model_validate(row)
    product = policy.product or ""
    reasons: list[str] = []
    clause_ids: list[str] = []

    if policy.start_date is not None and policy.end_date is not None:
        if not (policy.start_date <= incident_date <= policy.end_date):
            reasons.append("Policy not active on incident date")
            clause = _resolve_clause("policy period", product)
            if clause:
                clause_ids.append(clause)

    if policy.sum_insured is not None and Decimal(str(amount)) > policy.sum_insured:
        reasons.append("Claim amount exceeds sum insured")
        clause = _resolve_clause("sum insured limit", product)
        if clause:
            clause_ids.append(clause)

    exclusions = {str(item).strip().lower() for item in (policy.exclusions or [])}
    normalized = claim_type.strip().lower().replace("-", "_").replace(" ", "_")
    mapped = {
        "cosmetic": "cosmetic procedures",
        "pre_existing": "pre-existing conditions",
        "preexisting": "pre-existing conditions",
    }
    if normalized in mapped and mapped[normalized].lower() in {str(item).strip().lower() for item in exclusions}:
        reasons.append(f"Claim type is excluded: {mapped[normalized]}")
        clause = _resolve_clause(mapped[normalized], product)
        if clause:
            clause_ids.append(clause)
    elif normalized in mapped and normalized in {str(item).strip().lower() for item in exclusions}:
        reasons.append(f"Claim type is excluded: {mapped[normalized]}")
        clause = _resolve_clause(mapped[normalized], product)
        if clause:
            clause_ids.append(clause)

    return CoverageResult(
        covered=not reasons,
        reasons=reasons,
        clause_ids=list(dict.fromkeys(clause_ids)),
    )


@mcp.tool()
def search_policy_wording(query: str, product: str | None = None, k: int = 4) -> list[WordingHit]:
    return search_wording(query=query, product=product, k=k)


@mcp.resource("policy://{policy_number}")
def read_policy_resource(policy_number: str) -> str:
    policy = get_policy(policy_number)
    if isinstance(policy, ToolError):
        return json.dumps(policy.model_dump(mode="json"), default=str)
    return json.dumps(policy.model_dump(mode="json"), default=str, indent=2)


@mcp.resource("policy-wording://{product}")
def read_policy_wording(product: str) -> str:
    rows = fetch_all(
        "SELECT clause_id, title, text FROM policy_wording_chunks WHERE product = %s ORDER BY clause_id ASC",
        (product,),
    )
    if not rows:
        return ""
    chunks = [f"## {row['clause_id']} {row['title']}\n{row['text']}" for row in rows]
    return "\n\n".join(chunks)


if __name__ == "__main__":
    init_tracing("policy-mcp")
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
