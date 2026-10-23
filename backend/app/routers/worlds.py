"""v2 HTTP adapter. The registry owns paths, dispatch and wire schemas.

Errors stay inside this router so the existing campaign API keeps its own
FastAPI error handling. Preview budgets count the actual received JSON and
serialized response envelope, including UTF-8 and envelope overhead.
"""
from fastapi import APIRouter, Request
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.schemas.world.contracts import Id
from app.schemas.world.canonical import parse_json
from app.schemas.world.v2 import SCHEMA_MODELS
from app.schemas.world.v2.registry import OPERATIONS
from app.services.world.control import ServiceRefusal, _request_body_fields
from app.services.world.preview import preview_over_budget

router = APIRouter(tags=['worlds'])
PROTOCOL_HEADER = 'X-World-Protocol-Version'
MODELS = {model.__name__: model for model in SCHEMA_MODELS}
INTEGER_QUERY_FIELDS = frozenset({
    'after', 'limit', 'fenceEpoch', 'generation', 'issuedAtEpochMilli',
})


def _safe_id(value):
    try:
        return TypeAdapter(Id).validate_python(value)
    except ValidationError:
        return None


def _request_error(spec, detail):
    # The frozen read-only operations expose binding errors rather than the
    # write/query-malformed code. Stay within each operation's error surface.
    codes = {entry.code for entry in spec.errorCodes}
    code = 'request_malformed' if 'request_malformed' in codes else 'version_mismatch'
    return ServiceRefusal(code, detail)


async def _json_body(request, preview):
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if preview and preview_over_budget(len(chunks)):
            raise ServiceRefusal('preview_budget_exceeded', 'request byte budget',
                                 details={'limit': 'request'})
    try:
        # Use the shared parser before any float rounding can occur. It also
        # rejects duplicate keys, unsafe numbers and invalid canonical strings.
        body = parse_json(bytes(chunks).decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as error:
        raise ServiceRefusal('request_malformed', 'invalid JSON') from error
    if not isinstance(body, dict):
        raise ServiceRefusal('request_malformed', 'JSON object required')
    return body, len(chunks)


def _query(request, spec):
    query = {}
    for key, value in request.query_params.multi_items():
        if key not in spec.queryBindings or key in query:
            raise _request_error(spec, 'unknown or repeated query field')
        if key in INTEGER_QUERY_FIELDS:
            # Query parameters are strings on HTTP, but the contract is strict.
            if not value.isascii() or not value.isdecimal():
                raise _request_error(spec, 'integer query field required')
            try:
                value = int(value)
            except ValueError as error:
                raise _request_error(spec, 'integer query field is too long') from error
        elif key == 'includeRecovery':
            if value not in ('true', 'false'):
                raise _request_error(spec, 'boolean query field required')
            value = value == 'true'
        query[key] = value
    return query


def _endpoint(specs):
    async def endpoint(request: Request):
        service = request.app.state.world_service
        operation = specs[0].operation if len(specs) == 1 else None
        request_id = None
        world_id = _safe_id(request.path_params.get('worldId'))
        try:
            if request.headers.get(PROTOCOL_HEADER) != '2':
                raise ServiceRefusal('protocol_version_unsupported', 'v2 header required')
            body_method = request.method not in ('GET', 'DELETE')
            request_bytes = 0
            if body_method:
                payload, request_bytes = await _json_body(request, operation == 'preview_point')
                request_id = _safe_id(payload.get('requestId'))
                if len(specs) > 1:
                    selector = payload.get('operation')
                    selected = [spec for spec in specs
                                if spec.operation.removeprefix('checkpoint_') == selector
                                or spec.operation.removeprefix('round_conclusion_') == selector]
                    if len(selected) != 1:
                        raise ServiceRefusal('request_malformed', 'unknown operation selector')
                    spec = selected[0]
                    operation = spec.operation
                else:
                    spec = specs[0]
                version = payload.get('protocolVersion')
                if isinstance(version, bool) or version != 2:
                    raise ServiceRefusal('protocol_version_unsupported', 'v2 body required')
            else:
                spec = specs[0]
                payload = _query(request, spec)
                request_id = _safe_id(payload.get('requestId'))
            # The URL is authoritative; never silently overwrite conflicting
            # world/point identities from a write's JSON body.
            for key, value in request.path_params.items():
                if _safe_id(value) is None:
                    raise _request_error(spec, 'invalid path identity')
                if key in payload and payload[key] != value:
                    raise ServiceRefusal('version_mismatch', 'path/body identity differs')
                payload[key] = value
            payload['protocolVersion'] = 2
            if spec.requestSchema:
                model = MODELS[spec.requestSchema]
                fields = _request_body_fields(model)
                validated = {key: value for key, value in payload.items()
                             if key not in request.path_params or key in fields}
                # Read/query models take the wire version from the header.
                if not body_method and 'protocolVersion' not in fields:
                    validated.pop('protocolVersion', None)
                try:
                    model.model_validate(validated)
                except ValidationError as error:
                    raise _request_error(spec, 'request schema differs') from error
            result = await run_in_threadpool(service.execute, operation, payload)
            response = JSONResponse(result, status_code=spec.successHttpStatus)
            if operation == 'preview_point':
                budget = preview_over_budget(request_bytes, len(response.body))
                if budget:
                    raise ServiceRefusal('preview_budget_exceeded', 'response byte budget',
                                         details={'limit': budget[0]})
            return response
        except ServiceRefusal as error:
            result = service.error_response(error, operation, request_id, world_id)
            return JSONResponse(result, status_code=error.http_status)

    return endpoint


_routes = {}
for _spec in OPERATIONS:
    _routes.setdefault((_spec.method, _spec.path), []).append(_spec)
for (_method, _path), _specs in _routes.items():
    router.add_api_route(_path, _endpoint(_specs), methods=[_method],
                         name=_specs[0].operation, response_model=None)
