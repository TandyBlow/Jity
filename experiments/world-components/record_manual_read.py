"""Record the manual reading of the rows the first pass did not flag.

A machine check that finds nothing is not the same as a clean pair: the earlier
sample of 41 unflagged rows still found 5 carrying a small unlicensed detail. So
every unflagged row was read against its own fact, in three passes (41 sampled,
then the remaining 164). Rows that share a target string but sit on different
facts were read separately as (fact, target) pairs.

Three outcomes are recorded:

  ok      the target states its fact and adds nothing the unit does not license
  note    the target states its fact but adds a small detail (an extra motion, an
          unfixed quantity, a synonym); kept, because it does not change the fact
  defect  the target contradicts the format rule or the fact; fixed in
          audit_decisions.DECISIONS

Output: artifacts/target-audit-r1/manual-read-r1.json
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
OUT = WORKTREE / 'artifacts/target-audit-r1/manual-read-r1.json'
DECISIONS = WORKTREE / 'artifacts/target-audit-r1/decisions-r1.json'

# target text -> (outcome, reason); applies to every row that carries that target
NOTES = {
    '阿棠从早市过来，抱着一叠干纸进了档案馆。': ('note', '“抱着一叠干纸”是事实外的随身物；移动事实本身完整'),
    '韩渡蹲下去，把松脱的钟绳一圈一圈重新系紧。': ('note', '“蹲下去”是事实外动作'),
    '顾行舟直起身，手上的茧被水泡得发白。': ('note', '“直起身”是事实外动作'),
    '韩渡从潮渡上来，蹲到雾堤的钟架下。': ('note', '“蹲到钟架下”是到达后的动作'),
    '叶知微的袖口沾了一层铜油。': ('note', '“一层”是事实外的数量'),
    '沈砚照着旧墨迹，把潮汐簿缺的那页补全了。': ('note', '“照着旧墨迹”不在可见物件里，但不改变补全这一事实'),
    '沈砚从潮渡回来，走进旧灯塔的石阶。': ('note', '“回来”带返回义；石阶是旧灯塔的子地点'),
    '沈砚掀开旧纸，从抽屉底下摸出备用钥匙。': ('note', '“旧纸”不在可见清单；“抽屉底下”与事实“抽屉底层”略有出入'),
    '韩渡抬起头，眉毛上挂着的雾水往下滴。': ('note', '用“往下滴”表达事实里的“更重”'),
    '沈砚翻纸时，袖口蹭上一道墨痕。': ('note', '“墨痕”与事实里的“墨”同义'),
    '他等了一会儿，场景里没有新的变化。': ('defect', '目标里用了字段名“场景”，要求写的是不写字段名'),
}
DEFECTS = {target for target, (outcome, _) in NOTES.items() if outcome == 'defect'}


def main():
    decisions = json.loads(DECISIONS.read_text(encoding='utf-8'))['records']
    read = [row for row in decisions if row['verdict'] == 'machine-clean' or
            (row['verdict'] == 'banned' and row['original'] in DEFECTS)]
    records, counts = [], {}
    for row in read:
        outcome, reason = NOTES.get(row['original'], ('ok', ''))
        records.append({'pool': row['pool'], 'id': row['id'], 'fact': row['fact'],
                        'target': row['original'], 'outcome': outcome, 'reason': reason,
                        'fixedTo': row['revised'] if outcome == 'defect' else None})
        counts[outcome] = counts.get(outcome, 0) + 1
    assert len(records) == 205, len(records)
    assert counts.get('defect') == 5, counts
    body = {'rows': len(records),
            'method': 'first pass took every fifth row of this list (41); the remaining 164 were read after '
                      'that sample showed a small extra detail in 5 of 41. Pairs sharing a target string but '
                      'sitting on different facts were read separately.',
            'counts': dict(sorted(counts.items())),
            'noteOnNotes': 'note rows keep their targets: the detail does not change the fact. They are recorded '
                           'so a later arm can decide whether such tails should also be deleted.',
            'records': records}
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: body[k] for k in ('rows', 'counts')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
