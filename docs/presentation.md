# Presentation outline

## Slide 1 — Problem
- Claims teams handle fragmented document, policy, and approval flows.
- Manual processing is slow, inconsistent, and hard to audit.
- High-value decisions need traceability and guardrails.

## Slide 2 — Solution overview
- AI-driven claims triage and summary generation with human approval gates.
- LangGraph orchestrates specialist agents and pauses for human review.
- Workflow uses MCP servers to separate memory, policy, and document logic.

## Slide 3 — Architecture
- Streamlit UI to LangGraph orchestration to specialist agents.
- MCP tool layer isolates case, policy, document, and workflow actions.
- Postgres, Docling, Ollama, Mailpit, and Phoenix all plug into the same pipeline.

## Slide 4 — MCP design and least privilege
- Each service owns one domain.
- Tool allow-lists prevent unauthorized actions.
- The agent sees only the needed surface area, and human approvals remain explicit.

## Slide 5 — LangGraph orchestration and human-in-the-loop
- Intake, document validation, summary generation, routing, and SLA handling run in sequence.
- The graph pauses for approval or missing documents instead of auto-deciding.
- Checkpoints preserve replayable state for investigation and debugging.

## Slide 6 — Document intelligence
- OCR and field extraction from claim documents with Docling.
- Classification and validation for missing types, mismatches, and injection risks.
- Structured evidence supports summary generation and policy matching.

## Slide 7 — Governance and compliance
- PII masking for claimant data in live tool responses.
- Prompt injection detection and evidence-blocking safeguards.
- Append-only audit logging preserves a complete decision trail.
- SLA timers ensure timely follow-up and communications.

## Slide 8 — Evaluation results and before/after
- Golden scenarios define expected outcomes and routes.
- The evaluation gate checks success, routing, tool behavior, and risk metrics.
- Before/after comparisons show the delta in throughput, quality, and safety.

## Slide 9 — Business value
- Faster case triage and routing.
- Lower manual effort in high-volume document review.
- Better observability for auditors and operations teams.
- Reduced risk from decision leakage or policy mismatches.

## Slide 10 — Limitations and next steps
- Introduce enterprise identity and Keycloak integration.
- Add Presidio-based PII detection and greater redaction depth.
- Secure MCP with OAuth or mTLS in production.
- Extend into straight-through processing for low-risk claims.
