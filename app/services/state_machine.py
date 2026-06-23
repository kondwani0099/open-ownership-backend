"""
State machine: enforces legal status transitions.

Every transition is checked centrally here so that both
the API layer and tests can rely on a single source of truth.
"""

from app.models.application import LEGAL_TRANSITIONS, ApplicationInDB

# Transitions that require a comment
COMMENT_REQUIRED_TRANSITIONS = {
    ("SUBMITTED", "RETURNED_FOR_CHANGES"),
    ("UNDER_REVIEW", "REJECTED"),
}


class IllegalTransitionError(Exception):
    """Raised when a transition is not allowed by the state machine."""
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Illegal transition: {current} → {target}")


class MissingCommentError(Exception):
    """Raised when a comment-required transition is attempted without one."""
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(
            f"A comment is required for transition: {current} → {target}"
        )


def can_transition(current_status: str, target_status: str) -> bool:
    """Check whether a transition is syntactically legal."""
    allowed = LEGAL_TRANSITIONS.get(current_status, set())
    return target_status in allowed


def transition_requires_comment(current_status: str, target_status: str) -> bool:
    """Check whether a transition requires a comment."""
    return (current_status, target_status) in COMMENT_REQUIRED_TRANSITIONS


def validate_transition(
    application: ApplicationInDB,
    target_status: str,
    comment: str = "",
) -> None:
    """
    Validate a status transition for the given application.

    Raises:
        IllegalTransitionError if the transition is not allowed.
        MissingCommentError if a comment is required but missing.
    """
    current = application.status
    if not can_transition(current, target_status):
        raise IllegalTransitionError(current, target_status)
    if transition_requires_comment(current, target_status) and not comment.strip():
        raise MissingCommentError(current, target_status)


# ── Mapping: "action" → target status ──────────────────────────────────────────
ACTION_TO_STATUS: dict[str, str] = {
    "submit":  "SUBMITTED",
    "review":  "UNDER_REVIEW",
    "approve": "APPROVED",
    "reject":  "REJECTED",
    "return":  "RETURNED_FOR_CHANGES",
}


def resolve_action(action: str) -> str:
    """Resolve a human-friendly action name to its target status."""
    if action not in ACTION_TO_STATUS:
        raise ValueError(f"Unknown action: {action}. Valid: {list(ACTION_TO_STATUS.keys())}")
    return ACTION_TO_STATUS[action]
