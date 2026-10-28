# N4 batch rewrite assembly (deliverable-3 batch candidates).
#
# The rewrite TEXTS below are written by ZCode (the style-teacher role per
# the N4 exception clause) — this script only assembles rows mechanically:
# it inherits plan/world/planOnlyClaims/rawDelta from the seed row of the
# same sourceGroupId, recomputes content hashes, and stamps
# rewriter=zcode-model. Nothing here paraphrases or generates content.
#
# Every rewrite stays inside the controlled recognizer space (corpus_check
# entry_patterns); needs-review verdicts are NOT passes and are fixed or
# honestly reported before delivery.
#
# Usage: python experiments/world-components/n4_corpus/assemble_rewrites.py
# Output: experiments/world-components/n4_corpus/rewrites.jsonl (26 rows)

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SEEDS = HERE / "corpus.seeds.jsonl"
OUT = HERE / "rewrites.jsonl"

# (groupId, planRefs, text) — text by ZCode, 2026-10-29. planRefs are
# sentence-scoped (sentences split on 。).
REWRITES = [
    ("n4-loc-001", [[0, 1]], "约三分钟过去了，陈舟从东门一路走到了钟楼。"),
    ("n4-loc-002", [[0], [1]], "苏晚从水房进入了侧院。八分钟过去了。"),
    ("n4-loc-003", [[0], [1]], "周砚离开了钟楼一路走到了柴房。前后大约十二分钟。"),
    ("n4-loc-004", [[0, 1]], "二十五分钟过去了，林望从侧院抵达石桥。"),
    ("n4-loc-005", [[0], [1]], "沈青由柴房进入碑亭。整整四十分钟过去了。"),
    ("n4-loc-006", [[0, 1]], "一小时过去，陈舟从东门一路走到了水房。"),
    ("n4-empty-007", [[0, 1]], "八分钟过去了，风平浪静。"),
    ("n4-empty-008", [[0, 1]], "十二分钟过去了，平静如常。"),
    ("n4-empty-009", [[0, 1]], "整整二十五分钟过去了，没有动静。"),
    ("n4-empty-010", [[0, 1]], "四十分钟过去了，一切照旧。"),
    ("n4-task-011", [[0], [1]], "陈舟已达成任务「把铜铃挂回钟楼」。前后约十二分钟。"),
    ("n4-task-012", [[0], [1]], "苏晚办妥了任务「整理柴房」。整整二十五分钟过去了。"),
    ("n4-task-013", [[0, 1]], "约四十分钟过去了，周砚已达成任务「修缮石桥栏杆」。"),
    ("n4-task-014", [[0], [1]], "林望办妥了任务「清点碑亭石刻」。前后大约一小时。"),
    ("n4-task-015", [[0], [1]], "陈舟已办妥任务「把铜铃挂回钟楼」。约三分钟过去了。"),
    ("n4-chain-016", [[0, 1, 2], [3]],
     "苏晚办妥了任务「整理柴房」，变得沉稳，"
     "精神值从10提升至13。前后大约二十五分钟。"),
    ("n4-chain-017", [[0, 1, 2], [3]],
     "周砚完成了任务「修缮石桥栏杆」，话多了起来，精神值从12涨到了14。"
     "整整四十分钟过去了。"),
    ("n4-chain-018", [[0, 1, 2], [3]],
     "林望达成了任务「清点碑亭石刻」，变得内敛，"
     "精神值从11升到了12。前后大约一小时。"),
    ("n4-appear-019", [[0, 1]], "四十分钟过去了，石桥的外观变了：门柱上的漆皮剥落了大半。"),
    ("n4-appear-020", [[0], [1]], "碑亭的外观变了：石阶缝里长出了青苔。前后约一小时。"),
    ("n4-appear-021", [[0, 1]], "约三分钟过去了，东门的外观变了：栏杆的漆色褪成了灰白。"),
    ("n4-multi-022", [[0, 1], [2]],
     "陈舟一路从东门来到了柴房，林望已经在柴房了。约三分钟过去了。"),
    ("n4-multi-023", [[0, 1, 2]],
     "八分钟过去了，苏晚从水房抵达石桥时，沈青已经在石桥了。"),
    ("n4-multi-024", [[0, 1], [2]],
     "周砚从钟楼进入碑亭，陈舟已经在碑亭了。前后大约十二分钟。"),
    ("n4-loc-025", [[0, 1]], "整整一小时过去了，沈青由柴房抵达东门。"),
    ("n4-task-026", [[0, 1]], "约三分钟过去了，林望已办妥任务「清点碑亭石刻」。"),
]


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    seeds = {}
    for line in SEEDS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            s = json.loads(line)
            seeds[s["sourceGroupId"]] = s

    out = []
    for gid, refs, text in REWRITES:
        seed = seeds[gid]
        row = dict(seed)
        row["rowOrigin"] = "rewrite"
        row["rewriter"] = "zcode-model"
        row["text"] = text
        row["planRefs"] = refs
        row["hashes"]["text"] = sha(text)
        row["purpose"] = ("N4 批量改写候选（风格教师；待整批抽验，微调仍暂停）")
        out.append(row)

    assert len(out) == len(seeds), f"rewrites {len(out)} != seeds {len(seeds)}"
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
                   encoding="utf-8")
    print(f"wrote {len(out)} rewrite rows -> {OUT}")


if __name__ == "__main__":
    main()
