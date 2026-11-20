"""Internal kernel violation taxonomy; A2 maps these onto wire error codes."""
from dataclasses import dataclass
from enum import Enum


class ViolationKind(Enum):
    ID_UNRESOLVED = "id_unresolved"
    SEMANTIC_INVALID = "semantic_invalid"
    POSITION_INVALID = "position_invalid"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    TIME_LOCKED = "time_locked"
    PREFIX_BINDING = "prefix_binding"


@dataclass(frozen=True)
class Violation:
    """Structured refusal from a pure predicate; ``kind`` names the registry
    precondition or taxonomy entry, the A2 mapping table owns the wire code."""

    kind: str
    detail: str

    def __repr__(self):
        return f'Violation({self.kind}: {self.detail})'


class KernelViolation(Exception):
    """Fail-fast carrier for one refusal; A1b validation predicates return
    collections instead, the wire mapping never sees this type."""

    def __init__(self, kind: ViolationKind, detail: str):
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail
