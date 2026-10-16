"""Server-validated roll-high d20 action checks."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DIFFICULTY_TARGETS = {"容易": 8, "普通": 12, "困难": 16, "极难": 19}


class OptionCheck(BaseModel):
    """An optional check stored alongside one story option."""

    requires_check: bool = True
    name: str = "行动检定"
    skill: str = "行动"
    system: str = "通用 d20"
    difficulty: Literal["容易", "普通", "困难", "极难"] = "普通"
    stakes: str = "成功会推进当前行动，失败会带来相应后果。"
    target: int = Field(default=12, ge=1, le=20, description="推导字段，由 difficulty 决定")
    expression: str = "1d20 ≥ 12"

    @model_validator(mode="after")
    def _derive_threshold(self) -> "OptionCheck":
        self.target = DIFFICULTY_TARGETS[self.difficulty]
        self.expression = f"1d20 ≥ {self.target}"
        # All live checks use the same dice rule, including old saved metadata.
        self.system = "通用 d20"
        return self


class ActionCheckSubmission(BaseModel):
    """The client submits only the die face and the selected option identity."""

    model_config = ConfigDict(extra="forbid")

    roll: int = Field(strict=True, ge=1, le=20)
    option_index: int | None = Field(default=None, strict=True, ge=0)


class ActionCheckRequest(BaseModel):
    player_action: str = Field(min_length=1)
    timeline_node_id: int = Field(strict=True, ge=1)
    option_index: int | None = Field(default=None, strict=True, ge=0)


class ActionCheckResponse(BaseModel):
    check: OptionCheck | None = None
    option_index: int | None = None


class ActionCheckResult(BaseModel):
    """Authoritative result derived from the stored check and submitted die."""

    check: OptionCheck
    roll: int = Field(strict=True, ge=1, le=20)
    option_index: int | None = None
    outcome: Literal["critical", "success", "failure", "fumble"]
    degree: Literal["大成功", "成功", "失败", "大失败"]
