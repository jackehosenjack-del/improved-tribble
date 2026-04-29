import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Session, SQLModel, select


ALLOWED_REMOTE_CONFIG_KEYS = {
    "reward_daily_bonus_coins",
    "ads_interstitial_interval",
    "feature_bonus_popup_enabled",
    "rollout_step",
    "pricing_offer_variant",
    "pricing_offer_eur",
    "rollout_kill_switch",
}


class DecisionLog(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)

    app_id: str = SQLField(index=True)
    recommended_action: str = "WAIT"
    risk_score: float = 0
    uplift_score_b: float = 0

    metrics_json: str = "{}"
    top_factors_json: str = "[]"

    mode: str = "shadow"  # shadow | live
    applied: bool = False

    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class RemoteConfigState(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)

    app_id: str = SQLField(index=True, unique=True)
    config_json: str = "{}"

    version: int = 1
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class RemoteConfigAudit(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)

    app_id: str = SQLField(index=True)
    decision_log_id: int = SQLField(index=True)
    idempotency_key: str = SQLField(index=True, unique=True)

    previous_config_json: str = "{}"
    changes_json: str
    resulting_config_json: str = "{}"

    dry_run: bool = True
    applied: bool = False
    status: str = "dry_run"  # dry_run | applied | rejected | rollback

    reason: Optional[str] = None
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class DecisionRequest(BaseModel):
    metrics: Dict[str, Any] = Field(default_factory=dict)
    recommended_action: str = Field(default="WAIT", max_length=80)
    risk_score: float = Field(default=0, ge=0, le=1)
    uplift_score_b: float = 0
    top_factors: list[str] = Field(default_factory=list)


class RemoteConfigApplyRequest(BaseModel):
    app_id: str = Field(min_length=1, max_length=120)
    decision_log_id: int = Field(gt=0)
    changes: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    idempotency_key: str = Field(min_length=6, max_length=160)


class RemoteConfigAuditOut(BaseModel):
    id: int
    app_id: str
    decision_log_id: int
    idempotency_key: str
    previous_config: Dict[str, Any]
    changes: Dict[str, Any]
    resulting_config: Dict[str, Any]
    dry_run: bool
    applied: bool
    status: str
    reason: Optional[str]
    created_at: datetime


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _audit_to_out(audit: RemoteConfigAudit) -> dict:
    return {
        "id": audit.id,
        "app_id": audit.app_id,
        "decision_log_id": audit.decision_log_id,
        "idempotency_key": audit.idempotency_key,
        "previous_config": _json_loads(audit.previous_config_json, {}),
        "changes": _json_loads(audit.changes_json, {}),
        "resulting_config": _json_loads(audit.resulting_config_json, {}),
        "dry_run": audit.dry_run,
        "applied": audit.applied,
        "status": audit.status,
        "reason": audit.reason,
        "created_at": audit.created_at,
    }


def get_or_create_config_state(session: Session, app_id: str) -> RemoteConfigState:
    state = session.exec(
        select(RemoteConfigState).where(RemoteConfigState.app_id == app_id)
    ).first()

    if state:
        return state

    state = RemoteConfigState(app_id=app_id, config_json="{}", version=1)
    session.add(state)
    session.flush()
    return state


