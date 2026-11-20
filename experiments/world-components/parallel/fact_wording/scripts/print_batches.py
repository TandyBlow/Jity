"""Compact view of blind batches for judging (no scheme, score, unit id)."""
import json, re, sys, pathlib

def compact(item):
    fact = item["fact"]
    kind = fact.get("kind")
    if kind == "moved":
        spec = f'{fact["name"]} {fact.get("from")}->{fact.get("to")} dir={fact.get("direction")}'
    elif kind == "sanity_changed":
        spec = f'{fact["name"]} sanity {fact.get("from")}->{fact.get("to")}'
    elif kind == "appearance_changed":
        spec = f'{fact["name"]} 外貌 {fact.get("text")}'
    else:
        spec = f'{fact["name"]} 结果 {fact.get("resultText")}'
    inp = item["input"]
    place = re.search(r"地点=([^\n]+)", inp)
    vis = re.search(r"地点可见=([^\n]+)", inp)
    scene = re.search(r"场景=([^\n]+)", inp)
    return (f'{item["code"]} | {kind} | {spec}\n'
            f'   地点={place.group(1) if place else "?"} | 场景={scene.group(1) if scene else "?"}\n'
            f'   可见={vis.group(1) if vis else "?"}\n'
            f'   输出: {item["output"]}')

args = sys.argv[1:]
run = None
if "--run" in args:
    i = args.index("--run")
    run = pathlib.Path(args[i + 1])
    args = args[:i] + args[i + 2:]
if run is None:
    root = pathlib.Path(__file__).resolve().parents[1] / "artifacts/fact-wording/diagnostic-r1"
    run = sorted(root.glob("*/blind"))[-1]
for name in args:
    data = json.loads((run / name).read_text(encoding="utf-8"))
    print(f'== {name}')
    for item in data["items"]:
        print(compact(item))
