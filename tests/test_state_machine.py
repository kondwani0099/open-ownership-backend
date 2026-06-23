"""
Unit tests for the state machine — covers ALL legal and illegal transitions.

These tests exercise the core business logic without any database or HTTP layer.
"""

import pytest
from app.services.state_machine import (
    can_transition,
    transition_requires_comment,
    validate_transition,
    resolve_action,
    IllegalTransitionError,
    MissingCommentError,
    ACTION_TO_STATUS,
)
from app.models.application import ApplicationInDB, LEGAL_TRANSITIONS


# ── Helper: minimal application fixture ────────────────────────────────────────

def make_app(status: str, applicant_id: str = "alice@test.com") -> ApplicationInDB:
    return ApplicationInDB(
        id="fake-id",
        title="Test App",
        category="General",
        description="",
        amount=100.0,
        applicant_id=applicant_id,
        status=status,
    )


# ── can_transition (syntactic) ─────────────────────────────────────────────────

class TestCanTransition:
    """Legal transitions as defined in the state-machine diagram."""

    def test_draft_to_submitted(self):
        assert can_transition("DRAFT", "SUBMITTED") is True

    def test_draft_cannot_skip_to_approved(self):
        assert can_transition("DRAFT", "APPROVED") is False

    def test_draft_cannot_go_to_under_review(self):
        assert can_transition("DRAFT", "UNDER_REVIEW") is False

    def test_draft_cannot_be_rejected(self):
        assert can_transition("DRAFT", "REJECTED") is False

    def test_submitted_to_under_review(self):
        assert can_transition("SUBMITTED", "UNDER_REVIEW") is True

    def test_submitted_to_returned_for_changes(self):
        assert can_transition("SUBMITTED", "RETURNED_FOR_CHANGES") is True

    def test_submitted_cannot_be_approved_directly(self):
        assert can_transition("SUBMITTED", "APPROVED") is False

    def test_submitted_cannot_go_back_to_draft(self):
        assert can_transition("SUBMITTED", "DRAFT") is False

    def test_under_review_to_approved(self):
        assert can_transition("UNDER_REVIEW", "APPROVED") is True

    def test_under_review_to_rejected(self):
        assert can_transition("UNDER_REVIEW", "REJECTED") is True

    def test_under_review_cannot_go_to_draft(self):
        assert can_transition("UNDER_REVIEW", "DRAFT") is False

    def test_returned_for_changes_to_draft(self):
        assert can_transition("RETURNED_FOR_CHANGES", "DRAFT") is True

    def test_returned_for_changes_cannot_be_submitted_directly(self):
        assert can_transition("RETURNED_FOR_CHANGES", "SUBMITTED") is False

    def test_terminal_approved_has_no_exits(self):
        assert can_transition("APPROVED", "DRAFT") is False
        assert can_transition("APPROVED", "SUBMITTED") is False
        assert can_transition("APPROVED", "REJECTED") is False
        # All possible targets should be illegal
        for target in ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETURNED_FOR_CHANGES"]:
            assert can_transition("APPROVED", target) is False, f"APPROVED → {target} should be illegal"

    def test_terminal_rejected_has_no_exits(self):
        assert can_transition("REJECTED", "DRAFT") is False
        assert can_transition("REJECTED", "APPROVED") is False
        for target in ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETURNED_FOR_CHANGES"]:
            assert can_transition("REJECTED", target) is False, f"REJECTED → {target} should be illegal"


# ── comment-required rules ─────────────────────────────────────────────────────

class TestCommentRequired:
    def test_reject_requires_comment(self):
        assert transition_requires_comment("UNDER_REVIEW", "REJECTED") is True

    def test_return_requires_comment(self):
        assert transition_requires_comment("SUBMITTED", "RETURNED_FOR_CHANGES") is True

    def test_approve_does_not_require_comment(self):
        assert transition_requires_comment("UNDER_REVIEW", "APPROVED") is False

    def test_submit_does_not_require_comment(self):
        assert transition_requires_comment("DRAFT", "SUBMITTED") is False

    def test_review_does_not_require_comment(self):
        assert transition_requires_comment("SUBMITTED", "UNDER_REVIEW") is False


# ── validate_transition (full validation) ──────────────────────────────────────

