# 10-minute demo script

## 1) Everything healthy

```bash
docker compose ps
```

Expect all services to be `Up` or `healthy`, especially Postgres and the four MCP services.

Fallback CLI:

```bash
docker compose logs --tail=50 postgres case-mcp policy-mcp documents-mcp workflow-mcp ui
```

## 2) Clean claim flow

Open the Streamlit UI at http://localhost:8501 and submit a clean claim with `ADJ-1` as the case reference. Watch the workflow progress through the graph, then open the case summary and clause citations.

Fallback CLI:

```bash
python -m graph.run_cli --case-id ADJ-1
```

Log in as the approver before the SLA limit and approve the claim from the UI. Confirm the letter in Mailpit at http://localhost:8025.

Fallback CLI:

```bash
python -m scripts.run_agent --case-id ADJ-1 --approve
```

## 3) Missing documents flow

Submit a claim that triggers a missing-document pause. In the UI, show the claimant email in Mailpit and the `await_documents` state. Upload the invoice and confirm the case resumes.

Fallback CLI:

```bash
python -m graph.run_cli --case-id MISSING-1
```

## 4) Prompt injection check

Upload a document containing a prompt injection attempt. In the UI, confirm the injection badge and summary risk. Show that nothing was auto-approved and an audit trail preserves the event.

Fallback CLI:

```bash
python -m graph.run_cli --case-id INJECT-1
```

## 5) Approval limit guard

Submit a high-value case with `APR-1` and show that the approver is blocked by the approval limit. This demonstrates the least-privilege routing rule.

Fallback CLI:

```bash
python -m graph.run_cli --case-id APR-1
```

## 6) Replay a checkpoint

Navigate to the Graph tab in the UI and choose a checkpoint. Replay the state to show the same case can be resumed without losing route history.

Fallback CLI:

```bash
python -m graph.run_cli --case-id ADJ-1 --replay
```

## 7) Phoenix trace

Open http://localhost:6006 and show one traced run from the UI or the graph. Confirm the trace includes the AI operations and the MCP calls.

## 8) Evaluation page and gate

Open the Evaluation page in the UI and show the latest metric pass/fail summary. Then run the gate locally:

```bash
python -m evals.test_gate
```

This demonstrates the basic scoring, threshold checks, and the observation loop.
