"""IF-04 shared trace grammar. References are data nodes, never expressions."""
from typing import Literal
from pydantic import ConfigDict, Field, JsonValue, model_validator
from app.schemas.world.contracts import Contract, Id
from .base import Hex64, ProtocolVersion, TraceFormatVersion
from .registry import OperationName


class TraceVariable(Contract):
    name: Id
    kind: Literal['identity', 'clock', 'ownership', 'business']
    valueType: Literal['string', 'integer', 'boolean', 'object', 'array', 'null']
    origin: Literal['input', 'capture']
    captureStep: Id | None

    @model_validator(mode='after')
    def source(self):
        if (self.origin == 'capture') != (self.captureStep is not None):
            raise ValueError('captured variables need exactly one capture step')
        return self


class TraceCapture(Contract):
    variable: Id
    path: str = Field(pattern=r'^(/.*)?$')


class TraceAssertion(Contract):
    model_config=ConfigDict(extra='forbid',strict=True,json_schema_extra={'allOf':[
        {'if':{'properties':{'op':{'enum':['eq','ne','type','set','ordered','delta']}}},'then':{'required':['expected']}},
        {'if':{'properties':{'op':{'enum':['delta','time_window']}}},'then':{'required':['baseline']}},
    ]})
    op: Literal['eq', 'ne', 'type', 'range', 'set', 'ordered', 'delta', 'time_window', 'absent']
    path: str = Field(pattern=r'^(/.*)?$')
    expected: JsonValue = None
    baseline: JsonValue = None
    minimum: int | None = None
    maximum: int | None = None

    @model_validator(mode='after')
    def operands(self):
        if self.op in ('eq','ne','type','set','ordered','delta') and 'expected' not in self.model_fields_set:raise ValueError('assertion requires expected operand')
        if self.op in ('delta','time_window') and 'baseline' not in self.model_fields_set:raise ValueError('assertion requires baseline')
        if self.op in ('range','time_window') and self.minimum is None and self.maximum is None:raise ValueError('range requires bounds')
        if self.minimum is not None and self.maximum is not None and self.minimum>self.maximum:raise ValueError('inverted range')
        return self


class TraceStep(Contract):
    id: Id
    operation: OperationName
    scope: JsonValue
    request: JsonValue
    response: JsonValue
    responseKind: Literal['success', 'error']
    httpStatus: int = Field(ge=200, le=499)
    captures: list[TraceCapture]
    assertions: list[TraceAssertion] = Field(min_length=1)
    projectionPath: str | None
    digestPath: str | None
    expectedProjection: JsonValue = None
    nextAction: Literal['continue', 'compute', 'read', 'stop', 'retry_same_request',
        'reacquire_lease', 'refresh_context', 'wait_narration', 'regenerate_narration',
        'resolve_gate', 'pause', 'fix_request', 'none']

    @model_validator(mode='after')
    def projection_pair(self):
        if (self.projectionPath is None) != (self.expectedProjection is None) or (self.digestPath is None) != (self.expectedProjection is None):
            raise ValueError('projection path and independent expectation must occur together')
        if self.responseKind == 'error' and not any(a.path == '/error/code' and a.op == 'eq' for a in self.assertions):
            raise ValueError('error step requires an exact error code assertion')
        if not any(a.path not in ('', '/protocolVersion', '/engineVersion', '/schemaVersion', '/canonicalVersion') for a in self.assertions):
            raise ValueError('each step requires a semantic assertion')
        return self


class TraceSample(Contract):
    id: Id
    values: dict[Id, JsonValue]
    expectedDigests: dict[Id, Hex64]


class TraceDocument(Contract):
    model_config=ConfigDict(extra='forbid',strict=True,json_schema_extra={'allOf':[{'properties':{'steps':{
        'contains':{'required':['expectedProjection'],'properties':{'expectedProjection':{'not':{'type':'null'}}}},'minContains':1}}}]})
    traceFormatVersion: TraceFormatVersion
    protocolVersion: ProtocolVersion
    contractDigest: Hex64
    scenario: Literal['T01','T02','T03','T04','T05','T06','T07','T08','T09']
    acceptanceLayer: Literal['contract']
    runtimeTarget: Literal['runtime-A2','runtime-A3']
    description: str
    preconditions: list[str] = Field(min_length=1)
    variables: list[TraceVariable]
    steps: list[TraceStep] = Field(min_length=1)
    samples: list[TraceSample] = Field(min_length=2)

    @model_validator(mode='after')
    def expectations_and_samples(self):
        if not any(step.expectedProjection is not None for step in self.steps):raise ValueError('trace requires an independent state projection')
        if len({s.id for s in self.samples})!=len(self.samples):raise ValueError('duplicate sample id')
        return self
