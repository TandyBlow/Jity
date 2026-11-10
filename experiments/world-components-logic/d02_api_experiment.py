"""Bounded DeepSeek API helper for the D02 pilot.

Only three values are read from the existing backend env file.  The key is
never printed, logged, put in a command line, or written to an artifact.
Every request records its actual token usage and a conservative CNY estimate;
the script refuses to start a request that could cross its local budget guard.

This is a proxy API experiment, not the production API version and not a
small-model run.  Natural generations and API checker answers are assistant
drafts, not gold labels.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers

DATA = HERE / 'data' / 'd02-checkers' / 'pilot-v1'
DEFAULT_USAGE = DATA / 'api' / 'usage.jsonl'
# Conservative published peak prices (USD per 1M tokens) and CNY rate.
USD_INPUT_PER_M = 0.30
USD_OUTPUT_PER_M = 1.20
CNY_PER_USD = 7.1
BUDGET_CNY = 20.0
GUARD_CNY = 18.5


class BudgetStop(RuntimeError):
    pass


def read_config(env_file):
    values = {}
    for line in Path(env_file).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.strip() in ('DEEPSEEK_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ('DEEPSEEK_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
        if not values.get(key):
            raise SystemExit('missing ' + key + ' in env file')
    return values


def peak_now(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.weekday() >= 5:
        return False
    return 1 <= now.hour < 4 or 6 <= now.hour < 10


def estimate_cny(usage, peak=True):
    factor = 1.0 if peak else 0.5
    return round((usage.get('prompt_tokens', 0) * USD_INPUT_PER_M +
                  usage.get('completion_tokens', 0) * USD_OUTPUT_PER_M) *
                 factor * CNY_PER_USD / 1_000_000, 8)


class Ledger:
    def __init__(self, path, *, budget=BUDGET_CNY, guard=GUARD_CNY):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.budget = budget
        self.guard = guard

    def rows(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def spent(self):
        return sum(row.get('estimatedCny', 0) for row in self.rows())

    def check_room(self, prompt_chars, max_tokens):
        # One character per token is deliberately pessimistic for Chinese and
        # keeps the local guard below the actual 20 CNY authorization.
        worst = estimate_cny({'prompt_tokens': prompt_chars, 'completion_tokens': max_tokens},
                             peak=True)
        if self.spent() + worst > self.guard:
            raise BudgetStop('local guard: worst-case request would cross %.2f CNY' % self.guard)

    def append(self, row):
        with self.path.open('a') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def call_api(config, ledger, *, purpose, messages, max_tokens, temperature=0,
             json_mode=False, thinking=False, timeout=180):
    prompt_chars = sum(len(row.get('content', '')) for row in messages)
    ledger.check_room(prompt_chars, max_tokens)
    body = {
        'model': config['LLM_MODEL'], 'messages': messages,
        'max_tokens': max_tokens, 'temperature': temperature, 'stream': False,
    }
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    if not thinking:
        body['thinking'] = {'type': 'disabled'}
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(
        config['LLM_BASE_URL'].rstrip('/') + '/chat/completions', data=data,
        headers={'Authorization': 'Bearer ' + config['DEEPSEEK_API_KEY'],
                 'Content-Type': 'application/json'})
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:500]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2)
                continue
            ledger.append({'purpose': purpose, 'status': 'http_error',
                           'http': exc.code, 'detail': detail,
                           'latencyMs': int((time.time() - started) * 1000),
                           'estimatedCny': 0})
            raise RuntimeError('HTTP %s: %s' % (exc.code, detail[:200]))
        except Exception as exc:
            if attempt < 2:
                time.sleep(2)
                continue
            ledger.append({'purpose': purpose, 'status': 'transport_error',
                           'detail': type(exc).__name__, 'latencyMs':
                           int((time.time() - started) * 1000), 'estimatedCny': 0})
            raise
    usage = payload.get('usage') or {}
    cny = estimate_cny(usage, peak=peak_now())
    message = (payload.get('choices') or [{}])[0].get('message') or {}
    row = {
        'purpose': purpose, 'status': 'ok', 'model': payload.get('model'),
        'requestId': payload.get('id'), 'usage': usage,
        'estimatedCny': cny, 'peak': peak_now(),
        'latencyMs': int((time.time() - started) * 1000),
        'finishReason': (payload.get('choices') or [{}])[0].get('finish_reason'),
        'contentSha256': hashlib.sha256((message.get('content') or '').encode()).hexdigest(),
        'contentChars': len(message.get('content') or ''),
        'reasoningChars': len(message.get('reasoning_content') or ''),
    }
    ledger.append(row)
    return {'content': message.get('content') or '', 'usage': usage,
            'model': payload.get('model'), 'finishReason': row['finishReason'],
            'latencyMs': row['latencyMs'], 'estimatedCny': cny, 'requestId': payload.get('id')}


def generation_prompt(scenario, worlds):
    world = worlds[scenario['worldId']]
    actor = world['entities'][scenario['actorId']]
    lines = [
        '你是文字跑团的 D02.2 行动生成器。',
        '世界实体登记（只能使用已登记实体）：',
        json.dumps(world, ensure_ascii=False, sort_keys=True),
        '当前执行人：%s（%s）' % (actor['name'], scenario['actorId']),
        '玩家原始需求：' + scenario['prompt'],
        '请提出一次完整的短行动尝试，保留必要的条件、对象和多步骤；不要替世界结算结果。',
        '只输出行动原文：1-3 个步骤，每步一句，用换行分隔，不要编号，不要解释。',
    ]
    return '\n'.join(lines)


def checker_prompt(sample, worlds):
    world = worlds[sample['worldId']]
    actor = world['entities'][sample['actorId']]
    step_lines = []
    for step in sample['steps']:
        step_lines.append('%s[%d:%d]=%s' % (
            step['stepId'], step['start'], step['end'],
            sample['text'][step['start']:step['end']]))
    prompt = f'''你是文字跑团的 D02 行动检查器。只检查同一份行动原文；不得改写原文，不判断工具是否可用、行动是否合理、需求是否覆盖。只输出 JSON，不要解释。
世界实体登记：{json.dumps(world, ensure_ascii=False, sort_keys=True)}
当前执行人：{actor['name']}（{sample['actorId']}）
完整行动原文（跨度使用 Unicode code point 偏移）：{sample['text']}
步骤边界：{'; '.join(step_lines)}

任务一 M1：对每个步骤识别所有提及和五个公开角色。
返回 roleAudit 对象：
- steps: 每个输入步骤一项，stepId 必须完全一致。
- mentions: 每项包含 mentionId（步骤内唯一）、start、end、surface、roles（数组，可多角色）、diagnosticRoles（数组，来源/静态场所等内部角色）、status、bindingBasis、scope、entityId（可省略）、candidates（歧义时至少两个 ID）、confidence（可省略 0-1）。
- surface 必须等于原文切片；start/end 是半开区间 [start,end)，不含标点，end 指向切片后一位；同一跨度只出现一次，多角色合并到 roles。
- status 只能是 bound / unknown_entity / ambiguous / insufficient。
- bindingBasis 只能是 name / alias / pronoun / ellipsis / context / marker；本批一律自然名，不用 marker。
- 有提及但未登记用 unknown_entity；有多个可能实体用 ambiguous；不能确定用 insufficient；确实没有该角色不写 mention。
- roleStatus: 五个键 subject/object/tool/recipient/destination，每项 {{"status":"absent|bound|unknown_entity|ambiguous|insufficient","mentionIds":[...]}}。absent 表示这一步确实没有该角色；insufficient 表示有该角色但无法确定。不能用 null 混同。
- subject 必须按文本实际写的主体，不能把当前执行人当成默认主体。没有公开角色的提及放进 diagnosticRoles，不得伪装成五个公开角色。
- issues: 模型发现的结构问题数组，没有则 []；每项 code、message、blocking、stepId、scope。

任务二 M2：对整段做表达类型分类，并定位问题片段。
返回 expressionAudit 对象：
- label 只能是 attempt / result_assertion / non_action / mixed / uncertain。
- issues: 每项 code、message、blocking、scope、stepId、start、end。scope 只能是 main / condition / negation / quote / hypothesis / background。
- 只把未结算的本次结果写在事实语气中视为 result_assertion 或 mixed；条件、否定、引用、假设、背景中的成功词不要当成已发生结果。
- attempt 表示提出可供后续结算的行动，不要求出现“尝试”二字。
- abstain 为 null；若无法判断才用 {{"reason":"low_confidence|ambiguous_input|input_too_long|out_of_support|missing_context","detail":"..."}}，且 label 为 null。

严格输出：
{{"roleAudit":{{"steps":[...],"issues":[]}},"expressionAudit":{{"label":"...","issues":[],"abstain":null}}}}
必须输出完整 JSON，不能省略 steps、mentions、roleStatus、label、issues、abstain。'''
    return prompt


def parse_json(content):
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError('not_object')
    return value


def assemble_audits(parsed, text):
    role = parsed.get('roleAudit')
    expr = parsed.get('expressionAudit')
    if not isinstance(role, dict) or not isinstance(expr, dict):
        raise ValueError('missing_role_or_expression_audit')
    role = dict(role)
    expr = dict(expr)
    role['schema'] = checkers.ROLE_SCHEMA
    role['textSha256'] = checkers.digest(text)
    role.setdefault('issues', [])
    expr['schema'] = checkers.EXPRESSION_SCHEMA
    expr['textSha256'] = checkers.digest(text)
    expr.setdefault('issues', [])
    expr.setdefault('abstain', None)
    return role, expr


def run_generate(args):
    config = read_config(args.env_file)
    ledger = Ledger(args.usage)
    scenarios = json.loads((DATA / 'scenarios.json').read_text())
    worlds = json.loads((DATA / 'worlds.json').read_text())
    output = DATA / 'api' / 'natural-raw.jsonl'
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        raise SystemExit('natural raw already exists; pass --force only for a new batch')
    rows = []
    for scenario in scenarios[:args.limit]:
        prompt = generation_prompt(scenario, worlds)
        answer = call_api(config, ledger, purpose='natural_generation:' + scenario['scenarioGroup'],
                          messages=[{'role': 'user', 'content': prompt}],
                          max_tokens=args.max_tokens, temperature=1.0, json_mode=False,
                          thinking=args.thinking)
        text = answer['content'].strip()
        rows.append({'scenarioGroup': scenario['scenarioGroup'],
                     'split': scenario['split'], 'worldId': scenario['worldId'],
                     'actorId': scenario['actorId'], 'prompt': scenario['prompt'],
                     'text': text, 'finishReason': answer['finishReason'],
                     'usage': answer['usage'], 'estimatedCny': answer['estimatedCny'],
                     'latencyMs': answer['latencyMs'], 'requestId': answer['requestId']})
        print(scenario['scenarioGroup'], json.dumps(text, ensure_ascii=False))
    with output.open('w') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    print('wrote', output, 'calls', len(rows), 'spent', round(ledger.spent(), 6))


def run_check(args):
    config = read_config(args.env_file)
    ledger = Ledger(args.usage)
    worlds = json.loads((DATA / 'worlds.json').read_text())
    samples = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines() if line.strip()]
    if args.sample_id:
        wanted = set(args.sample_id)
        samples = [row for row in samples if row['sampleId'] in wanted]
    if args.source != 'all':
        samples = [row for row in samples if row['source'] == args.source]
    samples = samples[:args.limit]
    output = DATA / 'api' / ('checker-%s.jsonl' % args.tag)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        raise SystemExit('checker output already exists; pass --tag or --force')
    rows = []
    for sample in samples:
        prompt = checker_prompt(sample, worlds)
        try:
            answer = call_api(config, ledger, purpose='api_checker:' + sample['sampleId'],
                              messages=[{'role': 'user', 'content': prompt}],
                              max_tokens=args.max_tokens, temperature=0,
                              json_mode=True, thinking=args.thinking)
        except Exception as exc:
            rows.append({'sampleId': sample['sampleId'], 'status': 'request_error',
                         'error': type(exc).__name__})
            continue
        row = {'sampleId': sample['sampleId'], 'status': 'ok',
               'expected': sample['expected'], 'usage': answer['usage'],
               'estimatedCny': answer['estimatedCny'], 'latencyMs': answer['latencyMs'],
               'finishReason': answer['finishReason'], 'raw': answer['content']}
        try:
            parsed = parse_json(answer['content'])
            role, expr = assemble_audits(parsed, sample['text'])
            result = checkers.check_once(sample['text'], sample['steps'], role, expr,
                                         worlds[sample['worldId']], sample['actorId'])
            row.update({'parsed': True, 'decision': result.decision,
                        'codes': sorted({issue['code'] for issue in result.issues}),
                        'issues': [dict(issue) for issue in result.issues],
                        'reason': result.reason,
                        'm1': checkers.validate_role_audit(
                            sample['text'], sample['steps'], role, worlds[sample['worldId']],
                            sample['actorId']).decision,
                        'm2': checkers.validate_expression_audit(
                            sample['text'], sample['steps'], expr).decision})
        except Exception as exc:
            row.update({'parsed': False, 'error': type(exc).__name__ + ':' + str(exc)[:200]})
        rows.append(row)
        print(sample['sampleId'], row.get('decision'), row.get('codes'), row.get('error', ''))
    with output.open('w') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    summary(rows, ledger, output)


def summary(rows, ledger, output):
    parsed = [row for row in rows if row.get('parsed')]
    exact = [row for row in parsed if row.get('decision') == row['expected']['combined']]
    false_accept = [row for row in parsed if row.get('decision') == 'accept'
                    and row['expected']['combined'] != 'accept']
    data = {
        'schema': 'jity-d02-api-checker-run-v1',
        'requests': len(rows), 'parsed': len(parsed), 'exactDecision': len(exact),
        'falseAccepts': len(false_accept),
        'falseAcceptIds': [row['sampleId'] for row in false_accept],
        'spentCny': round(ledger.spent(), 6),
        'usage': {
            'promptTokens': sum(row.get('usage', {}).get('prompt_tokens', 0) for row in rows),
            'completionTokens': sum(row.get('usage', {}).get('completion_tokens', 0) for row in rows),
            'totalTokens': sum(row.get('usage', {}).get('total_tokens', 0) for row in rows),
        },
        'latencyMs': sorted(row.get('latencyMs', 0) for row in rows),
        'results': [{key: row.get(key) for key in
                     ('sampleId', 'status', 'parsed', 'decision', 'expected',
                      'codes', 'error', 'finishReason', 'latencyMs')} for row in rows],
    }
    out = output.with_suffix('.summary.json')
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print('summary', out, json.dumps({k: data[k] for k in
          ('requests', 'parsed', 'exactDecision', 'falseAccepts', 'spentCny', 'usage')},
          ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('generate', 'check', 'summary'))
    parser.add_argument('--env-file', type=Path,
                        default=Path(os.environ.get('D02_ENV_FILE', '')) if os.environ.get('D02_ENV_FILE') else None)
    parser.add_argument('--usage', type=Path, default=DEFAULT_USAGE)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--source', choices=('all', 'assistant_authored_targeted', 'api_first_output'),
                        default='assistant_authored_targeted')
    parser.add_argument('--sample-id', action='append')
    parser.add_argument('--tag', default='r1')
    parser.add_argument('--max-tokens', type=int, default=3000)
    parser.add_argument('--thinking', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if args.mode in ('generate', 'check') and not args.env_file:
        raise SystemExit('--env-file or D02_ENV_FILE is required')
    if args.mode == 'generate':
        run_generate(args)
    elif args.mode == 'check':
        run_check(args)
    else:
        rows = [json.loads(line) for line in (DATA / 'api' / ('checker-%s.jsonl' % args.tag)).read_text().splitlines()]
        summary(rows, Ledger(args.usage), DATA / 'api' / ('checker-%s.jsonl' % args.tag))


if __name__ == '__main__':
    main()
