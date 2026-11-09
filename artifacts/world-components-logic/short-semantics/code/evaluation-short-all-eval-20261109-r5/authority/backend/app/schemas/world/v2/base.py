"""v2 shared scalars and response envelope base.

The R1 recovery facts change the v2 response shape, so the response envelope
schemaVersion moves 1 -> 2 and old B clients reject new-version responses at
the first response. The other version axes are separate aliases and stay on 1:
the state model (WorldState, creation templates) and the trace format must not
be bumped together with the response line.
Domain types reused from the frozen v1 contracts are imported from
`app.schemas.world.contracts` directly by the modules that need them, so a v1
change cannot silently diverge from v2 usage.
"""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from app.schemas.world.contracts import Contract, Positive, _integer

PROTOCOL_VERSION = 2
ENGINE_VERSION = "world-engine-v1"
SCHEMA_VERSION = 2
STATE_SCHEMA_VERSION = 1
TRACE_FORMAT_VERSION = 1
CANONICAL_VERSION = "world-canonical-v1"

ProtocolVersion = Annotated[Literal[2], BeforeValidator(_integer)]
EngineVersion = Literal["world-engine-v1"]
SchemaVersion = Annotated[Literal[2], BeforeValidator(_integer)]
StateSchemaVersion = Annotated[Literal[1], BeforeValidator(_integer)]
# The shared integer guard matters on every version axis: a bare Literal[1]
# accepts True (== 1) while the exported JSON schema rejects it.
TraceFormatVersion = Annotated[Literal[1], BeforeValidator(_integer)]
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
