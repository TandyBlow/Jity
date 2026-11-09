"""Audit sealed profiling-comparison evidence without importing any model."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import statistics

from audit_run import digest, file_sha, journal

CALIBRATION_FIELDS = ('generation', 'component', 'inputSha256', 'messagesSha256', 'bindingSha256',
    'codec', 'modelIdentity', 'runtimeIdentity', 'codeIdentity', 'maxInputTokens', 'maxNewTokens', 'timeoutMs', 'decoding')


def audit(plan_path):
    plan_path = Path(plan_path).resolve()
    record_path = plan_path.with_name(plan_path.name.replace('.plan.json', '.record.json'))
    plan, record = json.loads(plan_path.read_text()), json.loads(record_path.read_text())
    assert record['status'] == 'diagnostic_completed' and record['unexecutedAttempts'] == 0
    plan_sha = file_sha(plan_path); assert record['planSha256'] == plan_sha
    for asset in [*plan['assets'].values(), plan['sourcePlan'], plan['sourceData']]:
        assert file_sha(asset['path']) == asset['sha256']
    for name, expected in plan['codeSha256'].items():
        assert file_sha(Path(plan['codeSnapshot']['directory']) / name) == expected
    source_ids = {w['exampleId'] for w in plan['workloads']}
    with gzip.open(plan['sourceData']['path'], 'rt') as stream:
        sources = {v['exampleId']: v for line in stream if (v := json.loads(line))['exampleId'] in source_ids}
    work = {w['workloadId']: w for w in plan['workloads']}
    for w in work.values():
        assert sources[w['exampleId']]['input'] == w['input'] and digest(w['input']) == w['inputHash']
    parity = json.loads(Path(plan['assets']['parity']['path']).read_text())
    requests, replies, progress, profiles = {}, {}, {}, {}
    starts, settles, case_batches, case_replies = Counter(), Counter(), Counter(), Counter()
    case_requests, batch_hashes, finished, load, parity_events = {}, {}, {}, [], []
    journals = {'browser': {'events': 0}, 'case': {'events': 0}}
    for row in journal(record_path.with_suffix('.webgpu.jsonl'), plan_sha, journals['browser']):
        data = row['data']; payload = data.get('payload', {}); name = data.get('name')
        if name == 'webgpu_request_started':
            request = payload['request']; rid = request['requestId']; assert rid not in requests
            requests[rid] = request
            assert request['requestSha256'] == digest({k: v for k, v in request.items() if k != 'requestSha256'})
            for text, sha in (('inputJson', 'inputSha256'), ('messagesJson', 'messagesSha256'), ('bindingJson', 'bindingSha256')):
                import hashlib
                assert hashlib.sha256(request[text].encode()).hexdigest() == request[sha]
        elif name == 'webgpu_browser_response':
            reply = payload['response']; rid = reply['requestId']; assert rid not in replies
            replies[rid] = reply
        elif name == 'webgpu_browser_event':
            event = payload['event']; kind = event['kind']; rid = event.get('requestId')
            if kind == 'request_model_load': load.append(event)
            if kind == 'tokenizer_parity_finished': parity_events.append(event)
            if kind in ('webgpu_device_lost', 'webgpu_unexpected_profile_kernel'):
                raise ValueError('unexpected_device_or_profile_event:' + kind)
            if kind == 'generator_forward_started':
                starts[rid] += 1
                assert event['completeInput'] is True and event['enableThinking'] is False
                requests[rid]['_observedInputIds'] = event['inputIds']
            if kind == 'generator_forward_settled': settles[rid] += 1
            if kind == 'generator_token_progress': progress[rid] = event['rawTokenIds']
            if kind == 'webgpu_kernel_profile_finished':
                assert rid not in finished; finished[rid] = event
            if kind == 'webgpu_kernel_profile_batch':
                request = requests[rid]; assert request['profilingMode'] == 'default'
                for key in ('generation', 'component', 'inputSha256', 'bindingSha256', 'modelIdentity', 'codeIdentity', 'placementPolicySha256'):
                    assert digest(event[key]) == digest(request[key])
                profile = profiles.setdefault(rid, {'batches': 0, 'kernels': 0, 'durationNs': 0,
                    'types': Counter(), 'weights': 0, 'positiveWeights': 0})
                assert event['batchIndex'] == profile['batches'] and event['firstKernelIndex'] == profile['kernels']
                batch_hashes[(rid, event['batchIndex'])] = digest({k: v for k, v in event.items() if k != 'kind'})
                profile['batches'] += 1
                for kernel in event['kernels']:
                    assert type(kernel['startTime']) is int and type(kernel['endTime']) is int
                    assert 0 <= kernel['startTime'] <= kernel['endTime']
                    profile['kernels'] += 1; profile['types'][kernel['kernelType']] += 1
                    profile['durationNs'] += kernel['endTime'] - kernel['startTime']
                    if kernel['kernelType'] == 'MatMulNBits':
                        profile['weights'] += 1
                        profile['positiveWeights'] += int(kernel['endTime'] > kernel['startTime'])
    for row in journal(record_path.with_suffix('.journal.jsonl'), plan_sha, journals['case']):
        if row['kind'] != 'attempt_checkpoint': continue
        data = row['data']; event = data['payload']; name = data['name']
        if name == 'webgpu_request_started':
            rid = event['request']['requestId']; assert data['caseId'] not in case_requests
            case_requests[data['caseId']] = rid
            assert event['request'] == {k: v for k, v in requests[rid].items() if not k.startswith('_')}
        if name == 'webgpu_browser_response':
            rid = event['response']['requestId']; assert event['response'] == replies[rid]
            case_replies[rid] += 1
        if name == 'webgpu_kernel_profile_batch':
            key = (event['requestId'], event['batchIndex'])
            assert digest(event) == batch_hashes[key]; case_batches[key] += 1
    assert set(case_batches) == set(batch_hashes) and all(n == 1 for n in case_batches.values())
    assert len(requests) == len(replies) == len(plan['cases']) == len(record['attempts']) == 8
    assert len(load) == 1 and len(parity_events) == 1
    parity_event = parity_events[0]
    assert parity_event['sourceSha256'] == plan['assets']['parity']['sha256']
    assert {v['exampleId']: v['actualInputIds'] for v in parity_event['cases']} == {
        v['exampleId']: v['expectedInputIds'] for v in parity['cases']}
    devices, completed_on, cases = set(), set(), []
    repeated_inputs, repeated_outputs = {}, {}
    for case, attempt in zip(plan['cases'], record['attempts']):
        assert case['caseId'] == attempt['caseId'] and attempt['status'] == 'complete'
        workload = work[case['workloadId']]; rid = case_requests[case['caseId']]
        request, reply = requests[rid], replies[rid]
        assert json.loads(request['inputJson']) == workload['input']
        messages = json.loads(request['messagesJson'])
        envelope = json.loads(next(m['content'] for m in messages if m['role'] == 'user'))
        assert envelope == {'component': case['component'], 'context': workload['input']}
        assert starts[rid] == settles[rid] == case_replies[rid] == 1
        assert request['profilingMode'] == case['profilingMode'] == attempt['profilingMode']
        assert reply['status'] == attempt['completion']['status'] == 'result'
        assert attempt['completion']['value'] == reply['rawText'] == attempt['nativeOutput']['rawText']
        assert reply['rawTokenIds'] == progress[rid] == attempt['nativeOutput']['rawTokenIds']
        assert reply['inputTokenIds'] == request['_observedInputIds']
        assert reply['rawTokenIds'][-1] in (151645, 151643)
        assert reply['eosReached'] is True and reply['stopReason'] == 'eos' and reply['enableThinking'] is False
        assert len(reply['inputTokenIds']) <= request['maxInputTokens'] and len(reply['rawTokenIds']) <= request['maxNewTokens']
        for key in ('requestId', 'requestSha256', 'generation', 'component', 'inputSha256', 'messagesSha256',
                    'bindingSha256', 'codec', 'modelIdentity', 'runtimeIdentity', 'codeIdentity', 'profilingMode', 'placementPolicySha256'):
            assert digest(reply[key]) == digest(request[key])
        device = reply['deviceIdentity']; devices.add(device['deviceSessionId'])
        assert device['runtimeDeviceVerified'] is True and device['adapterReferenceVerified'] is True
        assert device['lost'] is False and device['adapterInfo']['isFallbackAdapter'] is False
        evidence = reply['gpuEvidence']; assert evidence == finished[rid]['gpuEvidence']
        assert evidence['cpuNodeCount'] is None and evidence['cpuNodeDurationMs'] is None
        profile = profiles.get(rid)
        calibration = None
        if case['profilingMode'] == 'default':
            assert profile is not None
            assert evidence['kernelCount'] == profile['kernels'] and evidence['batchCount'] == profile['batches']
            assert evidence['kernelTypeCounts'] == dict(profile['types'])
            assert evidence['totalKernelDurationNs'] == profile['durationNs']
            assert evidence['weightKernelCount'] == profile['weights']
            assert evidence['positiveWeightKernelCount'] == profile['positiveWeights'] > 0
            assert evidence['invalidCount'] == 0 and evidence['provesGpuWeightCompute'] is True
            completed_on.add(rid)
        else:
            assert profile is None and evidence['perRequestGpuProof'] is False
            assert evidence['source'] == 'same_session_same_input_prior_gpu_calibration_v1'
            assert evidence['kernelCount'] is None and evidence['totalKernelDurationNs'] is None
            assert evidence['unexpectedProfileKernelCount'] == 0
            calibration = evidence['calibration']; assert calibration == request['calibration']
            previous = calibration['requestId']; assert previous in completed_on
            assert calibration['requestSha256'] == requests[previous]['requestSha256']
            assert calibration['deviceSessionId'] == device['deviceSessionId'] == replies[previous]['deviceIdentity']['deviceSessionId']
            assert calibration['positiveWeightKernelCount'] == profiles[previous]['positiveWeights']
            scope = {key: request[key] for key in CALIBRATION_FIELDS}
            assert scope == {key: requests[previous][key] for key in CALIBRATION_FIELDS}
            assert calibration['scopeSha256'] == digest(scope)
        wid = case['workloadId']
        repeated_inputs.setdefault(wid, reply['inputTokenIds']); assert repeated_inputs[wid] == reply['inputTokenIds']
        repeated_outputs.setdefault(wid, (reply['rawText'], reply['rawTokenIds']))
        assert repeated_outputs[wid] == (reply['rawText'], reply['rawTokenIds'])
        assert all(attempt[key] >= 0 for key in ('resultJournalMs', 'snapshotEndMs', 'telemetryJournalMs'))
        cases.append({'caseId': case['caseId'], 'component': case['component'], 'workloadId': wid,
            'mode': case['profilingMode'], 'requestId': rid, 'inputHash': workload['inputHash'],
            'inputTokenCount': len(reply['inputTokenIds']), 'outputTokenCount': len(reply['rawTokenIds']),
            'rawText': reply['rawText'], 'rawTokenIds': reply['rawTokenIds'], 'eosReached': True,
            'componentCompletion': attempt['completion'], 'timings': reply['timings'],
            'caseWallMs': attempt['elapsedIncludingTelemetryMs'],
            'resultJournalMs': attempt['resultJournalMs'], 'snapshotEndMs': attempt['snapshotEndMs'],
            'telemetryJournalMs': attempt['telemetryJournalMs'],
            'observedGpuKernelMs': profile['durationNs'] / 1e6 if profile else None,
            'kernelCount': profile['kernels'] if profile else None,
            'positiveWeightKernelCount': profile['positiveWeights'] if profile else None,
            'perRequestGpuProof': bool(profile), 'calibration': calibration})
    assert len(devices) == 1
    return {'schema': 'jity-webgpu-profiling-sealed-audit-v1', 'runId': plan['runId'],
        'modelExecutionsDuringAudit': 0, 'scope': 'fixed_base_two_inputs_on_off_repeated_diagnostic',
        'plan': {'path': str(plan_path), 'sha256': plan_sha},
        'record': {'path': str(record_path), 'sha256': file_sha(record_path)},
        'auditSourceSha256': file_sha(__file__), 'qualification': plan['qualification'],
        'journals': journals, 'supervisor': record['supervisor'], 'bootstrap': record['browserBootstrap'],
        'stages': record['stages'], 'modelLoadEvents': load,
        'cases': cases, 'caseCount': len(cases), 'allComponentsResult': True,
        'allInputsExact': True, 'allTokenProgressMatchesFinal': True, 'allEosReached': True,
        'journalChainsVerified': True, 'allKernelBatchesAccounted': True,
        'offCalibrationsBoundToPriorSameInputRequest': True, 'offPerRequestGpuProof': False,
        'tokenizerParityCases': len(parity['cases']), 'deviceSessionCount': len(devices),
        'totalKernelBatches': sum(p['batches'] for p in profiles.values()),
        'totalObservedKernels': sum(p['kernels'] for p in profiles.values()),
        'totalGenerateMs': sum(c['timings']['forwardMs'] for c in cases),
        'totalCaseWallMs': sum(c['caseWallMs'] for c in cases),
        'profiledOnKernelMsOnly': sum(c['observedGpuKernelMs'] or 0 for c in cases),
        'medianCaseWallMs': statistics.median(c['caseWallMs'] for c in cases),
        'comparisons': record['comparisons'], 'semanticQualityApproved': False,
        'limits': ['Two inputs from one already exposed development source, not eight independent semantic cases.',
            'Fixed on/off/on/off ordering is not counterbalanced; thermal state and background scheduling were not measured.',
            'Profiling changes pass boundaries; elapsed differences cannot isolate pure logging cost.',
            'Observed on-kernel durations are not unprofiled compute times; off GPU and all CPU operator times are unknown.',
            'Python RSS excludes browser/GPU memory; this is not a full AB/C/ready request.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(); result = audit(args.plan)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(json.dumps({key: result[key] for key in ('caseCount', 'totalKernelBatches', 'totalObservedKernels',
        'totalGenerateMs', 'totalCaseWallMs', 'profiledOnKernelMsOnly')}))
