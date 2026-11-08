"""Offline, append-only revisions of captured question banks (no model runner).

The review specification supplies semantic judgments; validation checks their
provenance and consistency, not whether a human has approved those judgments.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import html
import json
from pathlib import Path
import shutil

from . import question_bank as qb
from .storage import atomic_json, digest, digest_bytes, now

INSTRUCTION = "仅依据本次提供的记录回答；无法确定时明确说明，不补造事实。行动题只判断和解释，不执行行动。"
VERSION = "1.2.0-review"
SCHEMA = "jity.capture-question-bank.revision.v1"
POLICY = {
    "status": "pending_human_review",
    "correct": "准确表达或清楚蕴含事实即给该要点分；接受自然语言和同义转述，不要求内部字段名、逐字复述或另附免责声明。",
    "omitted": "遗漏要点为0；部分内容仅按该点列出的部分分给分；不因没有犯错而给分。",
    "incorrect": "错误或与证据相反的要点为0；不能用同时列出正确关键词抵消错误断言。",
    "unsupported_extra": "额外无依据断言不加分，单列unsupported_extra标记；若改变所问结论、身份归属、原因或状态，则相关点为0。纯粹无关扩写不扣无关的正确点。",
    "contradiction": "同一语义点内正确与相反断言并存且未明确撤回错误时，该点为0。结论与理由矛盾时，核心判断点及被该矛盾直接否定的依据点均为0；其他独立且一致的事实可保留分。不得机械堆词累计。",
    "no_double_credit": "同一事实仅计一次；蕴含关系可满足该语义点，无需重复补充同义免责声明。判断与依据分别计分时，必须分别表达判断和实际证据；仅重复结论不算依据。",
    "attribution": "某角色的说法不自动成为世界真相。题干明确问某人的说法时，顺承的转述可蕴含归属，无需每句重复自称；若明确升级为已证实事实，相关点为0。",
    "unknown": "接受本次提供的信息不足，不要求模型断言全局历史均无答案。仅说不知道只得未知结论点；人物角色、已知线索等解释点须有正确内容。",
    "boundary": "不作永久不可行、实际死亡、消耗销毁等额外推断是边界约束，不设独立奖励分。若实际作出这些错误断言，按其影响使相关点为0。",
    "execution": "只判断和解释。实际执行或声称新行动已经发生标记协议违规；新行动不能作为得分证据。",
    "model_answers": "not_run",
}


def file_sha(path):
    return digest_bytes(Path(path).read_bytes())


def inventory(root, excluded=()):
    return {str(p.relative_to(root)): file_sha(p) for p in sorted(Path(root).rglob("*"))
            if p.is_file() and str(p.relative_to(root)) not in excluded}


def build(previous, spec_path, output):
    previous, output = Path(previous).resolve(), Path(output).resolve()
    qb.require(not output.exists(), "Output exists; choose a new directory")
    spec = qb.read(spec_path)
    qb.require(not output.is_relative_to(Path(qb.read(previous / "manifest.json")["source_root"])), "Cannot write to recordings")
    # Validate the existing bank without modifying its artifacts.
    qb.validate(previous, source_check=True)
    output.mkdir(parents=True)
    for directory in ("frozen", "public", "private", "audit"):
        shutil.copytree(previous / directory, output / directory, copy_function=shutil.copyfile)
    for name in ("coverage.json",):
        shutil.copyfile(previous / name, output / name)
    atomic_json(output / "private/revision-spec.json", spec)
    atomic_json(output / "private/scoring-policy.json", POLICY)
    public = qb.read(previous / "public/questions.json")
    authored = qb.read(previous / "private/authoring.json")
    items = qb.read(previous / "audit/items.json")
    evidences = qb.read(previous / "audit/evidence.json")
    changes, audits, answers = [], [], []
    for i, row in enumerate(spec["questions"]):
        q = public["records"][i]
        qb.require(q["id"] == row["id"], "Stable order/IDs changed")
        old_gold = deepcopy(authored["questions"][i]["gold"])
        q["question"] = row["question"]
        gold = row["gold"]
        answers.append({"id": q["id"], **gold})
        aq = authored["questions"][i]
        aq.update(question=row["question"], gold=gold, purpose=row["purpose"])
        aq["review"]["status"] = "pending_human_review"
        aq["review"]["required"] += row["review"]
        if q["id"].endswith("G04-Q03"):
            aq["review"]["ambiguities"] = [x for x in aq["review"]["ambiguities"] if "待人工决定后续是否" not in x]
            aq["review"]["ambiguities"].append("历史解释及来源继续作为评分要求；actual full/state缺少它们，保留系统级诊断价值，不归因为获得完整证据后的回答能力。")
        audit = items["records"][i]
        audit["review"] = deepcopy(aq["review"])
        audit["purpose"] = row["purpose"]
        audit["answer_correctness"] = "not_run"
        audit["point_audit"] = "audit/points.json#" + q["id"]
        audit["evidence_ids"].extend(r["id"] for r in spec["references"] if r["question_id"] == q["id"])
        if q["id"].endswith("G03-Q01"):
            aq["first_action"] = audit["chronology"]["first_action"] = 0
            aq["chronology_notes"] = aq.get("chronology_notes", "") + " v1.2更正：首次结构化持有为initial 0；首次叙事为行动1；移交为行动24。"
            audit["chronology"]["author_notes"] = aq["chronology_notes"]
            audit["chronology"]["first_structured_possession_action"] = 0
            audit["chronology"]["first_narrative_action"] = 1
            aq["validity"]["from_submitted_action"] = 0
            audit["validity"]["from_submitted_action"] = 0
            audit["interval"]["since_first_actions"] = q["checkpoint"]["action_index"]
            audit["interval"]["since_first_campaign_turns"] = q["checkpoint"]["campaign_turn"]
        audit["channels"]["point_support_is_authoritative"] = "audit/points.json; legacy hits are topic matches only"
        for mode in qb.MODES:
            path = Path("public/inputs") / q["id"] / (mode + ".json")
            payload = qb.read(previous / path)
            payload["question"] = row["question"]
            payload["instruction"] = INSTRUCTION
            atomic_json(output / path, payload)
        changes.append({"id": q["id"], "old_question": qb.read(previous / "public/questions.json")["records"][i]["question"],
                        "new_question": q["question"], "old_max_score": old_gold["rubric"]["max_score"],
                        "new_max_score": gold["rubric"]["max_score"], **row["change"]})
        audits.append({"id": q["id"], "status": "pending_human_review", "purpose": row["purpose"],
                       "answer_correctness": "not_run", "points": row["points"],
                       "semantic_decisions": row["semantic_decisions"],
                       "history_scope": {"game_id": q["game_id"], "from_action": 0, "through_action": q["checkpoint"]["action_index"],
                         "fields": ["initial/state", "output including options, checks and updates", "actual player_action", "committed state and memory"],
                         "no_value_disclosure_claim": "bounded to this prefix; input support separately bounded to each supplied input"}})
    authored["bank_version"] = VERSION
    public["bank_version"] = VERSION
    for doc, path in ((public, "public/questions.json"), (authored, "private/authoring.json"),
                      ({"schema_version": SCHEMA, "bank_version": VERSION, "records": answers}, "private/answers.json"),
                      (items, "audit/items.json"), ({"schema_version": SCHEMA, "records": audits}, "audit/points.json"),
                      ({"schema_version": SCHEMA, "records": changes}, "audit/changes.json")):
        atomic_json(output / path, doc)
    # Resolve authored references against the newly frozen bytes.
    refs = []
    for ref in spec["references"]:
        ref = deepcopy(ref)
        file = qb.safe_path(output, ref["frozen_path"])
        ref["file_sha256"] = file_sha(file)
        ref["value_sha256"] = digest(qb.pointer(qb.read(file), ref["json_pointer"]))
        refs.append(ref)
    evidences["records"].extend(refs)
    atomic_json(output / "audit/evidence.json", evidences)
    atomic_json(output / "audit/revision-provenance.json", {
        "previous_bank": str(previous), "previous_delivery_sha256": file_sha(previous / "delivery.sha256.json"),
        "previous_manifest_sha256": file_sha(previous / "manifest.json"), "spec_sha256": file_sha(spec_path),
        "preservation": "All context values and source bytes must match v1.1; only question and common instruction change inside each input.",
        "human_review": "pending_human_review", "model_answers": "not_run"})
    # Keep the original dataset identity; bank version is a separate axis.
    manifest = qb.read(previous / "manifest.json")
    manifest.update(bank_version=VERSION, created_at=now(), revision_schema=SCHEMA, previous_bank=str(previous),
                    review_status="pending_human_review", model_answers="not_run")
    manifest["files"] = inventory(output)
    atomic_json(output / "manifest.json", manifest)
    (output / "manifest.sha256").write_text(file_sha(output / "manifest.json") + "  manifest.json\n")
    return validate(output)


def validate(root, check_original=False):
    root = Path(root).resolve()
    m = qb.read(root / "manifest.json")
    qb.require(m["bank_version"] == VERSION, "Wrong revision version")
    qb.require(file_sha(root / "manifest.json") == (root / "manifest.sha256").read_text().split()[0], "Manifest mismatch")
    for name, sha in m["files"].items():
        qb.require(file_sha(qb.safe_path(root, name)) == sha, "File mismatch: " + name)
    prev = Path(m["previous_bank"])
    provenance = qb.read(root / "audit/revision-provenance.json")
    qb.require(file_sha(prev / "delivery.sha256.json") == provenance["previous_delivery_sha256"], "Previous delivery changed")
    qb.require(file_sha(prev / "manifest.json") == provenance["previous_manifest_sha256"], "Previous manifest changed")
    qb.validate(prev, source_check=check_original)
    spec = qb.read(root / "private/revision-spec.json")
    public_document = qb.read(root / "public/questions.json")
    qb.require(set(public_document) == {"schema_version", "bank_id", "bank_version", "records"}, "Private or unexpected public root metadata")
    public = public_document["records"]
    old_public = qb.read(prev / "public/questions.json")["records"]
    gold = qb.read(root / "private/answers.json")["records"]
    audits = qb.read(root / "audit/points.json")["records"]
    authored = qb.read(root / "private/authoring.json")["questions"]
    ids = [q["id"] for q in public]
    qb.require(len(ids) == len(set(ids)) == 12 and ids == [q["id"] for q in old_public], "Stable IDs changed")
    for records in (gold, audits, authored, spec["questions"]):
        qb.require([q["id"] for q in records] == ids, "Incomplete question mapping")
    refs = qb.read(root / "audit/evidence.json")["records"]
    refmap = {r["id"]: r for r in refs}
    qb.require(len(refmap) == len(refs), "Duplicate evidence ID")
    source = root / "frozen/source"
    public_paths = {"public/questions.json"}
    total_points = 0
    for i, q in enumerate(public):
        qb.require(set(q) == qb.PUBLIC_KEYS, "Private or unexpected public metadata")
        for k in set(q) - {"question"}:
            qb.require(q[k] == old_public[i][k], "Checkpoint/game/data/kind changed")
        qb.require(q["question"] == spec["questions"][i]["question"] == authored[i]["question"], "Question mismatch")
        qb.require(q["checkpoint"] == qb.checkpoint_identity(qb.checkpoint(source, q["game_id"], q["checkpoint"]["action_index"])), "Checkpoint mismatch")
        qb.require(gold[i] == {"id": q["id"], **authored[i]["gold"]} == {"id": q["id"], **spec["questions"][i]["gold"]}, "Answer mismatch")
        qb.require(audits[i]["status"] == authored[i]["review"]["status"] == "pending_human_review", "Review status changed")
        points = gold[i]["rubric"]["points"]
        qb.require(sum(p["score"] for p in points) == gold[i]["rubric"]["max_score"], "Score sum mismatch")
        qb.require(gold[i]["required_points"] == [p["criterion"] for p in points], "Required points mismatch")
        qb.require(len({p["semantic_key"] for p in points}) == len(points), "Duplicate semantic scoring point")
        qb.require([p["id"] for p in points] == [p["id"] for p in audits[i]["points"]], "Point audit mismatch")
        qb.require(audits[i]["points"] == spec["questions"][i]["points"], "Point audit differs from authored judgments")
        total_points += len(points)
        for mode in qb.MODES:
            name = f"public/inputs/{q['id']}/{mode}.json"
            public_paths.add(name)
            got, old = qb.read(root / name), qb.read(prev / name)
            expected = deepcopy(old)
            expected.update(question=q["question"], instruction=INSTRUCTION)
            qb.require(got == expected, "Input changed beyond question/instruction: " + name)
            rebuilt = qb.make_input(source, q, mode, 6)
            rebuilt["instruction"] = INSTRUCTION
            qb.require(got == rebuilt, "Input does not match raw recorded channels: " + name)
        for p in audits[i]["points"]:
            qb.require(p["answer_correctness"] == "not_run", "Unexpected model result")
            for label in ("first_explicit", "latest_explicit"):
                loc = p["chronology"][label]
                if loc is None:
                    qb.require(p["chronology"].get("null_reason"), "Missing disclosure explanation")
                    continue
                cp = qb.checkpoint(source, q["game_id"], loc["action_index"])
                qb.require(loc["timeline_node"] == cp["head"] and loc["campaign_turn"] == cp["progress"]["turns_total"], "Disclosure coordinates mismatch")
                qb.require(loc["gap_actions"] == q["checkpoint"]["action_index"] - loc["action_index"], "Action interval mismatch")
                qb.require(loc["gap_campaign_turns"] == q["checkpoint"]["campaign_turn"] - loc["campaign_turn"], "Campaign interval mismatch")
                qb.require(loc["gap_actions"] >= 0 and loc["gap_campaign_turns"] >= 0, "Future disclosure")
                qb.require(loc["evidence_ids"], "Missing disclosure evidence")
                for rid in loc["evidence_ids"]:
                    r = refmap[rid]
                    qb.require(r["action_index"] == loc["action_index"] and r["classification"] == "explicit_answer", "Invalid disclosure evidence role")
            for rid in p["historical_evidence_ids"]:
                r = refmap[rid]
                qb.require(r["game_id"] == q["game_id"] and r["action_index"] <= q["checkpoint"]["action_index"], "Cross-game/future evidence")
            qb.require(set(p["inputs"]) == set(qb.MODES), "Missing input support")
            for mode, support in p["inputs"].items():
                qb.require(support["support"] in ("full", "partial", "not_provided"), "Bad support label")
                input_path = f"public/inputs/{q['id']}/{mode}.json"
                qb.require(support["input_context_sha256"] == digest(qb.read(root / input_path)["context"]), "Input audit digest mismatch")
                for rid in support["evidence_ids"]:
                    qb.require(refmap[rid]["frozen_path"] == input_path and refmap[rid]["json_pointer"].startswith("/context/"), "Wrong input evidence")
                if support["support"] != "not_provided":
                    qb.require(support["evidence_ids"] or support.get("basis") == "bounded_input_absence", "Unsupported support label")
    qb.require({str(p.relative_to(root)) for p in (root / "public").rglob("*") if p.is_file()} == public_paths, "Unexpected public file")
    for r in refs:
        path = qb.safe_path(root, r["frozen_path"])
        qb.require(file_sha(path) == r["file_sha256"], "Evidence file mismatch")
        value = qb.pointer(qb.read(path), r["json_pointer"])
        qb.require(digest(value) == r["value_sha256"], "Evidence value mismatch")
        if r.get("projection") == "names":
            value = [v.get("name") for v in value]
        excerpt = r["excerpt"]
        qb.require((excerpt in value) if isinstance(value, str) and isinstance(excerpt, str) else excerpt == value, "Inaccurate excerpt")
        qid = r.get("question_id", r["id"].split(".e")[0])
        q = next(x for x in public if x["id"] == qid)
        qb.require(r["game_id"] == q["game_id"] and r["action_index"] <= q["checkpoint"]["action_index"], "Future/cross-game reference")
        cp = qb.checkpoint(source, r["game_id"], r["action_index"])
        qb.require(cp["head"] == r["timeline_node"], "Evidence timeline mismatch")
        if r["frozen_path"].startswith("frozen/source/"):
            kind = "intents" if "/intents/" in r["frozen_path"] else "checkpoints"
            qb.require(r["frozen_path"] == "frozen/source/" + qb.source_name(r["game_id"], r["action_index"], kind), "Evidence coordinates/path mismatch")
    for path in (source).rglob("*"):
        if path.is_file():
            qb.require(file_sha(path) == file_sha(prev / path.relative_to(root)), "Frozen source changed")
    if check_original:
        qb.verify_source(Path(m["source_root"]))
    return {"status": "passed", "bank_version": VERSION, "questions": len(ids), "inputs": 36,
            "scoring_points": total_points, "evidence_references": len(refs), "review_status": "pending_human_review",
            "original_seal_checked": check_original, "model_experiments": "not_run",
            "limits": "Structural/provenance validation only. Semantic audit and rubrics remain pending human review."}


def report(root):
    root = Path(root)
    q = qb.read(root / "public/questions.json")["records"]
    gold = {x["id"]: x for x in qb.read(root / "private/answers.json")["records"]}
    audits = {x["id"]: x for x in qb.read(root / "audit/points.json")["records"]}
    items = {x["id"]: x for x in qb.read(root / "audit/items.json")["records"]}
    evidence = {x["id"]: x for x in qb.read(root / "audit/evidence.json")["records"]}
    changes = {x["id"]: x for x in qb.read(root / "audit/changes.json")["records"]}
    esc = lambda x: html.escape(str(x))
    labels = {"long_term_fact": "历史事实与状态判断", "retention_diagnostic": "记忆保留诊断", "recent_unknown_control": "近期未知控制", "recent_state_control": "近期状态控制", "mixed_fact_diagnostic": "历史事实兼保留诊断"}
    support_label = {"full": "完整", "partial": "部分", "not_provided": "未提供"}
    def evidence_html(ids):
        body = []
        for rid in dict.fromkeys(ids):
            r = evidence[rid]
            value = r["excerpt"] if isinstance(r["excerpt"], str) else json.dumps(r["excerpt"], ensure_ascii=False)
            body.append(f'<li><a href="../{esc(r["frozen_path"])}">{esc(rid)}</a> · A{r["action_index"]}/节点{r["timeline_node"]} · <code>{esc(r["json_pointer"])}</code><blockquote>{esc(value)}</blockquote></li>')
        return '<ul class="evidence">' + ''.join(body) + '</ul>'
    def loc(l):
        if l is None:
            return "不适用：有界不足判断没有一个已披露的姓名/数值"
        return f'A{l["action_index"]} / 战役{l["campaign_turn"]} / 节点{l["timeline_node"]}；距检查点 {l["gap_actions"]} 次提交 / {l["gap_campaign_turns"]} 次推进'
    cards = []
    for row in q:
        id = row["id"]; g = gold[id]; a = audits[id]; it = items[id]; c = row["checkpoint"]
        points = []
        for p, rule in zip(a["points"], g["rubric"]["points"]):
            inputs = []
            for mode, s in p["inputs"].items():
                inputs.append(f'<details><summary>{esc(mode)}：{support_label[s["support"]]}</summary><p>{esc(s["note"])}</p>{evidence_html(s["evidence_ids"])}</details>')
            points.append(f'<div class="point"><h4>{esc(p["id"].split(".")[-1])} · {rule["score"]}分 · {esc(rule["criterion"])}</h4><p>部分分：{esc(rule["partial_credit"])}</p><p>首次：{esc(loc(p["chronology"]["first_explicit"]))}<br>最近明确披露：{esc(loc(p["chronology"]["latest_explicit"]))}</p><p>更新：{esc(p["chronology"]["updates"])}</p><p>{esc(p["chronology"]["note"])}</p><details><summary>原始证据</summary>{evidence_html(p["historical_evidence_ids"])}</details>{"".join(inputs)}</div>')
        reviews = it["review"]["ambiguities"] + it["review"]["required"]
        cards.append(f'<article id="{id}" data-purpose="{a["purpose"]}"><p class="tag">{esc(labels[a["purpose"]])} · pending_human_review</p><h2>{esc(id)}</h2><p>A{c["action_index"]} / 战役{c["campaign_turn"]} / 时间线节点{c["timeline_node"]} · 最近6次提交不变</p><p class="question">{esc(row["question"])}</p><h3>标准答案 · {g["rubric"]["max_score"]}分</h3><p>{esc(g["answer"])}</p><p>可接受表述：{esc("；".join(g["acceptable_phrasings"]))}</p><p>整题相关话题间隔：{it["interval"]["since_last_public_mention_actions"]} 次提交 / {it["interval"]["since_last_campaign_turns"]} 次推进（保留 v1.1 定义；不等于每要点完整答案间隔）</p>{"".join(points)}<h3>语义审计决定</h3><ul>{"".join("<li>"+esc(x)+"</li>" for x in a["semantic_decisions"])}</ul><h3>典型错误与待复核</h3><p>{esc("；".join(g["typical_errors"]))}</p><ul>{"".join("<li>"+esc(x)+"</li>" for x in reviews)}</ul><h3>本次修改</h3><p>{esc(changes[id]["what"])}；原因：{esc(changes[id]["why"])}；评分含义：{esc(changes[id]["scoring_meaning"])}</p></article>')
    policy = ''.join(f'<li><b>{esc(k)}</b>：{esc(v)}</li>' for k,v in POLICY.items() if k not in ("status", "model_answers"))
    text = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Jity v1.2 题库人工审阅</title><style>body{{margin:0;background:#f4f3ef;color:#202b32;font:16px/1.75 system-ui,sans-serif}}main{{max-width:1120px;margin:auto;padding:28px}}header,article,section{{background:white;border:1px solid #dcded9;border-radius:14px;padding:26px;margin:20px 0}}h1{{font-size:30px}}h2{{font-size:24px;overflow-wrap:anywhere}}h3{{font-size:19px}}h4{{font-size:16px}}.tag{{color:#855100;font-weight:650}}.question{{font-size:20px;border-left:4px solid #2b776b;padding:12px}}.point{{padding:16px;background:#f5f8f7;border:1px solid #d6e3de;margin:16px 0;border-radius:8px}}code,a{{overflow-wrap:anywhere}}blockquote{{margin:8px 0;padding:10px;background:#eef1ee;white-space:pre-wrap;overflow-wrap:anywhere}}details{{margin:8px 0}}summary{{cursor:pointer}}select{{font:inherit;padding:6px}}@media(max-width:600px){{main{{padding:10px}}header,article,section{{padding:15px}}.point{{padding:10px}}h1{{font-size:25px}}}}</style><main><header><h1>Jity 长期一致性题库 · v1.2</h1><p class="tag">12题 · 4局 · 36份冻结输入 · 全部待人工审阅 · 模型实验未运行</p><p>{INSTRUCTION}</p><p>本页是私有审计报告，不可作为待测模型输入。以下分值是评分合同，不是模型成绩。12题来自4局，不是12个独立游戏样本。</p><p>四局终态均为预算结束的“未竟的追寻”，既有严格重放通过；本轮核验封存证据，不重跑游戏。原始异常和候选区保留。</p><p>历史事实题检验给定历史与当前状态的一致性；G02-Q03诊断数量在三组输入中的遗失；G04-Q03兼诊断解释来源的遗漏；G03-Q03是近期未知控制；G04-Q02是0间隔近期状态控制。G04-Q01各要点的间隔与可见性不同。</p><p>world_facts、人物信息和物品账本保留了多题答案，state组可以合法答对。三道行动题的核心结论均是否定，存在标签分布偏向；本次不强凑正例。没有明确消耗事件，不把移交/遗失冒称消耗。</p><p>历史证据存在、输入是否保留、未来回答是否正确是三个不同问题。第6、12题缺失的历史答案仍保留在私有标准中，没有补写输入记忆；它们不能单独证明回答模型在获得完整证据条件下的能力。</p><label>按用途查看 <select id="filter"><option value="all">全部12题</option>{''.join(f'<option value="{k}">{v}</option>' for k,v in labels.items())}</select></label><nav>{' · '.join(f'<a href="#{x["id"]}">{x["id"][-7:]}</a>' for x in q)}</nav></header><section><h2>统一语义评分规则</h2><ul>{policy}</ul><p>间隔按提交行动差及progress.turns_total推进差分别计算。节点是标识，不直接相减。持续摘要/状态曝光单列，不能改写为新剧情披露。未知结论无具体值披露位置，使用有界审查而非虚构首次出现。</p></section>{''.join(cards)}</main><script>document.getElementById('filter').addEventListener('change',e=>document.querySelectorAll('article').forEach(a=>a.hidden=e.target.value!=='all'&&a.dataset.purpose!==e.target.value));</script></html>'''
    target = root / "reports/review.html"
    target.parent.mkdir(exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    for name in ("previous", "spec", "output"):
        b.add_argument("--" + name, required=True)
    v = sub.add_parser("validate"); v.add_argument("bank"); v.add_argument("--check-original", action="store_true")
    r = sub.add_parser("report"); r.add_argument("bank")
    args = p.parse_args()
    if args.command == "build":
        result = build(args.previous, args.spec, args.output)
    elif args.command == "validate":
        result = validate(args.bank, args.check_original)
    else:
        result = report(args.bank)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
