# Economy Guard

State: LOOP_AWARE
Mode: ECONOMY_GUARDED
Goal: prevent loop abuse and uncontrolled cashout pressure.

## Endpoint

```http
GET /api/v1/economy/health
```

## Response shape

```json
{
  "cashout_volume_24h": 42.5,
  "reward_issued_24h": 88000,
  "referral_activations_24h": 13,
  "suspicious_users": 2,
  "risk_state": "guarded",
  "recommended_action": "observe"
}
```

## Core metric

```txt
economy_pressure = cashout_volume_24h / max(revenue_24h, 1)
```

## Risk bands

```txt
< 0.5   healthy
0.5-1.0 guarded
> 1.0   danger
```

## Recommended actions

- healthy: observe
- guarded: slow_rewards
- danger: lock_cashout_review

## Abuse indicators

- referral activation spike
- reward issued spike without matching revenue
- cashout volume above revenue
- repeated cashout requests by same user/device/window
- suspicious user count rising faster than total users

## Next implementation

Build a read-only FastAPI route first. Do not mutate balances from this endpoint. Use it as a dashboard and gate signal before any automatic action.
