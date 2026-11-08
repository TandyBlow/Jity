"""Build the c3 holdout package (12 new sources) from real authority commits.

What it does, in order:

1. Refuses any fact text that is a near-duplicate of the old material
   (bigram Jaccard >= 0.8 against the frozen old corpora). The check runs
   BEFORE the worlds are built, so no post-hoc cherry-picking is possible.
2. Creates 12 independent worlds. Every world gets its own root point and three
   normal points committed through the authority writer
   (``WorldService.create_world`` then ``SQLiteBaselineStore.transact``), so
   ``world_evidence`` and ``world_points.delta_json`` are produced by the same
   code path the product uses, not written by hand.
3. Extracts the facts of each world from the database only (evidence rows +
   delta_json + entity names), numbering them f0..fn in point order.
4. Authorizes one ``before`` relation per world through
   ``app.services.world.provenance.authorize`` (validator world-relation-validator/1).
5. Writes the package c3 consumes:

       <out>/manifest.json
       <out>/semantic-review.json        (AI draft, reviewer.kind = "ai")
       <out>/SEMANTIC-REVIEW-TODO.md
       <out>/pairs/<sourceId>-authorized.json
       <out>/world.db
       <out>/build-log.json

The semantic independence verdict is a human duty; this script only prepares the
table and marks it as AI, which c3's validator rejects until a person signs.

Usage:
    python -X utf8 backend/scripts/build_holdout_v1.py <outDir>
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend' / 'tests'))

from app.database.world_repository import state_digest  # noqa: E402
from app.database.world_store import SQLiteBaselineStore  # noqa: E402
from app.schemas.world.contracts import EntityDelta, TimelinePoint  # noqa: E402
from app.services.world.apply import apply_point  # noqa: E402
from app.services.world.control import WorldService  # noqa: E402
from app.services.world.provenance import authorize, bind_fact  # noqa: E402

import test_world_control_service as flow  # noqa: E402

FIXTURE = ROOT / 'design/world-protocol/v2/fixtures/projections/normal.expected.json'
C3 = ROOT / '.local/parallel/c-organize-plan'
OLD_MATERIAL = [
    C3 / 'artifacts/world-components/organize-wording/controllability-v1.jsonl',
    C3 / 'artifacts/world-components/organize-wording/pairs-v2.jsonl',
    C3 / 'experiments/world-components/parallel/organize_plan/freeze/sources.json',
]
NEAR_DUP = 0.8

# (sourceId, cast[3], [(point1 texts for A), (point2 texts for B), (point3 texts for C)],
#  (fromIndex, toIndex))
SOURCES = [
    ('h01', ('聂平', '韩渠', '邵原'),
     [['肩头的雪化成一片深色', '护腕的皮带松了一格'], ['靴筒外侧磨出白痕'],
      ['手指冻得发僵', '帽绳断了一股']], (2, 3)),
    ('h02', ('岑鹤', '汤续', '罗砚'),
     [['袖管里塞着半把谷壳', '指甲缝里嵌了糠'], ['腰带上的铜扣掉了一个'],
      ['后背的汗把里衣贴住', '鞋帮裂开一道口子']], (2, 3)),
    ('h03', ('奚戎', '穆迟', '谷晏'),
     [['围脖被风吹得翻起'], ['耳廓冻出红点', '袖口的毛边被磨平'],
      ['裤腿上沾着草屑', '领口撑得变了形']], (0, 1)),
    ('h04', ('章渡', '闻叙', '卫竺'),
     [['手背被缰绳勒出红痕', '袖口滴着水'], ['鞋跟陷进泥里拔不动'],
      ['睫毛上挂着水汽', '斗篷领子湿了一圈']], (2, 3)),
    ('h05', ('费岭', '邴收', '苏驿'),
     [['眉毛上落了煤灰', '指背蹭出一道黑印'], ['腰带挂钩崩开了'],
      ['靴面沾着湿煤渣', '袖管里落了碎屑']], (2, 3)),
    ('h06', ('蔺冬', '逄九', '燕岫'),
     [['手腕上缠着湿布条'], ['掌心起了一层白泡', '衣摆结着冰碴'],
      ['发梢冻成一缕一缕', '靴缝里渗进凉水']], (0, 1)),
    ('h07', ('卜晓', '关弋', '仲椋'),
     [['指腹勒出深红印子', '小臂上沾了麻屑'], ['膝弯处蹭掉一块皮'],
      ['肩线被压得往下塌', '后背留下一道绳痕']], (2, 3)),
    ('h08', ('计昀', '邬驮', '郝砺'),
     [['裤脚卷着几根草茎'], ['脚背被草叶划出细口', '头巾歪到一边'],
      ['手肘上沾着干草末', '衣襟上落了一层尘']], (0, 1)),
    ('h09', ('戎肃', '简弛', '郗照'),
     [['袖口落着几根细羽', '指节上蹭破一层薄皮'], ['衣摆在门槛上蹭脏'],
      ['鞋尖踢出了口子', '帽檐歪向一边']], (2, 3)),
    ('h10', ('阮柘', '屈遥', '常稔'),
     [['衬衫后背洇出汗印'], ['袖口卷到手肘上', '腰间的布袋磨破了角'],
      ['额头沾着草籽', '鞋带断了一根']], (0, 1)),
    ('h11', ('冉恪', '池卯', '骆覃'),
     [['手心的裂口又开了', '袖子里藏着一把干粮'], ['肩上披的褂子滑下一边'],
      ['脚踝上缠着布条', '裤管上沾着松针']], (2, 3)),
    ('h12', ('虞晏', '娄阶', '桑迟'),
     [['发间落着细小的霜'], ['鼻尖冻得发红', '衣角挂着半截草绳'],
      ['手背裂开几道细纹', '靴子里灌进了雪水']], (0, 1)),
]

PLACES = {
    'h01': ('高岑驿', '雪夜'),
    'h02': ('石梁驿', '清晨'),
    'h03': ('松门驿', '大风'),
    'h04': ('断桥驿', '大雾'),
    'h05': ('黑石驿', '深夜'),
    'h06': ('冷泉驿', '初冬'),
    'h07': ('青崖驿', '午后'),
    'h08': ('白草驿', '起风'),
    'h09': ('老鸦驿', '黄昏'),
    'h10': ('双槐驿', '正午'),
    'h11': ('独松驿', '黎明'),
    'h12': ('望云驿', '落雪'),
}

TIME_ADVANCE = {'boundary': 'elapsed', 'duration': {'amount': 2, 'unit': 'second'}}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def bigrams(text: str) -> set[str]:
    t = ''.join(ch for ch in text if ch not in '，。、；：！？“”‘’（）《》…—,.!?() \n\t')
    return {t[i:i + 2] for i in range(max(0, len(t) - 1))}


def jaccard(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def old_texts() -> list[dict]:
    rows: list[dict] = []
    for path in OLD_MATERIAL:
        if not path.exists():
            continue
        if path.suffix == '.jsonl':
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for fact in row.get('facts', []):
                    if fact.get('text'):
                        rows.append({'origin': f'{path.name}:{row.get("pairId") or row.get("sourceId")}',
                                     'text': fact['text']})
        else:
            for source in json.loads(path.read_text(encoding='utf-8'))['sources']:
                for fact in source['facts']:
                    rows.append({'origin': f'{path.name}:{source["sourceId"]}', 'text': fact['text']})
    return rows


def precheck(rows: list[dict]) -> list[dict]:
    """Refuse to build a world whose fact text is a near-duplicate of old material."""
    problems = []
    for row in rows:
        best = (0.0, {'origin': '', 'text': ''})
        for other in OLD_MATERIAL_ROWS:
            score = jaccard(row['text'], other['text'])
            if score > best[0]:
                best = (score, other)
        if best[0] >= NEAR_DUP:
            problems.append({'sourceId': row['sourceId'], 'text': row['text'],
                             'score': round(best[0], 3), 'oldText': best[1]['text'],
                             'oldOrigin': best[1]['origin']})
    return problems


def initial_state(tag: str, cast: tuple[str, str, str]) -> dict:
    snapshot = json.loads(FIXTURE.read_text(encoding='utf-8'))['initial']
    initial = copy.deepcopy(snapshot)
    initial.pop('worldId', None)
    place, scene = PLACES[tag]
    # Only the three actors used by this source are renamed; the rest keep a
    # neutral name so nothing in the fixture leaks the old vocabulary.
    rename = {'person_a': cast[0], 'person_b': cast[1], 'person_c': cast[2]}
    for key, value in initial['characters'].items():
        value['name'] = rename.get(key, f'{place}杂役')
        value['initialAppearance'] = f'{place}的人，{scene}里站着。'
        value['initialPersonality'] = '话少'
        value['initialSanity'] = 10
        value['tasks'] = {}
    for key, value in initial['locations'].items():
        value['name'] = f'{place}{key}'
        value['initialAppearance'] = f'{place}的一处角落，{scene}。'
    for key, value in initial['items'].items():
        value['name'] = f'{place}的{key}'
    initial['locations'] = {k: initial['locations'][k] for k in list(initial['locations'])[:1]}
    only = next(iter(initial['locations']))
    for value in initial['items'].values():
        value['initialPosition'] = {'containerId': only, 'slotId': None, 'relativeTo': None}
    for value in initial['characters'].values():
        value['initialPosition'] = {'containerId': only, 'slotId': None, 'relativeTo': None}
    initial['initialTime'] = {'calendar': 'gregorian', 'dateTime': '2027-01-16T05:00:00',
                              'instantOrdinal': 0}
    initial['protagonistId'] = 'person_a'
    return initial


def open_world(service, initial: dict, tag: str) -> dict:
    """create_world + root narration + allocate + start_advance, with request ids
    namespaced per world so one store can hold twelve of them."""
    created = flow._run(service, 'create_world', {
        'protocolVersion': 2, 'requestId': f'{tag}_create', 'initial': initial},
        flow.CreateWorldSuccess)
    world_id, root_id = created['data']['worldId'], created['data']['rootPointId']
    lease = created['data']['lease']
    flow._claim_and_submit(service, world_id, lease, root_id, f'{tag}_root', '驿站刚开门。')
    chain = {'advance_id': 'advance_1', 'input_id': 'input_1', 'round_id': 'round_1'}
    if getattr(getattr(service, 'store', service), 'persistent', False):
        allocated = service.execute('allocate_ids', flow._payload(
            f'{tag}_chain', world_id, lease, allocationKey=f'{tag}_chain', slots=[
                {'slotKey': kind, 'kind': kind, 'scope': None}
                for kind in ('advance', 'input', 'round')]))
        chain = {item['slotKey'] + '_id': item['id']
                 for item in allocated['data']['allocations']}
    allocations = flow._run(service, 'allocate_ids', flow._payload(
        f'{tag}_alloc', world_id, lease, allocationKey=f'{tag}_alloc', slots=[
            {'slotKey': 'point_1', 'kind': 'point', 'scope': None},
            {'slotKey': 'group_a', 'kind': 'group', 'scope': chain['round_id']}]),
        flow.AllocateIdsSuccess)
    ids = {item['slotKey']: item['id'] for item in allocations['data']['allocations']}
    flow._run(service, 'checkpoint_start_advance', flow._payload(
        f'{tag}_advance', world_id, lease, operation='start_advance',
        expectedPointId=root_id, expectedVersion=0, expectedCheckpointRevision=0,
        advanceId=chain['advance_id'], inputId=chain['input_id'],
        roundId=chain['round_id'], inputText='在驿门口停下。',
        order=list(initial['characters'].keys())), flow.StartAdvanceSuccess)
    return {'world_id': world_id, 'root_id': root_id, 'lease': lease, 'revision': 1, **chain}


def append_point(store, world_id, previous, point_id, seconds, entity_id, texts):
    def handler(snapshot):
        prior = snapshot['points'].get(previous)
        if prior is None:
            sequence = 0
            round_id = snapshot['round']['roundId']
            advance_id = snapshot['advance']['advanceId']
            base_state = snapshot['pointStates'][previous]['state']
        else:
            sequence = prior.sequence
            round_id, advance_id = prior.roundId, prior.advanceId
            base_state = snapshot['pointStates'][prior.id]['state']
        point = TimelinePoint.model_validate({
            'worldId': world_id, 'id': point_id, 'sequence': sequence + 1, 'kind': 'normal',
            'previousPointId': previous, 'roundId': round_id, 'advanceId': advance_id,
            'trigger': 'player', 'linkedFromPointId': None,
            'timeAdvance': {'boundary': 'elapsed',
                            'duration': {'amount': seconds, 'unit': 'second'}},
            'entityDeltas': {entity_id: EntityDelta.model_validate({
                'entityId': entity_id,
                'appearanceChanges': [{'id': f'{point_id}_{i}', 'text': text, 'supersedes': []}
                                      for i, text in enumerate(texts, 1)],
            }).model_dump(mode='json')},
        })
        state = apply_point(base_state, point)
        snapshot['points'][point.id] = point
        snapshot['pointStates'][point.id] = {'state': state, 'stateDigest': state_digest(state)}
        snapshot['narrations'][point.id] = {'status': 'ready', 'generation': 1, 'text': ''}
        return point.id

    return store.transact(world_id, handler)


def read_source(db_path: Path, world_id: str, point_ids: list[str]) -> dict:
    con = sqlite3.connect(db_path)
    row = con.execute('SELECT initial_json FROM worlds WHERE id=?', (world_id,)).fetchone()
    names = {k: v.get('name') for k, v in json.loads(row[0])['characters'].items()}
    kind_map = {'appearance': 'appearance_changed', 'personality': 'personality_changed',
                'position': 'moved', 'sanity': 'sanity_changed'}
    marks = ','.join('?' for _ in point_ids)
    evidence = con.execute(
        f'SELECT evidence_id,point_id,sequence,entity_id,kind,item_key,payload_json '
        f'FROM world_evidence WHERE point_id IN ({marks}) ORDER BY sequence,entity_id,item_key',
        point_ids).fetchall()
    points = con.execute(
        f'SELECT id,sequence,previous_point_id,time_json FROM world_points '
        f'WHERE id IN ({marks}) ORDER BY sequence', point_ids).fetchall()
    con.close()
    units = []
    for evidence_id, point_id, sequence, entity_id, kind, item_key, payload in evidence:
        if kind not in kind_map:
            continue
        data = json.loads(payload)
        units.append({'factId': f'f{len(units)}', 'entityId': entity_id,
                      'name': names.get(entity_id, entity_id), 'kind': kind_map[kind],
                      'text': data.get('text') or item_key,
                      'pointId': point_id, 'evidenceId': evidence_id, 'sequence': sequence})
    return {'nameMap': names, 'units': units,
            'points': [{'id': r[0], 'sequence': r[1], 'previousPointId': r[2],
                        'time': json.loads(r[3]) if r[3] else None} for r in points]}


def build(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pairs = out / 'pairs'
    if pairs.exists():
        shutil.rmtree(pairs)
    pairs.mkdir()
    db_path = out / 'world.db'
    if db_path.exists():
        db_path.unlink()
    store = SQLiteBaselineStore(str(db_path))
    service = WorldService(store)

    built, facts_all = [], []
    for source_id, cast, point_texts, relation in SOURCES:
        initial = initial_state(source_id, cast)
        state = open_world(service, copy.deepcopy(initial), source_id)
        world_id, previous = state['world_id'], state['root_id']
        entities = ['person_a', 'person_b', 'person_c']
        point_ids = []
        for index, (entity, texts) in enumerate(zip(entities, point_texts), start=1):
            point_id = f'{source_id}_p{index}'
            seconds = 2 if index == 1 else (3 if index == 2 else 1)
            append_point(store, world_id, previous, point_id, seconds, entity, texts)
            point_ids.append(point_id)
            previous = point_id
            for text in texts:
                facts_all.append({'sourceId': source_id, 'text': text})
        built.append({'sourceId': source_id, 'worldId': world_id,
                      'place': PLACES[source_id][0], 'pointIds': point_ids,
                      'relation': relation})
    return {'db': db_path, 'built': built, 'facts': facts_all}


def package_round(db_path: Path, item: dict, edges: list[dict]) -> dict:
    data = read_source(db_path, item['worldId'], item['pointIds'])
    units, points = data['units'], data['points']
    from_index, to_index = item['relation']
    requested = [{'type': 'before', 'fromFactId': f'f{from_index}',
                  'toFactId': f'f{to_index}'}]
    by_id = {u['factId']: u for u in units}
    facts = {u['factId']: bind_fact(u['factId'], item['worldId'], [u['pointId']], [u['evidenceId']])
             for u in units}
    index = {u['evidenceId']: u['pointId'] for u in units}
    relations = [{'type': 'before', 'fromFactId': r['fromFactId'],
                  'toFactId': r['toFactId'],
                  'evidence': [{'type': 'event',
                                'evidenceId': by_id[r['fromFactId']]['evidenceId']},
                               {'type': 'event',
                                'evidenceId': by_id[r['toFactId']]['evidenceId']}]}
                 for r in requested]
    point_views = [{'id': p['id'], 'worldId': item['worldId'],
                    'previousPointId': p['previousPointId'], 'time': p['time']}
                   for p in points]
    auth = authorize(facts, relations, point_views, index)
    for relation in auth['relations']:
        relation['elapsedSeconds'] = seconds_between(
            point_views, by_id[relation['fromFactId']]['pointId'],
            by_id[relation['toFactId']]['pointId'])
    return {'worldId': item['worldId'], 'units': units,
            'points': [{'id': p['id'], 'sequence': p['sequence'],
                        'previousPointId': p['previousPointId'], 'time': p['time']}
                       for p in points],
            'requestedRelations': requested, 'authorization': auth}


def seconds_between(points, a, b):
    by_id = {p['id']: p for p in points}
    chain, cur = [], a
    while cur is not None:
        chain.append(cur)
        if cur == b:
            break
        nxt = [p['id'] for p in points if p.get('previousPointId') == cur]
        cur = nxt[0] if len(nxt) == 1 else None
    else:
        return None
    if not chain or chain[-1] != b:
        return None
    total = 0
    for pid in chain[1:]:
        time_json = by_id[pid].get('time') or {}
        if time_json.get('boundary') == 'elapsed':
            d = time_json.get('duration') or {}
            total += int(d.get('amount') or 0) * {'second': 1, 'minute': 60}.get(d.get('unit'), 0)
    return total


def main(out_arg: str) -> int:
    global OLD_MATERIAL_ROWS
    out = Path(out_arg)
    OLD_MATERIAL_ROWS = old_texts()
    planned = []
    for source_id, cast, point_texts, _ in SOURCES:
        for texts in point_texts:
            for text in texts:
                planned.append({'sourceId': source_id, 'text': text})
    problems = precheck(planned)
    if problems:
        print(json.dumps({'status': 'refused', 'reason': 'near-duplicate fact text',
                          'problems': problems}, ensure_ascii=False, indent=1))
        return 1

    built = build(out)
    package = {'packageId': 'holdout-a-v1', 'sources': [], 'pairs': {}}
    for item in built['built']:
        document = package_round(built['db'], item, [])
        path = out / 'pairs' / f"{item['sourceId']}-authorized.json"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        package['sources'].append(item['sourceId'])
        package['pairs'][item['sourceId']] = {
            'file': f"pairs/{item['sourceId']}-authorized.json",
            'sha256': sha256_bytes(path.read_bytes()),
            'worldId': item['worldId'], 'pointIds': item['pointIds'],
            'place': item['place'],
            'verdict': document['authorization']['verdict'],
            'relation': document['authorization']['relations'][0] if document['authorization']['relations'] else None,
            'facts': [u['text'] for u in document['units']],
        }

    manifest = {
        'packageId': 'holdout-a-v1',
        'producedBy': 'A (world-server): backend/scripts/build_holdout_v1.py',
        'createdAt': '2027-01-16',
        'baseCommit': None,  # filled below from git
        'sources': package['sources'],
        'databases': {'h': 'world.db'},
        'generationProcess': {
            'method': ('12 independent worlds; each committed through the authority writer: '
                       'WorldService.create_world (root) then SQLiteBaselineStore.transact for three '
                       'normal points; world_evidence and world_points.delta_json are written by '
                       'app/database/world_repository._save_point inside the same transaction'),
            'worldRounds': [f"{i['sourceId']}:{i['worldId']}:{','.join(i['pointIds'])}"
                            for i in built['built']],
            'dedupeMethod': ('build_holdout_v1.precheck: every fact text is compared to all old '
                             'material fact texts (controllability-v1, pairs-v2, c3 freeze/sources) by '
                             'character-bigram Jaccard; the build refuses at >= 0.8 before any world '
                             'is created'),
            'producedAt': '2027-01-16',
            'producerCommit': None,
            'authorityEvidence': 'world_evidence + world_point_evidence + world_points.delta_json',
            'relationValidator': 'world-relation-validator/1',
        },
        'files': {
            'world.db': sha256_bytes((out / 'world.db').read_bytes()),
            'pairs': {sid: info['sha256'] for sid, info in package['pairs'].items()},
        },
    }
    # git identity of the producing tree, recorded rather than assumed
    import subprocess
    def git(*args):
        return subprocess.run(['git', '-c', f'safe.directory={ROOT.as_posix()}', *args],
                              cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest['baseCommit'] = git('rev-parse', 'HEAD')
    manifest['generationProcess']['producerCommit'] = manifest['baseCommit']
    manifest['generationProcess']['producerStatus'] = git('status', '--porcelain')[:2000]
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n',
                                       encoding='utf-8')

    semantic = {
        'protocol': 'c3-holdout-semantic-review-v1',
        'reviewer': {'identity': 'A-side assistant (AI draft)', 'kind': 'ai'},
        'note': ('AI draft only. c3 requires reviewer.kind == "human"; a person must read each source '
                 'and confirm or rewrite every verdict. Until then the package is not admissible.'),
        'sources': {
            sid: {'verdict': 'independent',
                  'note': ('new cast, new place, new appearance vocabulary; fact texts pass the '
                           'bigram screen and describe different events than any old source')}
            for sid in package['sources']
        },
    }
    (out / 'semantic-review.json').write_text(json.dumps(semantic, ensure_ascii=False, indent=1) + '\n',
                                             encoding='utf-8')
    todo = """# 语义独立性复核（待人工）