class TestValidateTransition:
    def test_legal_transition_passes(self):
        validate_transition(make_app("DRAFT"), "SUBMITTED")

    def test_illegal_transition_raises(self):
        with pytest.raises(IllegalTransitionError) as exc:
            validate_transition(make_app("DRAFT"), "APPROVED")
        assert "DRAFT" in str(exc.value)
        assert "APPROVED" in str(exc.value)

    def test_reject_without_comment_raises(self):
        with pytest.raises(MissingCommentError):
            validate_transition(make_app("UNDER_REVIEW"), "REJECTED", comment="")

    def test_reject_with_comment_passes(self):
        validate_transition(make_app("UNDER_REVIEW"), "REJECTED", comment="Not good enough")

    def test_return_without_comment_raises(self):
        with pytest.raises(MissingCommentError):
            validate_transition(make_app("SUBMITTED"), "RETURNED_FOR_CHANGES", comment="  ")

    def test_return_with_comment_passes(self):
        validate_transition(make_app("SUBMITTED"), "RETURNED_FOR_CHANGES", comment="Please revise")

    def test_terminal_status_cannot_transition(self):
        with pytest.raises(IllegalTransitionError):
            validate_transition(make_app("APPROVED"), "DRAFT")
        with pytest.raises(IllegalTransitionError):
            validate_transition(make_app("REJECTED"), "SUBMITTED")


# ── resolve_action ─────────────────────────────────────────────────────────────

class TestResolveAction:
    def test_submit_maps_to_submitted(self):
        assert resolve_action("submit") == "SUBMITTED"

    def test_review_maps_to_under_review(self):
        assert resolve_action("review") == "UNDER_REVIEW"

    def test_approve_maps_to_approved(self):
        assert resolve_action("approve") == "APPROVED"

    def test_reject_maps_to_rejected(self):
        assert resolve_action("reject") == "REJECTED"

    def test_return_maps_to_returned_for_changes(self):
        assert resolve_action("return") == "RETURNED_FOR_CHANGES"

    def test_unknown_action_raises(self):
        with pytest.raises(ValueError):
            resolve_action("nonsense")


# ── Full workflow sequence (integration-style unit test) ───────────────────────

class TestFullWorkflow:
    """Walk through the entire happy path and verify each step."""

    def test_happy_path_draft_to_approved(self):
        """DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED"""
        app = make_app("DRAFT")

        validate_transition(app, "SUBMITTED")
        app.status = "SUBMITTED"

        validate_transition(app, "UNDER_REVIEW")
        app.status = "UNDER_REVIEW"

        validate_transition(app, "APPROVED")
        app.status = "APPROVED"

        # Terminal — no more moves allowed
        with pytest.raises(IllegalTransitionError):
            validate_transition(app, "DRAFT")

    def test_return_round_trip(self):
        """DRAFT → SUBMITTED → RETURNED_FOR_CHANGES → DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED"""
        app = make_app("DRAFT")

        validate_transition(app, "SUBMITTED")
        app.status = "SUBMITTED"

        validate_transition(app, "RETURNED_FOR_CHANGES", comment="Fix the amount")
        app.status = "RETURNED_FOR_CHANGES"

        # Back to draft
        validate_transition(app, "DRAFT")
        app.status = "DRAFT"

        # Resubmit
        validate_transition(app, "SUBMITTED")
        app.status = "SUBMITTED"

        validate_transition(app, "UNDER_REVIEW")
        app.status = "UNDER_REVIEW"

        validate_transition(app, "APPROVED")
        app.status = "APPROVED"

    def test_rejection_path(self):
        """DRAFT → SUBMITTED → UNDER_REVIEW → REJECTED"""
        app = make_app("DRAFT")
        validate_transition(app, "SUBMITTED")
        app.status = "SUBMITTED"
        validate_transition(app, "UNDER_REVIEW")
        app.status = "UNDER_REVIEW"
        validate_transition(app, "REJECTED", comment="Not eligible")
        app.status = "REJECTED"

        # Terminal
        with pytest.raises(IllegalTransitionError):
            validate_transition(app, "DRAFT")


# ── Verify LEGAL_TRANSITIONS exhaustively ──────────────────────────────────────

class TestLegalTransitionsExhaustive:
    """Verify every transition in the LEGAL_TRANSITIONS map."""

    def test_legal_transitions_map_matches_can_transition(self):
        for from_status, to_set in LEGAL_TRANSITIONS.items():
            for to_status in to_set:
                assert can_transition(from_status, to_status) is True, \
                    f"LEGAL_TRANSITIONS says {from_status}→{to_status} is legal but can_transition says no"

    def test_no_extra_legal_transitions(self):
        """Ensure can_transition doesn't allow anything not in the map."""
        all_statuses = list(LEGAL_TRANSITIONS.keys())
        for from_status in all_statuses:
            for to_status in all_statuses:
                expected = to_status in LEGAL_TRANSITIONS.get(from_status, set())
                actual = can_transition(from_status, to_status)
                assert actual == expected, \
                    f"Mismatch: {from_status}→{to_status}: can_transition={actual}, expected={expected}"
