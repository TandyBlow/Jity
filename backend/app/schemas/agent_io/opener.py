"""Opening options schema — the choices proposed for a campaign's opening turn."""

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.game.story_output import OptionCheck


class OpeningOptions(BaseModel):
    """Options and their checks for a campaign opening, without narration.

    The opening narration is authored in the campaign file; only the choices come
    from the model, so this payload is deliberately narrower than StoryOutput.
    """

    options: list[str] = Field(min_length=2, max_length=6)
    option_checks: list[OptionCheck | None] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def _require_usable_options(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("options 不能包含空文本")
        return cleaned

    @field_validator("option_checks", mode="before")
    @classmethod
    def _require_explicit_difficulty(cls, values: Any) -> Any:
        """Reject checks that omit difficulty.

        The field carries a default, so a payload that forgets it would quietly
        become an ordinary check instead of failing loudly.
        """
        if not isinstance(values, list):
            return []
        for entry in values:
            if entry is None:
                continue
            if not isinstance(entry, dict):
                raise ValueError("option_checks 的元素必须是对象或 null")
            if "difficulty" not in entry:
                raise ValueError("option_checks 缺少必填字段：difficulty")
        return values

    @model_validator(mode="after")
    def _align_option_checks(self) -> "OpeningOptions":
        """Pad a short array with nulls, matching StoryOutput's behaviour."""
        aligned = list(self.option_checks[: len(self.options)])
        aligned.extend([None] * (len(self.options) - len(aligned)))
        self.option_checks = aligned
        return self
