"""v2 shared scalars and response envelope base.

S1 only bumps protocolVersion; schemaVersion/engineVersion stay on v1 because
the new v2 $defs add wire types without changing WorldState or apply semantics.
Domain types reused from the frozen v1 contracts are imported from
`app.schemas.world.contracts` directly by the modules that need them, so a v1
change cannot silently diverge from v2 usage.
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from app.schemas.world.contracts import Contract, Positive, _integer

PROTOCOL_VERSION = 2
ENGINE_VERSION = "world-engine-v1"
SCHEMA_VERSION = 1
CANONICAL_VERSION = "world-canonical-v1"

ProtocolVersion = Annotated[Literal[2], BeforeValidator(_integer)]
EngineVersion = Literal["world-engine-v1"]
SchemaVersion = Annotated[Literal[1], BeforeValidator(_integer)]
CanonicalVersion = Literal["world-canonical-v1"]
EpochMilli = Positive
Hex64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Envelope(Contract):
    """Version block shared by every v2 response; identifies the wire dialect."""

    protocolVersion: ProtocolVersion
    engineVersion: EngineVersion = ENGINE_VERSION
    schemaVersion: SchemaVersion = SCHEMA_VERSION
    canonicalVersion: CanonicalVersion = CANONICAL_VERSION
    serverTimeEpochMilli: EpochMilli