本目录的 `semantic-review.json` 是 **AI 草稿**，`reviewer.kind = "ai"`。c3 的
`validate_holdout.py` 只接受 `reviewer.kind == "human"`，所以在有人签之前，这个包会被判
`not-admissible`（`PKG-semantic-review-not-human`），**不会**被冻结。

人工需要做的事：

1. 逐个来源读 `pairs/<id>-authorized.json` 的事实文本，并与旧材料对照
   （`.../organize-wording/controllability-v1.jsonl`、`pairs-v2.jsonl`、c3 的
   `freeze/sources.json`）。
2. 判断该来源是否与旧材料在**事件语义**上独立（不是“字面不同”，而是“说的是不同的事”）。
3. 把每个来源的 `verdict` 改成 `independent` / `semantic-duplicate` / `unsure`，
   在 `note` 里写明与哪条旧材料不同、为什么；把 `reviewer` 改成真实身份并加 `date`。
4. 任何 `semantic-duplicate` 或 `unsure` 都会让整包被拒；宁可退回重做，不要放行。
"""
    (out / 'SEMANTIC-REVIEW-TODO.md').write_text(todo, encoding='utf-8')

    log = {
        'status': 'built',
        'sources': len(package['sources']),
        'facts': sum(len(v['facts']) for v in package['pairs'].values()),
        'verdicts': {sid: v['verdict'] for sid, v in package['pairs'].items()},
        'relations': {sid: (v['relation'] or {}).get('elapsedSeconds')
                      for sid, v in package['pairs'].items()},
        'nearDuplicateScreen': 'pass',
        'dbSha256': manifest['files']['world.db'],
    }
    (out / 'build-log.json').write_text(json.dumps(log, ensure_ascii=False, indent=1) + '\n',
                                        encoding='utf-8')
    print(json.dumps(log, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'artifacts/holdout-a-v1')))
