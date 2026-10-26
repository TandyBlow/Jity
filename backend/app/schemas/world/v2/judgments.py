"""Immutable judgment facts shared by compute responses and recovery reads."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.world.contracts import Contract, Id, SafeInt
from .base import Hex64


class RollOutcome(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"ruleVersion": {"const": "reaction-d20-v1"}}},
         "then": {"properties": {"target": {"const": 11}}}},
    ]})

    rollId: Id
    groupId: Id
    sourceId: Id
    targetId: Id
    triggerKey: Id
    ruleVersion: Literal["reaction-fixture-v1", "reaction-d20-v1"]
    target: Annotated[SafeInt, Field(ge=1, le=20)]
    result: Annotated[SafeInt, Field(ge=1, le=20)]
    eligibilityBaselineDigest: Hex64
    eligible: bool
    admitted: bool

    @model_validator(mode="after")
    def final_admission(self):
        if self.ruleVersion == "reaction-d20-v1" and self.target != 11:
            raise ValueError("reaction-d20-v1 requires target 11")
        if self.admitted != (self.eligible and self.result >= self.target):
            raise ValueError("admission differs from fixed roll and eligibility")
        return self
