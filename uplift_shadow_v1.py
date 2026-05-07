"""Shadow-only uplift recommendation scorer.

Side-effect free: no Remote Config writes, no user mutation, no gameplay changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

MODEL_VERSION = "uplift_shadow_v1"
MIN_USERS = 100
CRASH_FREE_KILL_THRESHOLD = 0.995
MAX_SAFE_RISK_SCORE = 0.30


@dataclass(frozen=True)
class UpliftMetrics:
    segment: str
    users: int
    crash_free_users: float
    retention_d1_a: float = 0.0
    retention_d1_b: float = 0.0
    rpu_usd_a: float = 0.0
    rpu_usd_b: float = 0.0
    anr_rate: float = 0.0
    ad_impressions_per_user_a: float = 0.0
    ad_impressions_per_user_b: float = 0.0
    purchase_conversion_rate_a: float = 0.0
    purchase_conversion_rate_b: float = 0.0
    incident_active: bool = False
    drift_detected: bool = False
    audit_present: bool = True
    dry_run: bool = True


def _bounded(value: Any, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = minimum
    return min(max(numeric, minimum), maximum)


def _non_negative(value: Any) -> float:
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def metrics_from_mapping(payload: Mapping[str, Any]) -> UpliftMetrics:
    return UpliftMetrics(
        segment=str(payload.get("segment") or "unknown")[:240],
        users=max(int(payload.get("users") or 0), 0),
        crash_free_users=_bounded(payload.get("crash_free_users")),
        retention_d1_a=_bounded(payload.get("retention_d1_a")),
        retention_d1_b=_bounded(payload.get("retention_d1_b")),
        rpu_usd_a=_non_negative(payload.get("rpu_usd_a")),
        rpu_usd_b=_non_negative(payload.get("rpu_usd_b")),
        anr_rate=_bounded(payload.get("anr_rate")),
        ad_impressions_per_user_a=_non_negative(payload.get("ad_impressions_per_user_a")),
        ad_impressions_per_user_b=_non_negative(payload.get("ad_impressions_per_user_b")),
        purchase_conversion_rate_a=_bounded(payload.get("purchase_conversion_rate_a")),
        purchase_conversion_rate_b=_bounded(payload.get("purchase_conversion_rate_b")),
        incident_active=_as_bool(payload.get("incident_active")),
        drift_detected=_as_bool(payload.get("drift_detected")),
        audit_present=_as_bool(payload.get("audit_present"), default=True),
        dry_run=True,
    )


def compute_risk_score(metrics: UpliftMetrics) -> float:
    crash_component = _bounded((CRASH_FREE_KILL_THRESHOLD - metrics.crash_free_users) * 200)
    anr_component = _bounded(metrics.anr_rate * 20)
    ad_delta = metrics.ad_impressions_per_user_b - metrics.ad_impressions_per_user_a
    fatigue_component = _bounded(ad_delta / 20.0)
    retention_delta = metrics.retention_d1_b - metrics.retention_d1_a
    retention_penalty = _bounded(-retention_delta * 4)
    governance_component = 0.0
    if metrics.incident_active:
        governance_component += 0.35
    if metrics.drift_detected:
        governance_component += 0.25
    if not metrics.audit_present:
        governance_component += 0.25
    risk = (
        0.35 * crash_component
        + 0.20 * anr_component
        + 0.15 * fatigue_component
        + 0.15 * retention_penalty
        + 0.15 * _bounded(governance_component)
    )
    return round(_bounded(risk), 4)


def compute_uplift_score_b(metrics: UpliftMetrics) -> float:
    rpu_delta = metrics.rpu_usd_b - metrics.rpu_usd_a
    retention_delta = metrics.retention_d1_b - metrics.retention_d1_a
    purchase_delta = metrics.purchase_conversion_rate_b - metrics.purchase_conversion_rate_a
    ad_delta = metrics.ad_impressions_per_user_b - metrics.ad_impressions_per_user_a
    score = 0.50 * rpu_delta + 0.30 * retention_delta + 0.15 * purchase_delta - 0.05 * max(ad_delta, 0.0)
    return round(score, 4)


def score_uplift_shadow(payload: Mapping[str, Any]) -> dict[str, Any]:
    metrics = metrics_from_mapping(payload)
    risk_score = compute_risk_score(metrics)
    uplift_score_b = compute_uplift_score_b(metrics)
    hard_rule_triggered = False
    top_factors: list[str] = []

    if metrics.incident_active:
        recommended_action = "FREEZE"
        hard_rule_triggered = True
        top_factors.append("incident_active")
    elif metrics.drift_detected:
        recommended_action = "ZERO"
        hard_rule_triggered = True
        top_factors.append("drift_detected")
    elif not metrics.audit_present:
        recommended_action = "ZERO"
        hard_rule_triggered = True
        top_factors.append("audit_missing")
    elif metrics.users < MIN_USERS:
        recommended_action = "WAIT"
        hard_rule_triggered = True
        top_factors.append("low_data")
    elif metrics.crash_free_users < CRASH_FREE_KILL_THRESHOLD:
        recommended_action = "KILL"
        hard_rule_triggered = True
        top_factors.append("crash_free_below_threshold")
    elif uplift_score_b > 0 and risk_score < MAX_SAFE_RISK_SCORE:
        recommended_action = "RECOMMEND_SWITCH_TO_B"
        top_factors.append("positive_uplift_b")
    else:
        recommended_action = "KEEP_A"
        if uplift_score_b <= 0:
            top_factors.append("no_positive_uplift_b")
        if risk_score >= MAX_SAFE_RISK_SCORE:
            top_factors.append("risk_above_threshold")

    return {
        "segment": metrics.segment,
        "model_version": MODEL_VERSION,
        "risk_score": risk_score,
        "uplift_score_b": uplift_score_b,
        "recommended_action": recommended_action,
        "top_factors": top_factors,
        "hard_rule_triggered": hard_rule_triggered,
        "dry_run": True,
        "applied": False,
        "shadow_only": True,
        "input_snapshot": asdict(metrics),
    }
