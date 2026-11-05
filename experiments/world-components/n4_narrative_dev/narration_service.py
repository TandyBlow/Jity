"""Local resident narration service (standalone; not part of the world router).

One model load, serial requests, whole-round API and a single-fact debug API.

Reused as-is:
  * ``fact_contract`` for canonical fact serialization,
  * the authoritative relation verdict that ships inside each round payload
    (produced by the server-side validator; this service never re-decides),
  * the existing two-layer edit (``n4_pipeline.two_layer_edit``).

Quality is reported as ``unverified``: the automatic repetition scan is a hint
only and never promotes a round to "quality passed".
"""
import argparse
import json
import pathlib
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

import fact_contract as FC  # noqa: E402
import n4_pipeline as P  # noqa: E402
from sequence_policy import generate_greedy  # noqa: E402

SERVICE_VERSION = 'narration-service/1'
AUTO_REPEAT = None


def init_repeat_pattern():
    global AUTO_REPEAT
    import re
    AUTO_REPEAT = re.compile(r'(.{2,6})[,，]\1')


class Engine:
    """Loads u240 once and answers one request at a time."""

    def __init__(self, model_dir, rounds_dir):
        import torch
        from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
        from transformers.models.t5.tokenization_t5 import T5Tokenizer

        started = time.perf_counter()
        self.torch = torch
        self.tokenizer = T5Tokenizer.from_pretrained(model_dir, legacy=False,
                                                    local_files_only=True)
        self.model = T5ForConditionalGeneration.from_pretrained(
            model_dir, torch_dtype=torch.float32)
        self.device = 'cpu'
        self.model.to(self.device).eval()
        self.cold_start_seconds = round(time.perf_counter() - started, 3)
        # 调用计数：用来核对“预算到期后不再启动下一条事实”
        self.calls = {'encoder': 0, 'decoder': 0}
        self.model.register_forward_hook(self._count_decoder)
        self.model.get_encoder().register_forward_hook(self._count_encoder)
        self.lock = threading.Lock()
        self.rounds_dir = pathlib.Path(rounds_dir)
        init_repeat_pattern()

    def _count_encoder(self, *_args, **_kwargs):
        self.calls['encoder'] += 1

    def _count_decoder(self, *_args, **_kwargs):
        self.calls['decoder'] += 1

    def call_counts(self):
        return dict(self.calls)

    # ---- rounds ---------------------------------------------------------
    def round_ids(self):
        return sorted(p.stem.replace('-authorized', '')
                      for p in self.rounds_dir.glob('*-authorized.json'))

    def load_round(self, round_id):
        path = self.rounds_dir / f'{round_id}-authorized.json'
        if not path.exists():
            raise KeyError(round_id)
        return json.loads(path.read_text(encoding='utf-8'))

    # ---- generation -----------------------------------------------------
    def generate_fact(self, unit, budget):
        fact = {'kind': unit['kind'], 'name': unit['name'], 'text': unit['text']}
        line = FC.serialize_fact(fact)
        FC.check_line(unit['kind'], line)
        header = ('短句任务。'
                  + chr(10) + '地点=潮汐档案馆>长桌'
                  + chr(10) + '地点可见=潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌'
                  + chr(10) + '场景=夜；浓雾'
                  + chr(10) + '视角={pov}；第三人称').format(pov=unit['name'])
        prompt = header + chr(10) + '事实=' + line + chr(10) + '短句：' + chr(10)
        before = self.call_counts()
        started = time.perf_counter()
        enc = self.tokenizer(prompt, return_tensors='pt', truncation=False).to(self.device)
        with self.torch.inference_mode():
            ids, meta = generate_greedy(self.model, enc, budget)
        text = self.tokenizer.decode(ids[0], skip_special_tokens=True)
        after = self.call_counts()
        return {'text': text, 'complete': bool(meta['complete']),
                'seconds': round(time.perf_counter() - started, 3), 'factLine': line,
                'calls': {'encoder': after['encoder'] - before['encoder'],
                          'decoder': after['decoder'] - before['decoder']}}

    @staticmethod
    def assemble(units, rows, verdict, person_names):
        """按结构化单元装配正文：缺口保留边界，缺口两侧不合并、不连接。

        - 只有“完成且非空”的单元进入正文；
        - 缺口把事实序列切成若干连续段，每段独立做两层编辑；
        - 跨缺口的同主体合并不发生，跨缺口的关系连接也不发生；
        - 一段都没有时不产生任何占位标点。
        """
        runs, gaps, current = [], [], []
        seen = {}
        for index, (unit, row) in enumerate(zip(units, rows), start=1):
            usable = bool(row['complete']) and bool((row['text'] or '').strip())
            if usable:
                current.append(row)
                seen[row['factId']] = True
                continue
            if current:
                runs.append(current)
                current = []
            reason = ('not-started' if row.get('notStarted')
                      else ('timeout' if not row['complete'] else 'empty-output'))
            gaps.append({'factId': unit['factId'], 'name': unit['name'],
                         'position': index, 'reason': reason,
                         'partial': row['text']})
        if current:
            runs.append(current)

        segments, merge_ops, merge_dropped, connector_ops, connector_fallbacks =             [], [], [], [], []
        for index, run in enumerate(runs):
            ids = {row['factId'] for row in run}
            scoped = {'verdict': verdict.get('verdict'),
                      'relations': [r for r in verdict.get('relations', [])
                                    if r['fromFactId'] in ids and r['toFactId'] in ids]}
            produced = P.two_layer_edit(run, scoped, person_names)
            text = produced['text']
            if text and not text.endswith(('。', '！', '？')):
                text += '。'
            segments.append({'index': index, 'factIds': [row['factId'] for row in run],
                             'text': text})
            merge_ops += produced['mergeOps']
            merge_dropped += produced['mergeDropped']
            connector_ops += produced['connectorOps']
            connector_fallbacks += produced['connectorFallbacks']
        return {'text': ''.join(segment['text'] for segment in segments),
                'segments': segments, 'gaps': gaps,
                'empty': not segments,
                'mergeOps': merge_ops, 'mergeDropped': merge_dropped,
                'connectorOps': connector_ops,
                'connectorFallbacks': connector_fallbacks}

    def process_round(self, payload, budget, force_timeout=None):
        request_id = payload.get('requestId') or f'req-{int(time.time() * 1000)}'
        units = payload['units']
        for unit in units:
            unit.setdefault('worldId', payload['worldId'])
        assemble_started = time.perf_counter()
        references = [{k: unit.get(k) for k in ('factId', 'name', 'kind', 'text',
                                                'pointId', 'evidenceId')} for unit in units]
        assemble_seconds = round(time.perf_counter() - assemble_started, 6)

        rows, per_fact = [], []
        started = time.perf_counter()
        deadline = started + budget
        with self.lock:
            for unit in units:
                remaining = deadline - time.perf_counter()
                if unit['factId'] == force_timeout:
                    remaining = min(remaining, 0.05)
                if remaining <= 0:
                    # 整回合预算已到期：不再启动这一条，零模型调用
                    rows.append({'factId': unit['factId'], 'name': unit['name'],
                                 'kind': unit['kind'], 'text': '', 'complete': False,
                                 'notStarted': True})
                    per_fact.append({'factId': unit['factId'], 'name': unit['name'],
                                     'factLine': None, 'complete': False, 'seconds': 0.0,
                                     'notStarted': True,
                                     'calls': {'encoder': 0, 'decoder': 0}})
                    continue
                produced = self.generate_fact(unit, remaining)
                rows.append({'factId': unit['factId'], 'name': unit['name'],
                             'kind': unit['kind'], 'text': produced['text'],
                             'complete': produced['complete'], 'notStarted': False})
                per_fact.append({'factId': unit['factId'], 'name': unit['name'],
                                 'factLine': produced['factLine'],
                                 'complete': produced['complete'],
                                 'seconds': produced['seconds'],
                                 'notStarted': False,
                                 'calls': produced['calls']})
        generate_seconds = round(time.perf_counter() - started, 3)

        incomplete = [row['factId'] for row in rows if not row['complete']]
        verdict = payload['authorization']
        if incomplete:
            verdict = dict(verdict)
            verdict['relations'] = [r for r in verdict['relations']
                                    if not ({r['fromFactId'], r['toFactId']} & set(incomplete))]

        edit_started = time.perf_counter()
        person_names = {u['name'] for u in units
                        if str(u.get('entityId', '')).startswith(('person_', 'char_'))}
        edited = self.assemble(units, rows, verdict, person_names)
        edit_seconds = round(time.perf_counter() - edit_started, 6)

        repeat_hints = [row['factId'] for row in rows if AUTO_REPEAT.search(row['text'] or '')]
        return {
            'requestId': request_id,
            'service': SERVICE_VERSION,
            'components': {'pipeline': P.PIPELINE_VERSION, 'validator': P.VALIDATOR,
                           'relationEdit': P.RELATION_VERSION,
                           'conservativeEdit': P.EDIT_VERSION},
            'worldId': payload['worldId'],
            'facts': references,
            'generation': per_fact,
            'sourceComplete': not incomplete,
            'incompleteFacts': incomplete,
            'original': ''.join(u['text'] for u in units),
            'edited': edited['text'],
            'bodyEmpty': edited['empty'],
            'gaps': edited['gaps'],
            'edit': {'segments': edited['segments'],
                     'mergeOps': edited['mergeOps'],
                     'mergeDropped': edited['mergeDropped'],
                     'connectorOps': edited['connectorOps'],
                     'connectorFallbacks': edited['connectorFallbacks']},
            'authorization': {'verdict': verdict.get('verdict'),
                              'relations': verdict.get('relations', [])},
            'quality': {'status': 'unverified',
                        'repeatHints': repeat_hints,
                        'note': '自动重复检查只是提示；质量默认未核验'},
            'modelCalls': {'encoder': sum(f['calls']['encoder'] for f in per_fact),
                           'decoder': sum(f['calls']['decoder'] for f in per_fact)},
            'budgetSeconds': budget,
            'timing': {'assemble': assemble_seconds, 'generate': generate_seconds,
                       'edit': edit_seconds,
                       'serverTotal': round(assemble_seconds + generate_seconds
                                            + edit_seconds, 3)},
        }