def validate_remote_config_changes(changes: Dict[str, Any]) -> None:
    if not changes:
        raise HTTPException(status_code=400, detail="No config changes supplied")

    invalid = [key for key in changes if key not in ALLOWED_REMOTE_CONFIG_KEYS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid keys: {invalid}")

    # Safety rule: AI/config automation may activate a kill switch,
    # but must never disable it automatically.
    if changes.get("rollout_kill_switch") is False:
        raise HTTPException(
            status_code=400,
            detail="rollout_kill_switch=false is blocked by governance policy",
        )


def create_rejected_audit(
    session: Session,
    payload: RemoteConfigApplyRequest,
    previous_config: Dict[str, Any],
    reason: str,
) -> RemoteConfigAudit:
    audit = RemoteConfigAudit(
        app_id=payload.app_id,
        decision_log_id=payload.decision_log_id,
        idempotency_key=payload.idempotency_key,
        previous_config_json=_json_dumps(previous_config),
        changes_json=_json_dumps(payload.changes),
        resulting_config_json=_json_dumps(previous_config),
        dry_run=payload.dry_run,
        applied=False,
        status="rejected",
        reason=reason,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)
    return audit


def ensure_live_apply_has_matching_dry_run(
    session: Session,
    decision_log_id: int,
    changes: Dict[str, Any],
) -> None:
    previous_dry_run = session.exec(
        select(RemoteConfigAudit)
        .where(RemoteConfigAudit.decision_log_id == decision_log_id)
        .where(RemoteConfigAudit.status == "dry_run")
        .order_by(RemoteConfigAudit.created_at.desc())
    ).first()

    if not previous_dry_run:
        raise HTTPException(
            status_code=400,
            detail="Live apply blocked: dry_run required before apply",
        )

    dry_run_changes = _json_loads(previous_dry_run.changes_json, {})
    if dry_run_changes != changes:
        raise HTTPException(
            status_code=400,
            detail="Live apply blocked: changes must match previous dry_run",
        )


def register_growth_os_routes(app: FastAPI, engine) -> None:
    @app.post("/growth-os/ai-decision/{app_id}")
    def create_ai_decision(app_id: str, payload: DecisionRequest | None = None):
        request = payload or DecisionRequest()
        with Session(engine) as session:
            log = DecisionLog(
                app_id=app_id,
                recommended_action=request.recommended_action,
                risk_score=round(request.risk_score, 3),
                uplift_score_b=round(request.uplift_score_b, 3),
                metrics_json=_json_dumps(request.metrics),
                top_factors_json=_json_dumps(request.top_factors),
                mode="shadow",
                applied=False,
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return {
                "decision_log_id": log.id,
                "app_id": log.app_id,
                "recommended_action": log.recommended_action,
                "risk_score": log.risk_score,
                "uplift_score_b": log.uplift_score_b,
                "top_factors": request.top_factors,
                "mode": log.mode,
                "applied": log.applied,
            }

    @app.post("/growth-os/remote-config/apply")
    def apply_remote_config(payload: RemoteConfigApplyRequest):
        with Session(engine) as session:
            existing = session.exec(
                select(RemoteConfigAudit).where(
                    RemoteConfigAudit.idempotency_key == payload.idempotency_key
                )
            ).first()
            if existing:
                return {
                    **_audit_to_out(existing),
                    "idempotent_replay": True,
                }

            decision_log = session.get(DecisionLog, payload.decision_log_id)
            if not decision_log:
                raise HTTPException(status_code=404, detail="DecisionLog not found")

            if decision_log.app_id != payload.app_id:
                raise HTTPException(status_code=400, detail="DecisionLog app_id mismatch")

            state = get_or_create_config_state(session, payload.app_id)
            previous_config = _json_loads(state.config_json, {})

            try:
                validate_remote_config_changes(payload.changes)
                if not payload.dry_run:
                    ensure_live_apply_has_matching_dry_run(
                        session=session,
                        decision_log_id=payload.decision_log_id,
                        changes=payload.changes,
                    )
            except HTTPException as exc:
                create_rejected_audit(
                    session=session,
                    payload=payload,
                    previous_config=previous_config,
                    reason=str(exc.detail),
                )
                raise

            resulting_config = {**previous_config, **payload.changes}
            audit = RemoteConfigAudit(
                app_id=payload.app_id,
                decision_log_id=payload.decision_log_id,
                idempotency_key=payload.idempotency_key,
                previous_config_json=_json_dumps(previous_config),
                changes_json=_json_dumps(payload.changes),
                resulting_config_json=_json_dumps(resulting_config),
                dry_run=payload.dry_run,
                applied=not payload.dry_run,
                status="dry_run" if payload.dry_run else "applied",
            )
            session.add(audit)

            if not payload.dry_run:
                state.config_json = _json_dumps(resulting_config)
                state.version += 1
                state.updated_at = _now_utc()
                decision_log.applied = True
                decision_log.mode = "live"

            session.commit()
            session.refresh(audit)
            return _audit_to_out(audit)

    @app.get("/growth-os/remote-config/state/{app_id}")
    def get_remote_config_state(app_id: str):
        with Session(engine) as session:
            state = get_or_create_config_state(session, app_id)
            session.commit()
            session.refresh(state)
            return {
                "app_id": state.app_id,
                "config": _json_loads(state.config_json, {}),
                "version": state.version,
                "updated_at": state.updated_at,
            }

    @app.get("/growth-os/remote-config/audit")
    def list_remote_config_audits(limit: int = 100):
        safe_limit = min(max(limit, 1), 250)
        with Session(engine) as session:
            audits = session.exec(
                select(RemoteConfigAudit)
                .order_by(RemoteConfigAudit.created_at.desc())
                .limit(safe_limit)
            ).all()
            return [_audit_to_out(audit) for audit in audits]

    @app.get("/growth-os/remote-config/audit/{audit_id}")
    def get_remote_config_audit(audit_id: int):
        with Session(engine) as session:
            audit = session.get(RemoteConfigAudit, audit_id)
            if not audit:
                raise HTTPException(status_code=404, detail="Audit not found")
            return _audit_to_out(audit)

    @app.post("/growth-os/remote-config/rollback/{audit_id}")
    def rollback_remote_config(audit_id: int):
        with Session(engine) as session:
            audit = session.get(RemoteConfigAudit, audit_id)
            if not audit:
                raise HTTPException(status_code=404, detail="Audit not found")

            if not audit.applied or audit.status != "applied":
                raise HTTPException(
                    status_code=400,
                    detail="Only applied configs can be rolled back",
                )

            rollback_key = f"rollback_{audit.id}"
            existing = session.exec(
                select(RemoteConfigAudit).where(
                    RemoteConfigAudit.idempotency_key == rollback_key
                )
            ).first()
            if existing:
                return {
                    **_audit_to_out(existing),
                    "idempotent_replay": True,
                    "rolled_back_from": audit.id,
                }

            state = get_or_create_config_state(session, audit.app_id)
            current_config = _json_loads(state.config_json, {})
            rollback_config = _json_loads(audit.previous_config_json, {})

            rollback_audit = RemoteConfigAudit(
                app_id=audit.app_id,
                decision_log_id=audit.decision_log_id,
                idempotency_key=rollback_key,
                previous_config_json=_json_dumps(current_config),
                changes_json=_json_dumps(rollback_config),
                resulting_config_json=_json_dumps(rollback_config),
                dry_run=False,
                applied=True,
                status="rollback",
                reason=f"Rollback for audit {audit.id}",
            )
            session.add(rollback_audit)

            state.config_json = _json_dumps(rollback_config)
            state.version += 1
            state.updated_at = _now_utc()

            session.commit()
            session.refresh(rollback_audit)
            return {
                **_audit_to_out(rollback_audit),
                "rolled_back_from": audit.id,
            }
