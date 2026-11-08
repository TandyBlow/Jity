"""Render a private, self-contained question-bank review; never run a model."""
from __future__ import annotations

from collections import Counter
import html
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import quote


_LABELS = {
    "id": "题目 ID", "game_id": "所属游戏", "data_version": "数据版本",
    "checkpoint": "检查点", "kind": "题型", "category": "覆盖类别",
    "test_target": "测试目标", "chronology": "事实首次出现、更新与最近重提",
    "interval": "间隔及计算方法", "channels": "信息通道与近期窗口可见性",
    "validity": "有效期与歧义", "review": "人工复核事项",
    "unknown_audit": "不知道类题目的范围与线索审查",
    "acceptable_phrasings": "可接受表述", "required_points": "必要答案要点",
    "rubric": "评分规则与部分得分", "typical_errors": "典型错误",
    "action_index": "提交行动序号", "campaign_turn": "战役推进回合",
    "timeline_node": "时间线节点", "state_sha256": "状态 SHA-256",
    "checkpoint_sha256": "检查点规范化内容 SHA-256", "source_path": "原始证据路径",
    "frozen_path": "冻结证据路径", "json_pointer": "JSON 字段位置",
    "value_sha256": "字段值 SHA-256", "file_sha256": "原始文件 SHA-256",
}


def _text(value):
    return html.escape(str(value), quote=True)


def _pretty(value):
    return _text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _value(value):
    if isinstance(value, (dict, list)):
        return '<pre class="json">' + _pretty(value) + '</pre>'
    if value is None:
        return '<span class="muted">未提供</span>'
    return '<div class="prose">' + _text(value) + '</div>'


def _fields(record, exclude=()):
    return '<dl class="fields">' + ''.join(
        '<dt>' + _text(_LABELS.get(key, key)) + '</dt><dd>' + _value(value) + '</dd>'
        for key, value in record.items() if key not in exclude
    ) + '</dl>'


def _load(bank_dir, relative, required=False):
    path = bank_dir / relative
    if not path.exists() and not required:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _records(document, label):
    records = document.get("records") if isinstance(document, dict) else None
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(label + ".records 必须是对象列表")
    ids = [row.get("id") for row in records]
    if any(not isinstance(identifier, str) or not identifier for identifier in ids):
        raise ValueError(label + " 中每条记录必须有非空字符串 ID")
    if len(ids) != len(set(ids)):
        raise ValueError(label + " 中存在重复 ID")
    return records


def _detail(title, value, open_=False):
    return '<details class="detail"' + (' open' if open_ else '') + '><summary>' + _text(title) + '</summary>' + _value(value) + '</details>'


