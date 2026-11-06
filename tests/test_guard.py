from __future__ import annotations

from graph.guard import allowed_moves, check_move, expected_next


def test_route_override_and_manual_review() -> None:
    state = {"status": "REGISTERED", "hops": 0, "errors": []}
    assert expected_next(state) == "document_fanout"
    assert check_move(state, "routing") == ("document_fanout", True)
    assert "manual_review" in allowed_moves(state)

    state = {"status": "DOCS_PROCESSED", "hops": 0, "flags": {"low_confidence": True}, "errors": []}
    assert expected_next(state) == "manual_review"
    assert check_move(state, "summary") == ("manual_review", True)

    state = {"status": "AWAITING_DOCUMENTS", "hops": 0, "flags": {"missing_types": ["invoice"]}, "errors": []}
    assert expected_next(state) == "await_documents"
    assert check_move(state, "sla_comms") == ("await_documents", True)

    state = {"status": "NEW", "hops": 0, "errors": [{"stage": "intake", "error": "x"}, {"stage": "routing", "error": "y"}]}
    assert expected_next(state) == "manual_review"
    assert "manual_review" in allowed_moves(state)
    assert check_move(state, "intake") == ("manual_review", True)

    assert "manual_review" in allowed_moves({"status": "AWAITING_APPROVAL", "errors": []})
