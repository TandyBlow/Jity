"""Tests for narrative health monitor."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.schemas.campaign import HealthMetrics, HealthGuidanceHint
from app.services.health_monitor import HealthMonitor, DEFAULT_BASELINE, Z_SCORE_THRESHOLD


class TestHealthMonitor:
    """Tests for HealthMonitor metric computation."""

    def test_compute_returns_health_metrics(self):
        """compute() should return a HealthMetrics object."""
        db = MagicMock()
        monitor = HealthMonitor(db)
        metrics = monitor.compute("test-camp", 5)
        assert isinstance(metrics, HealthMetrics)
        assert 0.0 <= metrics.pacing_score <= 1.0
        assert metrics.tension_trajectory in ("rising", "falling", "stable", "peak", "valley")

    def test_default_baseline_has_metrics(self):
        """DEFAULT_BASELINE should contain all expected metrics."""
        assert "word_count" in DEFAULT_BASELINE
        assert "sanity_delta" in DEFAULT_BASELINE
        assert "dialogue_lines" in DEFAULT_BASELINE
        assert "option_count" in DEFAULT_BASELINE

    def test_z_score_calculation(self):
        """_z_score should compute correctly."""
        db = MagicMock()
        monitor = HealthMonitor(db)
        # value=800, mean=1200, std=400 → z = (800-1200)/400 = -1.0
        z = monitor._z_score(800, "word_count")
        assert z == -1.0

    def test_z_score_zero_std(self):
        """_z_score with zero std should return 0.0."""
        db = MagicMock()
        monitor = HealthMonitor(db)
        monitor.baseline["word_count"] = (1200.0, 0.0)
        z = monitor._z_score(800, "word_count")
        assert z == 0.0

    def test_cooldown_allows_after_threshold(self):
        """_check_cooldown should allow after GUIDANCE_COOLDOWN turns."""
        from app.services.health_monitor import GUIDANCE_COOLDOWN
        cooldowns = {"pacing_slow": 0}
        assert HealthMonitor._check_cooldown(cooldowns, "pacing_slow", GUIDANCE_COOLDOWN) is True

    def test_cooldown_blocks_within_threshold(self):
        """_check_cooldown should block within GUIDANCE_COOLDOWN turns."""
        from app.services.health_monitor import GUIDANCE_COOLDOWN
        cooldowns = {"pacing_slow": 3}
        assert HealthMonitor._check_cooldown(cooldowns, "pacing_slow", 4) is False


class TestHealthMetricsModel:
    """Tests for HealthMetrics Pydantic model."""

    def test_default_metrics(self):
        """Default HealthMetrics should have reasonable values."""
        m = HealthMetrics()
        assert m.pacing_score == 0.5
        assert m.tension_trajectory == "stable"
        assert m.dialogue_density == 0.0
        assert m.needs_guidance is False
        assert m.guidance_hints == []

    def test_metrics_with_hints(self):
        """HealthMetrics should accept guidance hints."""
        m = HealthMetrics(
            needs_guidance=True,
            guidance_hints=[HealthGuidanceHint.PACING_SLOW],
        )
        assert m.needs_guidance is True
        assert HealthGuidanceHint.PACING_SLOW in m.guidance_hints


class TestCampaignManagerHealth:
    """Tests for CampaignManager health guidance methods."""

    def test_inject_health_without_monitor_returns_none(self):
        """inject_health should return None when no monitor set."""
        from app.services.campaign_manager import CampaignManager
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        result = mgr.inject_health()
        assert result is None

    def test_build_health_guidance_pacing_slow(self):
        """_build_health_guidance should produce Chinese guidance for pacing_slow."""
        from app.services.campaign_manager import CampaignManager
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        metrics = HealthMetrics(
            needs_guidance=True,
            guidance_hints=[HealthGuidanceHint.PACING_SLOW],
        )
        result = mgr._build_health_guidance(metrics)
        assert result is not None
        assert "叙事健康引导" in result
        assert "节奏" in result

    def test_build_health_guidance_no_hints(self):
        """_build_health_guidance should return None when no hints."""
        from app.services.campaign_manager import CampaignManager
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        metrics = HealthMetrics(needs_guidance=False, guidance_hints=[])
        result = mgr._build_health_guidance(metrics)
        assert result is None