def _frozen_link(bank_dir, value):
    """Only link to existing files inside the bank, never arbitrary URLs/paths."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return ''
    candidate = (bank_dir / value).resolve()
    try:
        relative = candidate.relative_to(bank_dir)
    except ValueError:
        return ''
    if not candidate.is_file():
        return ''
    href = '../' + quote(relative.as_posix(), safe='/')
    return '<a class="file-link" href="' + _text(href) + '">打开冻结证据文件</a>'


def _evidence_html(bank_dir, identifier, evidence):
    if evidence is None:
        return '<div class="warning">证据引用不存在：' + _text(identifier) + '</div>'
    return (
        '<article class="evidence"><h4>' + _text(identifier) + '</h4>'
        '<div class="excerpt"><span class="small-label">最小必要摘录</span>'
        + _value(evidence.get('excerpt')) + '</div>'
        + _fields(evidence, exclude=('id', 'excerpt'))
        + _frozen_link(bank_dir, evidence.get('frozen_path')) + '</article>'
    )


def _source_table(dataset):
    games = dataset.get('games', []) if isinstance(dataset, dict) else []
    if not isinstance(games, list) or not games:
        return '<p class="muted">来源逐局审计未提供；不能据此认定来源已验收。</p>'
    rows = []
    for game in games:
        if not isinstance(game, dict):
            continue
        replay = game.get('strict_replay', game.get('replay', {}))
        replay = replay if isinstance(replay, dict) else {}
        rows.append('<tr>' + ''.join('<td>' + _text(value) + '</td>' for value in (
            game.get('game_id', game.get('id', '—')), game.get('status', '未提供'),
            game.get('submitted_actions', '—'), game.get('effective_campaign_turns', '—'),
            game.get('timeline_nodes_including_initial', '—'), replay.get('status', '未提供'),
            game.get('ending', '—'), game.get('eligibility', '未提供'),
        )) + '</tr>')
    return '<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + v + '</th>' for v in (
        '游戏', '录制状态', '提交行动', '有效推进', '节点（含初始）', '严格重放', '结局', '来源资格'
    )) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def render_report(bank_dir: Path) -> Path:
    """Read separated bank files and atomically write reports/review.html.

    This output intentionally contains private answers and audit evidence. It
    must never be used as model-visible input. Missing optional audit documents
    are shown explicitly; malformed required documents and duplicate IDs fail.
    """
    bank_dir = Path(bank_dir).resolve()
    questions_doc = _load(bank_dir, 'public/questions.json', required=True)
    answers_doc = _load(bank_dir, 'private/answers.json', required=True)
    items_doc = _load(bank_dir, 'audit/items.json', required=True)
    evidence_doc = _load(bank_dir, 'audit/evidence.json', required=True)
    questions = _records(questions_doc, 'public/questions.json')
    answers = {row['id']: row for row in _records(answers_doc, 'private/answers.json')}
    items = {row['id']: row for row in _records(items_doc, 'audit/items.json')}
    evidence = {row['id']: row for row in _records(evidence_doc, 'audit/evidence.json')}
    dataset = _load(bank_dir, 'audit/dataset.json')
    coverage = _load(bank_dir, 'coverage.json')
    candidates = _load(bank_dir, 'private/candidates.json')
    validation = _load(bank_dir, 'validation.json')
    game_ids = sorted({str(question.get('game_id', '未提供')) for question in questions})
    kinds = sorted({str(question.get('kind', '未提供')) for question in questions})
    cards = []
    for question in questions:
        identifier = question['id']
        answer = answers.get(identifier)
        audit = items.get(identifier)
        checkpoint = question.get('checkpoint') or {}
        checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
        title = question.get('question', '问题正文缺失')
        meta = '{} · {} · 行动 {} / 推进 {} / 节点 {}'.format(
            question.get('game_id', '未提供'), question.get('kind', '未提供'),
            checkpoint.get('action_index', '—'), checkpoint.get('campaign_turn', '—'),
            checkpoint.get('timeline_node', '—'))
        if audit:
            interval = audit.get('interval', {})
            visible = audit.get('channels', {})
            recent_label = {'none': '未出现答案', 'partial': '含部分答案', 'full': '含完整答案',
                            'no_known_answer': '原历史也未披露确切值'}.get(visible.get('recent_answer_coverage'), '待核')
            meta += ' · 最近公开重提后 {} 次行动 · 近期窗口：{}'.format(
                interval.get('since_last_public_mention_actions', '—'), recent_label)
        body = '<div class="question-text"><span class="small-label">模型可见问题</span>' + _value(title) + '</div>'
        if answer is None:
            body += '<div class="warning">此题私有标准答案缺失，请复核。</div>'
        else:
            body += '<div class="gold"><span class="small-label">私有标准答案 · 尚待人工审阅</span>' + _value(answer.get('answer')) + '</div>'
            body += '<div class="two-col"><section><h3>答案要求与评分规则</h3>' + _fields(answer, exclude=('id', 'answer')) + '</section>'
        if audit is None:
            body += '<div class="warning">此题审计记录缺失，请复核。</div>'
        else:
            body += '<section><h3>间隔、通道与事实边界</h3>' + _fields(audit, exclude=('id', 'evidence_ids')) + '</section>'
        if answer is not None:
            body += '</div>'
        body += '<h3>检查点与数据版本</h3>' + _fields(question, exclude=('question',))
        evidence_ids = (audit or {}).get('evidence_ids', [])
        if isinstance(evidence_ids, str):
            evidence_ids = [evidence_ids]
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        body += '<h3>原始证据与最小摘录</h3>'
        if not evidence_ids:
            body += '<div class="warning">未列出证据引用。</div>'
        for evidence_id in evidence_ids:
            body += _evidence_html(bank_dir, str(evidence_id), evidence.get(str(evidence_id)))
        body += _detail('完整题目、答案与审计记录（私有）', {'question': question, 'answer': answer, 'audit': audit})
        cards.append(
            '<details class="question-card" data-game="' + _text(question.get('game_id', '未提供'))
            + '" data-kind="' + _text(question.get('kind', '未提供')) + '"><summary><div>'
            + '<span class="item-id">' + _text(identifier) + '</span><span class="pill">待人工审阅</span>'
            + '<div class="card-title">' + _text(title) + '</div><div class="meta">' + _text(meta)
            + '</div></div></summary><div class="card-body">' + body + '</div></details>'
        )
    coverage_counts = Counter(str((items.get(q['id']) or {}).get('category', q.get('kind', '未提供'))) for q in questions)
    coverage_chips = ''.join('<span class="count-chip">' + _text(kind) + ' <b>' + str(count) + '</b></span>' for kind, count in sorted(coverage_counts.items(), key=lambda pair: str(pair[0])))
    validation_status = validation.get('status', '未提供') if isinstance(validation, dict) else '未提供'
    replacements = {
        '__BANK_ID__': _text(questions_doc.get('bank_id', bank_dir.name)),
        '__N_QUESTIONS__': str(len(questions)), '__N_GAMES__': str(len(game_ids)),
        '__VALIDATION_STATUS__': _text(validation_status),
        '__SOURCE_TABLE__': _source_table(dataset), '__COVERAGE_CHIPS__': coverage_chips,
        '__COVERAGE__': _detail('实际覆盖、未覆盖目标及限制', coverage if coverage is not None else {'status': 'coverage.json 未提供，需人工补核。'}, True),
        '__DATASET__': _detail('完整逐局来源审计、异常与计数定义', dataset if dataset is not None else {'status': 'audit/dataset.json 未提供'}),
        '__VALIDATION__': _detail('离线验证详情（不属于模型成绩）', validation if validation is not None else {'status': 'validation.json 尚未生成'}),
        '__CANDIDATES__': _detail('候选区：不计入正式首批题目', candidates if candidates is not None else {'status': 'private/candidates.json 未提供'}),
        '__GAME_OPTIONS__': ''.join('<option value="' + _text(value) + '">' + _text(value) + '</option>' for value in game_ids),
        '__KIND_OPTIONS__': ''.join('<option value="' + _text(value) + '">' + _text(value) + '</option>' for value in kinds),
        '__CARDS__': ''.join(cards),
        '__METADATA__': _detail('公开题库元数据', {key: value for key, value in questions_doc.items() if key != 'records'}),
    }
    # One pass prevents content containing a template token from being replaced.
    import re
    document = re.sub('|'.join(re.escape(key) for key in replacements),
                      lambda match: replacements[match.group()], _HTML)
    reports_dir = bank_dir / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    destination = reports_dir / 'review.html'
    descriptor, temporary = tempfile.mkstemp(prefix='.review-', suffix='.html', dir=reports_dir)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(document)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Jity · 长期一致性题库审阅</title>
<style>
:root{color-scheme:light;--ink:#172e3d;--muted:#586d7c;--line:#d7e1e6;--paper:#fff;--bg:#f2f5f6;--accent:#13665f;--amber:#86541b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}main,header>div{width:min(1240px,calc(100% - 40px));margin:auto}header{background:#142e39;color:#fff;padding:35px 0 30px}header .eyebrow{color:#a4c9c2;font-size:12px;letter-spacing:2px}h1{font-size:clamp(25px,4vw,39px);line-height:1.3;margin:10px 0 15px}h2{font-size:22px;margin:0 0 12px}h3{font-size:16px;margin:24px 0 10px}h4{font-size:14px;margin:0 0 12px;overflow-wrap:anywhere}p{margin:10px 0}.subtitle{max-width:900px;color:#d0e0e4}.bank-id{font:12px/1.6 ui-monospace,monospace;color:#b3ced1;overflow-wrap:anywhere}.status{display:inline-block;padding:4px 11px;background:#f9dd9e;border-radius:99px;color:#51390d;font-size:13px;font-weight:700}main{padding:24px 0 48px}.notice,.warning{border:1px solid #e1bf79;background:#fff8e8;color:#694713;border-radius:10px;padding:15px 18px;margin-bottom:20px}.notice strong{display:block}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.metric,.panel{background:var(--paper);border:1px solid var(--line);border-radius:13px;padding:20px}.metric .number{font-size:30px;line-height:1.25;font-weight:700;overflow-wrap:anywhere}.metric .number.small{font-size:22px}.metric .label,.meta,.muted{font-size:12px;color:var(--muted)}.panel{margin:20px 0}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:24px}.two-col>section{min-width:0}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;min-width:820px}th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}td{overflow-wrap:anywhere}.count-chip{display:inline-flex;gap:10px;background:#edf5f2;color:#205a51;border:1px solid #d9e9e2;border-radius:30px;padding:5px 13px;margin:4px 6px 4px 0;font-size:13px}.detail{margin:15px 0;border-top:1px solid var(--line);padding-top:12px}.detail>summary{cursor:pointer;font-weight:600;font-size:13px}.json{background:#f3f6f8;border:1px solid #e4eaed;border-radius:7px;padding:11px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;max-height:520px;overflow:auto;margin:8px 0}.prose{white-space:pre-wrap;overflow-wrap:anywhere}.filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px}.filters label{font-size:12px;font-weight:600;color:var(--muted)}input,select{display:block;width:100%;min-width:0;margin-top:5px;padding:10px 12px;border:1px solid #b8c9d2;border-radius:7px;background:#fff;color:var(--ink);font:inherit;font-size:14px}.toolbar{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:17px 0 0}.toolbar .buttons{display:flex;gap:8px;flex-wrap:wrap}button{border:1px solid #b8c9d2;border-radius:6px;background:#fff;padding:7px 12px;color:var(--ink);font:inherit;font-size:12px;cursor:pointer}button:hover{background:#eaf2f1}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #4b9e91;outline-offset:3px}.question-card{background:#fff;border:1px solid var(--line);border-radius:12px;margin:14px 0;overflow:hidden}.question-card>summary{cursor:pointer;padding:18px 22px;display:flex;gap:14px;list-style:none}.question-card>summary::-webkit-details-marker{display:none}.question-card>summary:before{content:'›';font-size:27px;line-height:30px;color:var(--accent)}.question-card[open]>summary:before{content:'⌄'}.question-card>summary>div{min-width:0;flex:1}.item-id{font:12px/1.5 ui-monospace,monospace;color:#426271;overflow-wrap:anywhere}.pill{display:inline-block;font-size:11px;margin-left:12px;padding:2px 8px;background:#fff2d1;color:#72531c;border-radius:20px}.card-title{font-size:17px;font-weight:650;margin:7px 0;overflow-wrap:anywhere}.card-body{border-top:1px solid var(--line);padding:22px}.question-text,.gold{border-radius:9px;padding:16px 18px;margin-bottom:16px}.question-text{background:#edf4f8;border:1px solid #cfdee8;font-size:17px}.gold{background:#edf6f0;border:1px solid #cce3d4;font-size:16px}.small-label{display:block;font-size:11px;font-weight:700;letter-spacing:.5px;color:#536f72;margin-bottom:8px}.fields{display:grid;grid-template-columns:minmax(125px,180px) minmax(0,1fr);gap:0;margin:8px 0 18px;font-size:13px}.fields dt,.fields dd{margin:0;padding:9px 0;border-bottom:1px solid #e6ecef;min-width:0}.fields dt{color:var(--muted);padding-right:15px;overflow-wrap:anywhere}.fields .json{margin:0}.evidence{border:1px solid var(--line);border-left:3px solid #63a79b;border-radius:8px;padding:17px;margin:13px 0}.excerpt{background:#f7f7f0;border-radius:6px;padding:13px 15px}.file-link{color:#11665e;font-size:13px;text-decoration-thickness:1px}.footer{font-size:12px;color:var(--muted);margin:25px 0 0}.empty{text-align:center;padding:35px;color:var(--muted)}[hidden]{display:none!important}noscript{display:block;margin:12px 0;color:var(--amber)}
@media(max-width:760px){main,header>div{width:calc(100% - 24px)}header{padding:25px 0}.metrics{grid-template-columns:1fr 1fr;gap:10px}.metric,.panel{padding:15px}.filters,.two-col{grid-template-columns:1fr}.filters{gap:11px}.toolbar{align-items:flex-start;flex-direction:column}.card-body{padding:14px}.question-card>summary{padding:15px}.fields{grid-template-columns:1fr}.fields dt{padding-bottom:2px;border-bottom:0;font-weight:600}.fields dd{padding-top:2px}.card-title{font-size:16px}.evidence{padding:12px}.question-text,.gold{padding:13px;font-size:15px}.json{max-height:380px}.pill{margin-left:6px}}
@media print{header{background:#fff;color:#000}.subtitle,.bank-id{color:#333}.filters,.toolbar{display:none}.question-card,.panel,.metric{box-shadow:none}.json{max-height:none;overflow:visible}body{background:#fff}}
</style></head><body>
<header><div><div class="eyebrow">JITY / LONG-TERM CONSISTENCY</div><h1>检查点＋问题＋证据答案</h1><span class="status">首批题库 · 待人工审阅</span><p class="subtitle">检查事实边界、最近重提、信息通道和标准答案。此页只展示题库及离线完整性验证，不计算或宣称模型记忆成绩。</p><div class="bank-id">__BANK_ID__</div></div></header>
<main>
<div class="notice"><strong>私有审阅报告：包含标准答案与完整审计证据，请勿作为待测模型输入。</strong>未来每题须独立作答，三组共享同一检查点和同一问题。完整记忆、近期上下文、结构化状态三组尚未生成模型回答。</div>
<div class="metrics"><div class="metric"><div class="number">__N_QUESTIONS__</div><div class="label">待审题目 · 非独立游戏样本</div></div><div class="metric"><div class="number">__N_GAMES__</div><div class="label">题目来源游戏</div></div><div class="metric"><div class="number">0</div><div class="label">本次模型回答 · 0 付费 API 调用</div></div><div class="metric"><div class="number small">__VALIDATION_STATUS__</div><div class="label">离线结构验证状态 · 非模型成绩</div></div></div>
<section class="panel"><h2>来源、覆盖与限制</h2><p class="muted">多题来自同一游戏、同一检查点时具有相关性；来自四局的多道题不能视为大量独立游戏样本。严格重放通过仅说明录制可重现。提交行动、战役有效推进与时间线节点分别计数。</p>__SOURCE_TABLE__<div style="margin-top:16px">__COVERAGE_CHIPS__</div>__COVERAGE____DATASET____VALIDATION____CANDIDATES____METADATA__</section>
<section class="panel"><h2>逐题审阅</h2><div class="filters"><label>搜索问题、答案、证据或待复核项<input id="search" type="search" placeholder="输入关键词" autocomplete="off"></label><label>来源游戏<select id="game"><option value="">所有游戏</option>__GAME_OPTIONS__</select></label><label>题型<select id="kind"><option value="">所有题型</option>__KIND_OPTIONS__</select></label></div><div class="toolbar"><div id="count" class="muted" role="status" aria-live="polite">共 __N_QUESTIONS__ 题</div><div class="buttons"><button id="expand" type="button">展开筛选结果</button><button id="collapse" type="button">折叠全部</button></div></div><noscript>未启用 JavaScript：所有题目仍可逐题展开阅读，筛选功能不可用。</noscript></section>
<div id="questions">__CARDS__</div><div id="empty" class="empty" hidden>没有符合筛选条件的题目。</div>
<p class="footer">本报告自包含，无外部脚本、字体、图片或网络请求。证据链接仅指向题库目录中的现有冻结文件。需要人工完成语义重提、未知问题线索与答案边界复核后，方可用于后续三组独立作答实验。</p>
</main><script>
(() => { 'use strict';
const cards = [...document.querySelectorAll('.question-card')];
const search = document.getElementById('search'), game = document.getElementById('game'), kind = document.getElementById('kind');
function filter() { const query = search.value.trim().toLocaleLowerCase(); let shown = 0;
  cards.forEach(card => { const match = (!game.value || card.dataset.game === game.value) && (!kind.value || card.dataset.kind === kind.value) && (!query || card.textContent.toLocaleLowerCase().includes(query)); card.hidden = !match; if (match) shown++; });
  document.getElementById('count').textContent = `显示 ${shown} / ${cards.length} 题`;
  document.getElementById('empty').hidden = shown !== 0;
}
search.addEventListener('input', filter); game.addEventListener('change', filter); kind.addEventListener('change', filter);
document.getElementById('expand').addEventListener('click', () => cards.forEach(card => { if (!card.hidden) card.open = true; }));
document.getElementById('collapse').addEventListener('click', () => cards.forEach(card => { card.open = false; })); filter();
})();
</script></body></html>'''