def create_app(engine):
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title='Jity narration service', version=SERVICE_VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'],
                       allow_headers=['*'])
    app.state.engine = engine

    @app.get('/health')
    def health():
        return {'ok': True, 'service': SERVICE_VERSION,
                'coldStartSeconds': engine.cold_start_seconds,
                'device': engine.device, 'rounds': engine.round_ids()}

    @app.get('/rounds')
    def rounds():
        return {'rounds': engine.round_ids()}

    @app.get('/rounds/{round_id}')
    def get_round(round_id: str):
        try:
            return engine.load_round(round_id)
        except KeyError:
            raise HTTPException(status_code=404, detail='unknown round')

    @app.post('/rounds/{round_id}')
    def run_round(round_id: str, budget: float = Query(20.0, gt=0),
                  forceTimeout: str | None = Query(None)):
        try:
            payload = engine.load_round(round_id)
        except KeyError:
            raise HTTPException(status_code=404, detail='unknown round')
        return engine.process_round(payload, budget, forceTimeout)

    @app.post('/fact')
    def run_fact(body: dict, budget: float = Query(20.0, gt=0)):
        facts = body.get('facts') or []
        if len(facts) != 1:
            raise HTTPException(status_code=400, detail='single fact only')
        return engine.generate_fact(facts[0], budget)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=str(ROOT / '.local' / 'models'))
    parser.add_argument('--rounds', default=str(ROOT / 'artifacts' / 'world-provenance'))
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8031)
    args = parser.parse_args()
    import uvicorn
    engine = Engine(args.model, args.rounds)
    print(json.dumps({'service': SERVICE_VERSION,
                      'coldStartSeconds': engine.cold_start_seconds,
                      'rounds': engine.round_ids()}), flush=True)
    uvicorn.run(create_app(engine), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    raise SystemExit(main())
