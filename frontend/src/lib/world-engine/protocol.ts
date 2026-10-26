import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020';
import schema from '../../../../design/world-protocol/v2/world-protocol.schema.json';
import contract from '../../../../design/world-protocol/v2/api-contract.json';
import { worldOperations, type WorldOperation, type RequestMap, type Success, type ErrorResponse, type OperationSpec, type ClientAction, type ControlState } from './types';

export class ProtocolError extends Error { readonly name = 'ProtocolError'; }
const ajv = new Ajv2020({ strictSchema: true, strictTypes: false, strictRequired: false,
  allErrors: true, coerceTypes: false, useDefaults: false, removeAdditional: false });
ajv.addKeyword({ keyword: 'discriminator', schemaType: 'object', valid: true });
ajv.addSchema(schema);
const validators = new Map<string, ValidateFunction>();
export const operationRegistry = Object.fromEntries(contract.operations.map((op) => [op.operation, op])) as unknown as Record<WorldOperation, OperationSpec>;
if (Object.keys(operationRegistry).sort().join() !== [...worldOperations].sort().join()) throw new ProtocolError('Operation registry differs from TS consumer');
export const protocolHeader = contract.protocolHeader;

export function validateSchema(name: string, value: unknown): void {
  let fn = validators.get(name);
  if (!fn) {
    fn = ajv.getSchema(`${schema.$id}#/$defs/${name}`);
    if (!fn) throw new ProtocolError(`Unknown schema: ${name}`);
    validators.set(name, fn);
  }
  if (!fn(value)) throw new ProtocolError(`${name}: ${ajv.errorsText(fn.errors)}`);
}
export function validateRequest<K extends WorldOperation>(operation: K, request: unknown): RequestMap[K] {
  const spec = operationRegistry[operation];
  if (!spec) throw new ProtocolError(`Unknown operation: ${operation}`);
  if (spec.requestSchema) validateSchema(spec.requestSchema, request);
  else if (JSON.stringify(request) !== '{}') throw new ProtocolError('Bodyless operation accepts no request fields');
  return request as RequestMap[K];
}
function validateVersions(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== 'object') throw new ProtocolError('Response is not an object');
  const v = value as Record<string, unknown>;
  if (v.protocolVersion !== 2 || v.engineVersion !== 'world-engine-v1' || v.schemaVersion !== 2 || v.canonicalVersion !== 'world-canonical-v1') throw new ProtocolError('Unsupported response version');
}
export function validateSuccess<K extends WorldOperation>(operation: K, value: unknown): Success<K> {
  validateVersions(value);
  validateSchema(operationRegistry[operation].successSchema, value);
  if ('operation' in value && value.operation !== operation) throw new ProtocolError('Response operation mismatch');
  return value as unknown as Success<K>;
}
export function validateError(value: unknown): ErrorResponse {
  validateVersions(value);
  validateSchema('ErrorResponse', value);
  return value as unknown as ErrorResponse;
}
export const recoveryActions: Record<ClientAction, string> = {
  retry_same_request: 'preserve_request_id_and_payload', reacquire_lease: 'stop_writes_and_acquire',
  refresh_context: 'reload_context', wait_narration: 'wait_without_computing',
  regenerate_narration: 'request_fresh_claim', resolve_gate: 'inspect_current_control',
  pause: 'pause_preserving_frozen_work', fix_request: 'stop_automatic_retry', none: 'display_error',
};
export function canSchedule(control: ControlState): boolean { return control.canCompute; }
export function recoveryAction(error: ErrorResponse): string { return recoveryActions[error.error.clientAction]; }
