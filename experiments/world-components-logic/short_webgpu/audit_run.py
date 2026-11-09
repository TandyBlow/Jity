"""Stream a sealed WebGPU batch's raw evidence; never load a model."""
from collections import Counter
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def journal(path, plan_sha, stats):
    previous = None
    with Path(path).open('rb') as f:
        for index, line in enumerate(f):
            if not line.endswith(b'\n'): raise ValueError('unsealed_partial_tail:' + str(path))
            row = json.loads(line)
            assert row['sequence'] == index and row['planSha256'] == plan_sha and row['previousSha256'] == previous
            assert digest({k: v for k, v in row.items() if k != 'sha256'}) == row['sha256']
            previous = row['sha256']; stats['events'] += 1
            yield row
    stats.update(path=str(path), sha256=file_sha(path), bytes=Path(path).stat().st_size, lastEventSha256=previous)


def audit(plan_path):
    plan_path = Path(plan_path).resolve()
    record_path = plan_path.with_name(plan_path.name.replace('.plan.json', '.record.json'))
    plan, record = json.loads(plan_path.read_text()), json.loads(record_path.read_text())
    assert record['status'] == 'diagnostic_completed'
    plan_sha = file_sha(plan_path)
    assert record['planSha256'] == plan_sha
    requests, replies, progress, profiles, starts, settles = {}, {}, {}, {}, Counter(), Counter()
    model_loads, devices, direct_case_batches = [], set(), Counter()
    journals = {'browser': {'events': 0}, 'case': {'events': 0}}
    expected_batch_hashes = {}
    for row in journal(record_path.with_suffix('.webgpu.jsonl'), plan_sha, journals['browser']):
        data = row['data']; payload = data.get('payload', {}); name = data.get('name')
        if name == 'webgpu_request_started':
            request = payload['request']; rid = request['requestId']; assert rid not in requests
            requests[rid] = request
            for text, sha in [('inputJson', 'inputSha256'), ('messagesJson', 'messagesSha256'), ('bindingJson', 'bindingSha256')]:
                assert hashlib.sha256(request[text].encode()).hexdigest() == request[sha]
        elif name == 'webgpu_browser_response':
            reply = payload['response']; rid = reply['requestId']; assert rid not in replies
            replies[rid] = reply
        elif name == 'webgpu_browser_event':
            event = payload['event']; kind = event['kind']; rid = event.get('requestId')
            if kind == 'request_model_load': model_loads.append(event)
            if kind == 'generator_forward_started': starts[rid] += 1
            if kind == 'generator_forward_settled': settles[rid] += 1
            if kind == 'generator_token_progress': progress[rid] = event['rawTokenIds']
            if kind == 'webgpu_kernel_profile_batch':
                r = requests[rid]
                for key in ('generation', 'component', 'inputSha256', 'bindingSha256', 'modelIdentity', 'codeIdentity', 'placementPolicySha256'):
                    assert digest(event[key]) == digest(r[key])
                p = profiles.setdefault(rid, {'batches': 0, 'kernels': 0, 'durationNs': 0, 'types': Counter(), 'weights': 0, 'positiveWeights': 0})
                assert event['batchIndex'] == p['batches'] and event['firstKernelIndex'] == p['kernels']
                expected_batch_hashes[(rid, event['batchIndex'])] = digest({k: v for k, v in event.items() if k != 'kind'})
                p['batches'] += 1
                for k in event['kernels']:
                    assert type(k['startTime']) is int and type(k['endTime']) is int and 0 <= k['startTime'] <= k['endTime']
                    p['kernels'] += 1; p['types'][k['kernelType']] += 1
                    p['durationNs'] += k['endTime'] - k['startTime']
                    if k['kernelType'] == 'MatMulNBits':
                        p['weights'] += 1
                        p['positiveWeights'] += int(k['endTime'] > k['startTime'])
    for row in journal(record_path.with_suffix('.journal.jsonl'), plan_sha, journals['case']):
        data = row['data']
        if row['kind'] == 'attempt_checkpoint' and data['name'] == 'webgpu_kernel_profile_batch':
            event = data['payload']; key = (event['requestId'], event['batchIndex'])
            assert digest(event) == expected_batch_hashes[key]
            direct_case_batches[key] += 1
    assert set(direct_case_batches) == set(expected_batch_hashes)
    assert all(n == 1 for n in direct_case_batches.values())
    assert len(requests) == len(replies) == len(plan['cases']) == len(record['attempts'])
    source_path = plan['dataSnapshot']['supervision.jsonl.gz']['path']
    assert file_sha(source_path) == plan['dataSnapshot']['supervision.jsonl.gz']['sha256']
    ids = {c['exampleId'] for c in plan['cases']}
    with gzip.open(source_path, 'rt') as f:
        sources = {x['exampleId']: x for line in f if (x := json.loads(line))['exampleId'] in ids}
    by_input = {(r['component'], r['inputSha256']): rid for rid, r in requests.items()}
    cases = []
    for case, attempt in zip(plan['cases'], record['attempts']):
        assert attempt['caseId'] == case['caseId']
        source = sources[case['exampleId']]
        assert digest(source['input']) == case['inputHash']
        rid = by_input[(case['component'], case['inputHash'])]
        request, reply, p = requests[rid], replies[rid], profiles[rid]
        assert json.loads(request['inputJson']) == source['input']
        assert starts[rid] == settles[rid] == 1
        assert reply['rawTokenIds'] == progress[rid] and reply['rawTokenIds'][-1] in (151645, 151643)
        assert reply['eosReached'] is True and reply['stopReason'] == 'eos' and reply['enableThinking'] is False
        assert len(reply['inputTokenIds']) <= request['maxInputTokens']
        assert len(reply['rawTokenIds']) <= request['maxNewTokens']
        d = reply['deviceIdentity']; devices.add(d['deviceSessionId'])
        assert d['runtimeDeviceVerified'] is True and d['adapterReferenceVerified'] is True and d['lost'] is False
        assert d['adapterInfo']['isFallbackAdapter'] is False
        e = reply['gpuEvidence']
        assert e['kernelCount'] == p['kernels'] and e['batchCount'] == p['batches'] and e['kernelTypeCounts'] == dict(p['types'])
        assert e['totalKernelDurationNs'] == p['durationNs'] and e['weightKernelCount'] == p['weights']
        assert e['positiveWeightKernelCount'] == p['positiveWeights'] > 0
        assert e['invalidCount'] == 0 and e['provesGpuWeightCompute'] is True
        assert e['cpuNodeCount'] is None and e['cpuNodeDurationMs'] is None
        cases.append({'caseId': case['caseId'], 'exampleId': case['exampleId'], 'component': case['component'],
            'inputHash': case['inputHash'], 'requestId': rid, 'browserCompletion': reply['status'],
            'componentCompletion': attempt['outcome']['completion'], 'rawText': reply['rawText'],
            'rawTokenIds': reply['rawTokenIds'], 'inputTokenCount': len(reply['inputTokenIds']),
            'outputTokenCount': len(reply['rawTokenIds']), 'timings': reply['timings'],
            'caseWallMs': attempt['timing']['caseWallMs'], 'gpuKernelCount': p['kernels'],
            'positiveGpuWeightKernelCount': p['positiveWeights'], 'observedGpuKernelMs': p['durationNs'] / 1e6,
            'kernelBatchCount': p['batches'], 'humanReview': 'pending', 'semanticApproval': False})
    assert len(devices) == 1
    return {'schema': 'jity-qwen-webgpu-sealed-audit-v1', 'runId': plan['runId'],
        'scope': 'base_zero_shot_text_diagnostic_not_full_chain', 'modelExecutionsDuringAudit': 0,
        'plan': {'path': str(plan_path), 'sha256': plan_sha},
        'record': {'path': str(record_path), 'sha256': file_sha(record_path)}, 'journals': journals,
        'supervisor': record['supervisor'], 'browserBootstrap': record['browserBootstrap'],
        'stages': record['stages'], 'registeredCases': len(cases),
        'browserResults': sum(c['browserCompletion'] == 'result' for c in cases),
        'componentResults': sum(c['componentCompletion']['status'] == 'result' for c in cases),
        'componentIncomplete': sum(c['componentCompletion']['status'] == 'incomplete' for c in cases),
        'allFullInputsExact': True, 'allTokenProgressMatchesFinal': True,
        'allJournalChainsVerified': True, 'allKernelBatchesAccounted': True,
        'allRequestsHavePositiveGpuWeightProof': True, 'deviceSessionCount': len(devices),
        'totalKernelBatches': sum(c['kernelBatchCount'] for c in cases),
        'totalKernels': sum(c['gpuKernelCount'] for c in cases),
        'totalGenerateMs': sum(c['timings']['forwardMs'] for c in cases),
        'totalObservedGpuKernelMs': sum(c['observedGpuKernelMs'] for c in cases),
        'medianCaseWallMs': statistics.median(c['caseWallMs'] for c in cases),
        'cases': cases, 'semanticQualityApproved': False, 'humanReviewCount': 0,
        'limits': ['Observed profiled GPU kernel duration is not pure unprofiled compute time.',
            'CPU node time, browser memory, GPU peak memory and full AB/C/ready cost remain unmeasured.',
            'Raw text and timing completeness do not prove semantic correctness.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan)
    with args.output.open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps({k: result[k] for k in ('registeredCases', 'browserResults', 'componentResults',
        'componentIncomplete', 'totalKernelBatches', 'totalKernels', 'totalGenerateMs',
        'totalObservedGpuKernelMs', 'medianCaseWallMs')}, ensure_ascii=False))
