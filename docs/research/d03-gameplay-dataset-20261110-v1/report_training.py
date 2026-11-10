import json
import shutil
from pathlib import Path
from train import DATA, ROOT, PARENT, PARENT_SHA, load_data, metrics, sha

def main():
    out=DATA.parent
    run=ROOT/'.local/d03-gameplay/runs/gameplay-v1'
    config=json.loads((run/'run.json').read_text())
    summary=json.loads((run/'summary.json').read_text())
    pred=json.loads((run/'test-predictions.json').read_text())
    parent=json.loads((run/'parent-on-new-test.json').read_text())
    regression=json.loads((run/'r2-regression-predictions.json').read_text())
    assert sha(DATA)==config['datasetSha256']
    assert sha(out/'train.py')==config['codeSha256']
    assert sha(out/'training-protocol.md')==config['protocolSha256']
    assert sha(run/'model/model.safetensors')==summary['checkpointSha256']
    assert sha(PARENT/'model/model.safetensors')==PARENT_SHA
    assert metrics(pred,summary['threshold'])==summary['test']
    ps=json.loads((PARENT/'summary.json').read_text())
    assert metrics(parent,ps['threshold'])==summary['parentOnNewTest']
    assert metrics(regression,summary['threshold'])==summary['r2Regression']
    rows={r['sceneId']:r for r in load_data() if r['split']=='test'}
    assert set(rows)=={r['sceneId'] for r in pred}
    cases=[]
    for p in pred:
        row=rows[p['sceneId']]
        names={c['id']:c['name'] for c in row['input']['characters']}
        assert set(names)==set(p['scores'])
        assert row['targetIds']==p['targetIds']
        selected=sorted(k for k,v in p['scores'].items() if v>=summary['threshold'])
        cases.append({'sceneId':p['sceneId'],'action':row['input']['action'],
                      'expected':[names[c] for c in p['targetIds']],
                      'predicted':[names[c] for c in selected],
                      'correct':set(selected)==set(p['targetIds']),'scores':p['scores']})
    for f in ['summary.json','run.json','test-predictions.json','train-predictions.json',
              'parent-on-new-test.json','r2-regression-predictions.json','events.jsonl']:
        shutil.copyfile(run/f,out/f)
    (out/'test-case-review.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
    events=[json.loads(s) for s in (run/'events.jsonl').read_text().splitlines()]
    audit=next(e for e in events if e['kind']=='audit')
    steps=next(e['steps'] for e in events if e['kind']=='training_start')
    def line(label,m):
        return f"| {label} | {m['exactCount']}/{m['scenes']} | {m['fn']} | {m['fp']} | {m['emptyCorrect']}/{m['emptyCount']} |"
    lines=['# 游戏剧情首轮训练结果','',
        '2026-11-10。用户已认可17条可用标注并授权训练；7条待裁定候选仍排除。原草稿记录的pending状态保留作历史，当前接受范围见data-manifest.json。','',
        '**'+('通过这6条游戏测试的探索门及旧基础题回归。' if summary['curriculumGate'] else '未同时通过游戏测试探索门与旧基础题回归。')+'**','',
        '## 实际执行','',
        '- 从R3选中模型继续微调全部MacBERT参数，仅用本批7条真实录制行动样本；未混入合成训练数据或新改写。',
        '- game-01/02训练7条；game-03开发4条；game-04测试6条。同一游戏不跨集合，明显歧义已排除。',
        f'- 8轮，{steps}个优化步，FP32/MPS，seed42，batch8，lr2e-5。最长完整输入{audit["maxTokens"]}tokens，无截断。',
        f'- 开发集选择第{summary["selectedEpoch"]}轮、阈值{summary["threshold"]:.2f}，保存重载后测试一次。',
        f'- 运行内用时{summary["seconds"]:.1f}秒。主聊天的旧模型不覆盖。','',
        '| 范围 | 完整目标集合正确 | 漏选 | 误选 | 空集正确 |',
        '|---|---:|---:|---:|---:|',
        line('本次训练集',summary['train']),line('开发集（用于选择）',summary['development']),
        line('R3父模型在同一游戏测试上',summary['parentOnNewTest']),line('本次模型游戏测试',summary['test']),
        line('旧R2基础题回归',summary['r2Regression']),line('全空基线（游戏测试）',summary['allNoneBaseline']),'',
        '## 六个测试实例','', '| 行动 | 应选 | 实选 | 正确 |','|---|---|---|---|']
    for c in cases:
        lines.append(f"| {c['action']} | {'、'.join(c['expected']) or '空集'} | {'、'.join(c['predicted']) or '空集'} | {'是' if c['correct'] else '否'} |")
    lines+=['','## 解释边界','',
        '用户认可了标注，但测试只有game-04的一条路线、6个相关片段。所有阳性目标都是诺诺；四个游戏共享背景。即使6/6，也不能据此声称完整D03、多人目标选择、跨故事泛化或稳定准确率。','',
        '模型输入只有行动前局部摘要和原始玩家行动，未知已行动状态明确显示未知。原始完整叙事、来源证据、标签和骰点没有拼入模型。此轮证明的是有限游戏片段上的可行性，不代表完整世界输入适配。','',
        f'本机全名册批次推理中位{summary["testLatencyMs"]["median"]:.1f}ms，最大{summary["testLatencyMs"]["max"]:.1f}ms；含分词和设备同步，不含首次加载，不代表浏览器或完整非叙事链500ms验收。','',
        '3项工程测试已通过：冻结可用子集与游戏划分、排除标签/审计信息且保留未知状态、集合指标。报告另核验输入、协议、代码、父子模型哈希，并从预测复算指标。没有替换产品模型、蒸馏、提交或上传。','',
        '- [协议](training-protocol.md)、[接受记录](data-manifest.json)、[原始样本表](README.md)。',
        '- [指标](summary.json)、[逐例结果](test-case-review.json)、[完整分数](test-predictions.json)。',
        f'- 模型：`{run / "model"}`。','',
        '复现命令（从仓库根目录；运行目录必须未存在）：','',
        '```sh',
        '.local/d03-macbert/venv/bin/python docs/research/d03-gameplay-dataset-20261110-v1/train.py --run gameplay-v1 --device mps',
        '```','']
    (out/'training-report.md').write_text('\n'.join(lines))
    print(json.dumps({'verified':True,'testCorrect':sum(c['correct'] for c in cases),'report':str(out/'training-report.md')},ensure_ascii=False))

if __name__=='__main__':main()
