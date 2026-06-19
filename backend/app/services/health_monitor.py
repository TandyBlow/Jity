"""HealthMonitor — narrative health metric computation (CAMP-09).

Pure Python computation from model_outputs instrumentation data.
Zero LLM calls. Metrics compared against auto_play.py baseline z-scores.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.database import Database
from app.schemas.campaign import HealthMetrics, HealthGuidanceHint

logger = logging.getLogger(__name__)

# Baseline statistics from auto_play.py runs (CAMP-09c).
# PLACEHOLDER values — must be calibrated from actual auto_play.py data.
DEFAULT_BASELINE: dict[str, tuple[float, float]] = {
    "word_count": (1200.0, 400.0),
    "sanity_delta": (-2.0, 5.0),
    "health_delta": (-1.0, 3.0),
    "dialogue_lines": (2.5, 1.5),
    "option_count": (3.5, 1.0),
    "location_changes_per_10": (3.0, 1.5),
}

Z_SCORE_THRESHOLD = -1.5  # Trigger guidance when metric > 1.5 std below mean
GUIDANCE_COOLDOWN = 5     # Inject at most once per N turns per category


class HealthMonitor:
    """Computes narrative health metrics from model_outputs instrumentation data."""

    def __init__(self, db: Database, baseline: dict[str, tuple[float, float]] | None = None) -> None:
        self.db = db
        self.baseline = baseline or DEFAULT_BASELINE
        self._cooldowns: dict[str, dict[str, int]] = {}

    def compute(self, campaign_id: str, turn: int) -> HealthMetrics:
        """Compute health metrics from recent model_outputs rows.

        Args:
            campaign_id: Campaign identifier for cooldown tracking
            turn: Current turn number

        Returns:
            HealthMetrics with computed values and guidance hints
        """
        outputs = self._get_recent_outputs(limit=10)

        word_count = sum(o.get("word_count", 0) for o in outputs) / max(len(outputs), 1)
        dialogue_lines = sum(o.get("dialogue_lines", 0) for o in outputs) / max(len(outputs), 1)
        option_count = sum(o.get("option_count", 0) for o in outputs) / max(len(outputs), 1)
        location_changes = sum(o.get("location_changed", 0) for o in outputs)

        # Compute z-scores
        z_word = self._z_score(word_count, "word_count")
        z_dialogue = self._z_score(dialogue_lines, "dialogue_lines")
        z_option = self._z_score(option_count, "option_count")
        z_location = self._z_score(location_changes, "location_changes_per_10")

        # Pacing: too slow = few words, no location changes
        if z_word < Z_SCORE_THRESHOLD and z_location < Z_SCORE_THRESHOLD:
            pacing_score = 0.2
        elif z_word > 1.0:
            pacing_score = 0.9
        else:
            pacing_score = 0.5

        # Tension trajectory
        sanity_deltas = [o.get("sanity_delta", 0) for o in outputs[-5:]]
        avg_sanity = sum(sanity_deltas) / max(len(sanity_deltas), 1)
        if avg_sanity < -5:
            tension_trajectory = "rising"
        elif avg_sanity > 2:
            tension_trajectory = "falling"
        else:
            tension_trajectory = "stable"

        # Dialogue density
        dialogue_density = dialogue_lines / max(word_count, 1)

        # Guidance hints
        hints: list[HealthGuidanceHint] = []
        cooldowns = self._cooldowns.setdefault(campaign_id, {})
        if pacing_score < 0.3 and self._check_cooldown(cooldowns, "pacing_slow", turn):
            hints.append(HealthGuidanceHint.PACING_SLOW)
            cooldowns["pacing_slow"] = turn
        if dialogue_density > 0.02 and self._check_cooldown(cooldowns, "dialogue_heavy", turn):
            hints.append(HealthGuidanceHint.DIALOGUE_HEAVY)
            cooldowns["dialogue_heavy"] = turn
        if z_option < -1.0 and self._check_cooldown(cooldowns, "clue_starvation", turn):
            hints.append(HealthGuidanceHint.CLUE_STARVATION)
            cooldowns["clue_starvation"] = turn

        return HealthMetrics(
            pacing_score=pacing_score,
            tension_trajectory=tension_trajectory,
            clue_exposure_rate=0.0,
            dialogue_density=dialogue_density,
            narrative_throughput=z_word,
            needs_guidance=len(hints) > 0,
            guidance_hints=hints,
            last_guidance_turn=dict(cooldowns),
        )

    def _get_recent_outputs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent model_outputs rows. Returns empty list if DB connection fails."""
        try:
            from app.database import Database
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM model_outputs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def _z_score(self, value: float, metric: str) -> float:
        """Compute z-score of value against baseline for metric."""
        mean, std = self.baseline.get(metric, (0, 1))
        if std == 0:
            return 0.0
        return (value - mean) / std

    @staticmethod
    def _check_cooldown(cooldowns: dict[str, int], hint_name: str, turn: int) -> bool:
        """Return True if guidance hint is off cooldown."""
        last = cooldowns.get(hint_name, -999)
        return (turn - last) >= GUIDANCE_COOLDOWN
