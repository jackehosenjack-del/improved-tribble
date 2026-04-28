from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Session, SQLModel, create_engine, select
from sqlalchemy import event
from sqlalchemy.engine import Engine


# Compliance guardrails: this app is free-play entertainment only.
REAL_MONEY_STAKES = False
CASHOUT_ENABLED = False
COINS_HAVE_CASH_VALUE = False
DONATION_AFFECTS_GAMEPLAY = False
DONATION_AFFECTS_WIN_CHANCE = False
PRIZES_HAVE_CASH_VALUE = False

DATABASE_URL = "sqlite:///demo_loop.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class PlayResult(str, Enum):
    small_win = "small_win"
    bonus = "bonus"
    no_win = "no_win"


class DemoUser(SQLModel, table=True):
    user_id: str = SQLField(primary_key=True)
    coins: int = 0
    xp: int = 0
    level: int = 1
    plays: int = 0
    badge: str = "New Player"
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class DemoEvent(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    event_name: str
    coins_delta: int = 0
    xp_delta: int = 0
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class DonationLog(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    user_id: str = SQLField(index=True)
    amount_eur: float
    provider: str = "manual"
    note: Optional[str] = None
    gameplay_effect: bool = False
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class PlayRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    action: str = Field(default="free_spin", max_length=40)


class DonationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    amount_eur: float = Field(gt=0, le=500)
    provider: str = Field(default="manual", max_length=40)
    note: Optional[str] = Field(default=None, max_length=240)


class CashoutRequest(BaseModel):
    user_id: str
    amount_eur: float
    provider: Optional[str] = None
    target_wallet: Optional[str] = None


app = FastAPI(
    title="Safe Demo Loop API",
    version="1.0.0",
    description="Free-play demo backend with virtual coins only. No real-money cashout.",
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def recalculate_level_and_badge(user: DemoUser) -> None:
    user.level = max(1, (user.xp // 100) + 1)
    if user.level >= 10:
        user.badge = "Gold Player"
    elif user.level >= 5:
        user.badge = "Silver Player"
    elif user.level >= 2:
        user.badge = "Bronze Player"
    else:
        user.badge = "New Player"


def get_or_create_user(session: Session, user_id: str) -> DemoUser:
    user = session.get(DemoUser, user_id)
    if user is None:
        user = DemoUser(user_id=user_id)
        session.add(user)
        session.flush()
    return user


def deterministic_reward(user_id: str, play_number: int) -> tuple[PlayResult, int, int]:
    # Deterministic for testability; not linked to donations or money.
    seed = sum(ord(ch) for ch in user_id) + play_number
    if seed % 10 == 0:
        return PlayResult.bonus, 100, 25
    if seed % 3 == 0:
        return PlayResult.small_win, 50, 10
    return PlayResult.no_win, 10, 5


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)


@app.get("/")
def root():
    return {
        "name": "Safe Demo Loop API",
        "status": "running",
        "mode": "FREE_PLAY",
        "cashout_enabled": CASHOUT_ENABLED,
        "real_money_stakes": REAL_MONEY_STAKES,
        "coins_have_cash_value": COINS_HAVE_CASH_VALUE,
        "endpoints": [
            "GET /health",
            "GET /api/v1/demo/config",
            "POST /api/v1/demo/play",
            "GET /api/v1/demo/state/{user_id}",
            "GET /api/v1/demo/leaderboard",
            "POST /api/v1/demo/donation/log",
            "POST /api/v1/cashout/request (disabled)",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "mode": "FREE_PLAY", "cashout_enabled": False}


@app.get("/api/v1/demo/config")
def demo_config():
    return {
        "real_money_stakes": REAL_MONEY_STAKES,
        "cashout_enabled": CASHOUT_ENABLED,
        "coins_have_cash_value": COINS_HAVE_CASH_VALUE,
        "donation_affects_gameplay": DONATION_AFFECTS_GAMEPLAY,
        "donation_affects_win_chance": DONATION_AFFECTS_WIN_CHANCE,
        "prizes_have_cash_value": PRIZES_HAVE_CASH_VALUE,
    }


@app.post("/api/v1/demo/play")
def demo_play(payload: PlayRequest):
    with Session(engine) as session:
        user = get_or_create_user(session, payload.user_id)
        next_play = user.plays + 1
        result, coins_delta, xp_delta = deterministic_reward(user.user_id, next_play)

        user.plays = next_play
        user.coins += coins_delta
        user.xp += xp_delta
        user.updated_at = now_utc()
        recalculate_level_and_badge(user)

        session.add(DemoEvent(
            user_id=user.user_id,
            event_name=f"demo_{payload.action}",
            coins_delta=coins_delta,
            xp_delta=xp_delta,
        ))
        session.add(user)
        session.commit()
        session.refresh(user)

        return {
            "user_id": user.user_id,
            "result": result,
            "coins_added": coins_delta,
            "xp_added": xp_delta,
            "total_coins": user.coins,
            "xp": user.xp,
            "level": user.level,
            "badge": user.badge,
            "cashout_enabled": CASHOUT_ENABLED,
            "real_money_value": COINS_HAVE_CASH_VALUE,
            "donation_affects_gameplay": DONATION_AFFECTS_GAMEPLAY,
        }


@app.get("/api/v1/demo/state/{user_id}")
def demo_state(user_id: str):
    with Session(engine) as session:
        user = get_or_create_user(session, user_id)
        session.commit()
        session.refresh(user)
        return {
            "user_id": user.user_id,
            "coins": user.coins,
            "xp": user.xp,
            "level": user.level,
            "badge": user.badge,
            "plays": user.plays,
            "cashout_enabled": CASHOUT_ENABLED,
            "coins_have_cash_value": COINS_HAVE_CASH_VALUE,
        }


@app.get("/api/v1/demo/leaderboard")
def demo_leaderboard(limit: int = 10):
    safe_limit = min(max(limit, 1), 100)
    with Session(engine) as session:
        users = session.exec(
            select(DemoUser).order_by(DemoUser.coins.desc(), DemoUser.xp.desc()).limit(safe_limit)
        ).all()
        return {
            "mode": "FREE_PLAY",
            "cashout_enabled": CASHOUT_ENABLED,
            "items": [
                {
                    "rank": index + 1,
                    "user_id": user.user_id,
                    "coins": user.coins,
                    "xp": user.xp,
                    "level": user.level,
                    "badge": user.badge,
                }
                for index, user in enumerate(users)
            ],
        }


@app.post("/api/v1/demo/donation/log")
def log_donation(payload: DonationRequest):
    with Session(engine) as session:
        get_or_create_user(session, payload.user_id)
        donation = DonationLog(
            user_id=payload.user_id,
            amount_eur=round(payload.amount_eur, 2),
            provider=payload.provider,
            note=payload.note,
            gameplay_effect=False,
        )
        session.add(donation)
        session.add(DemoEvent(
            user_id=payload.user_id,
            event_name="donation_logged_no_gameplay_effect",
            coins_delta=0,
            xp_delta=0,
        ))
        session.commit()
        session.refresh(donation)
        return {
            "status": "logged",
            "donation_id": donation.id,
            "user_id": payload.user_id,
            "amount_eur": donation.amount_eur,
            "gameplay_effect": False,
            "coins_added": 0,
            "win_chance_changed": False,
        }


@app.post("/api/v1/cashout/request")
def disabled_cashout(payload: CashoutRequest):
    raise HTTPException(
        status_code=403,
        detail={
            "error": "cashout_disabled",
            "reason": "Safe prototype uses virtual coins only. No real-money payout is available.",
            "cashout_enabled": CASHOUT_ENABLED,
        },
    )
