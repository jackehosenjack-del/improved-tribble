from uplift_shadow_v1 import score_uplift_shadow


def test_shadow_scorer_returns_safe_contract():
    result = score_uplift_shadow({
        "segment": "country=DE|new_vs_returning=new|device_class=mid|traffic_source=organic",
        "users": 500,
        "crash_free_users": 0.999,
        "retention_d1_a": 0.25,
        "retention_d1_b": 0.31,
        "rpu_usd_a": 0.10,
        "rpu_usd_b": 0.18,
        "purchase_conversion_rate_a": 0.02,
        "purchase_conversion_rate_b": 0.03,
    })

    assert result["model_version"] == "uplift_shadow_v1"
    assert result["shadow_only"] is True
    assert result["dry_run"] is True
    assert result["applied"] is False
    assert "risk_score" in result
    assert "uplift_score_b" in result
    assert "recommended_action" in result
