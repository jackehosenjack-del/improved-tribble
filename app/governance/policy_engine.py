"""Zero Trust Governance Policy Engine."""


def evaluate_runtime(ctx: dict) -> dict:
    checks = {
        "proof_is_live": ctx.get("proof_is_live") is True,
        "observation_is_live": ctx.get("observation_is_live") is True,
        "audit_is_complete": ctx.get("audit_is_complete") is True,
        "recovery_is_ready": ctx.get("recovery_is_ready") is True,
        "policy_is_intact": ctx.get("policy_is_intact") is True,
        "incident_inactive": ctx.get("incident_active") is False,
    }

    failed = [name for name, ok in checks.items() if not ok]

    if failed:
        return {
            "authority": "ZERO",
            "permission": "REVOKED",
            "action": "OBSERVE_ONLY",
            "failed": failed,
        }

    return {
        "authority": "CURRENT",
        "permission": "LEASE_ONE_CYCLE",
        "action": "EXECUTE",
        "failed": [],
    }
