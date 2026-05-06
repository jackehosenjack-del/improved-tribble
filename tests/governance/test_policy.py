from app.governance.policy import (
    GovernanceContext,
    GovernanceDecision,
    governance_policy_check,
)


def test_denies_when_incident_active():
    ctx = GovernanceContext(
        incident_active=True,
        proof_is_fresh=True,
        audit_ready=True,
        recovery_ready=True,
        drift_detected=False,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.DENY_INCIDENT_ACTIVE


def test_denies_when_proof_is_stale():
    ctx = GovernanceContext(
        incident_active=False,
        proof_is_fresh=False,
        audit_ready=True,
        recovery_ready=True,
        drift_detected=False,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.DENY_STALE_PROOF


def test_denies_when_audit_missing():
    ctx = GovernanceContext(
        incident_active=False,
        proof_is_fresh=True,
        audit_ready=False,
        recovery_ready=True,
        drift_detected=False,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.DENY_MISSING_AUDIT


def test_denies_when_recovery_missing():
    ctx = GovernanceContext(
        incident_active=False,
        proof_is_fresh=True,
        audit_ready=True,
        recovery_ready=False,
        drift_detected=False,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.DENY_NO_RECOVERY


def test_denies_when_drift_detected():
    ctx = GovernanceContext(
        incident_active=False,
        proof_is_fresh=True,
        audit_ready=True,
        recovery_ready=True,
        drift_detected=True,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.DENY_DRIFT


def test_allows_one_window_only_when_all_checks_pass():
    ctx = GovernanceContext(
        incident_active=False,
        proof_is_fresh=True,
        audit_ready=True,
        recovery_ready=True,
        drift_detected=False,
    )

    assert governance_policy_check(ctx) == GovernanceDecision.ALLOW_ONE_WINDOW
