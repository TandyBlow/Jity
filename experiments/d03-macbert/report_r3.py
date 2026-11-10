"""Verify the selected R3 model, same-test parent comparison and R2 regression."""
import json
from pathlib import Path
import shutil
from train_r3 import DATA, ROOT, PARENT, PARENT_SHA, load_data, metrics, sha

def main():
    run=ROOT/'.local/d03-macbert/runs/macbert-r3'
    dest=DATA.parent
    result=json.loads((run/'summary.json').read_text())
    config=json.loads((run/'run.json').read_text())
    predictions=json.loads((run/'test-predictions.json').read_text())
    parent_predictions=json.loads((run/'parent-on-new-test.json').read_text())
    regression=json.loads((run/'r2-regression-predictions.json').read_text())
    assert sha(DATA)==config['datasetSha256']
    assert sha(Path(__file__).with_name('train_r3.py'))==config['codeSha256']
    assert sha(dest/'protocol.md')==config['protocolSha256']
    assert sha(run/'model/model.safetensors')==result['checkpointSha256']
    assert sha(PARENT/'model/model.safetensors')==PARENT_SHA==config['parentCheckpointSha256']
    assert metrics(predictions,result['threshold'])==result['test']
    assert metrics(parent_predictions,.5)==result['parentOnNewTest']
    assert metrics(regression,result['threshold'])==result['r2Regression']
    rows={r['sceneId']:r for r in load_data() if r['split']=='test'}
    oldrows={r['sceneId']:r for r in load_data(ROOT/'docs/research/d03-macbert/r2/scenes.jsonl') if r['split']=='test'}
    def audit_and_errors(records,lookup,threshold):
        assert set(lookup)=={p['sceneId'] for p in records}
        errors=[]
        for pred in records:
            row=lookup[pred['sceneId']]
            names={c['id']:c['name'] for c in row['input']['characters']}
            assert set(pred['scores'])==set(names)
            assert pred['targetIds']==row['targetIds']
            selected={cid for cid,score in pred['scores'].items() if score>=threshold}
            expected=set(row['targetIds'])
            if selected!=expected:
                errors.append({'sceneId':row['sceneId'],'sourceGroup':row['sourceGroup'],
                    'category':row.get('category','r2_regression'),'input':row['input'],
                    'targetIds':sorted(expected),'predictedIds':sorted(selected),
                    'expectedNames':[names[c] for c in sorted(expected)],
                    'predictedNames':[names[c] for c in sorted(selected)],
                    'missedNames':[names[c] for c in sorted(expected-selected)],
                    'extraNames':[names[c] for c in sorted(selected-expected)],'scores':pred['scores']})
        return errors
    errors=audit_and_errors(predictions,rows,result['threshold'])
    parent_errors=audit_and_errors(parent_predictions,rows,.5)
    regression_errors=audit_and_errors(regression,oldrows,result['threshold'])
    for filename in ['run.json','summary.json','test-predictions.json','base-manifest.json',
                     'parent-on-new-test.json','r2-regression-predictions.json']:
        shutil.copyfile(run/filename,dest/filename)
    for name,records in [('test-errors',errors),('parent-errors',parent_errors),('regression-errors',regression_errors)]:
        (dest/(name+'.json')).write_text(json.dumps(records,ensure_ascii=False,indent=2))
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    audit=next(e for e in events if e['kind']=='audit')
    (dest/'learning-curve.json').write_text(json.dumps([e for e in events if e['kind']=='epoch'],ensure_ascii=False,indent=2))
    def table(label,m):
        return (f"| {label} | {m['exactCount']}/{m['scenes']} ({m['exactMatch']:.1%}) | "
                f"{m['fn']} | {m['fp']} | {m['emptyCorrect']}/{m['emptyCount']} |")
    labels={'ownership':'归属与借用','reference':'人物指代','condition':'条件与否定','isolation':'传播与隔离'}
    lines=['# D03 第三轮：表达变化与关系难度','', '日期：2026-11-10。','',
        '**'+('通过本轮探索质量及旧题回归门，尚不代表生产或独立泛化通过。' if result['curriculumGate'] else
              '未同时通过新质量门与旧题回归门，不启动蒸馏或替换原模型。')+'**','',
        '## 实际执行','',
        '- 总人数仍为2–3（含行动者）；增加归属借用、明确指代、条件否定、简单传播/隔离。',
        '- 新增24个来源机制组，每组2个对照×3种表达，共144实例；同组所有改写及对照保持同一划分。',
        '- 新训练96实例加R2训练复习96实例：合计192实例508候选对；新开发/测试各24实例66候选对，分别来自4个来源组。',
        '- 从R2选中第4轮的完整模型继续微调；不重置分类头，不使用R2开发/测试训练。',
        '- 8轮、512优化步，FP32/MPS，seed42，batch8，lr2e-5，其余超参见协议。',
        f"- 最长输入{audit['maxTokens']}tokens，完整事实与候选进入模型，不截断。",
        f"- 仅用新开发集选择第{result['selectedEpoch']}轮、阈值{result['threshold']:.2f}；保存重载后一次最终测试。",
        f"- 运行内计时{result['seconds']:.1f}秒，包括最终评测，不含环境准备。",'',
        '## 结果','',
        '| 范围 | 完整目标集合正确 | 漏目标 | 错选目标 | 空集正确 |',
        '|---|---:|---:|---:|---:|',
        table('R3训练（新题+复习）',result['train']),table('R3开发（用于选择）',result['development']),
        table('R2模型在本轮新测试上',result['parentOnNewTest']),table('R3模型在本轮新测试上',result['test']),
        table('R3在R2旧测试上（回归）',result['r2Regression']),
        table('新测试全空基线',result['allNoneBaseline']), '',
        'R2旧测试在R2模型上的历史成绩为24/24；该资料已曝光，只作回归，不作为新的独立测试。父模型同题对照是在本轮训练及选择结束后以父模型固定阈值0.5执行，结果没有回流训练。','',
        '| 新测试子集 | 完整目标集合正确 | 漏目标 | 错选目标 | 空集正确 |',
        '|---|---:|---:|---:|---:|',
        table('2人',result['testByCharacterCount']['2']),table('3人',result['testByCharacterCount']['3']),
    ]
    for category,m in result['testByCategory'].items():
        lines.append(table(labels[category],m))
    lines+=['',f"非空集合正确 {result['testNonempty']['exactCount']}/{result['testNonempty']['scenes']}；新测试precision {result['test']['precision']:.1%}、recall {result['test']['recall']:.1%}。来源组全部6变体同时正确率 {result['test']['groupExactMatch']:.1%}。",'',
        f"本机完整候选批次推理中位{result['testLatencyMs']['median']:.1f}ms、最大{result['testLatencyMs']['max']:.1f}ms。含重新分词及设备同步，不含模型首次加载，不是浏览器或完整非叙事链500ms验收。",'',
        '## 限制','',
        '全部为助手合成标签，未经人工审核。4个新测试来源组各含6个相关变体；24实例不是24个独立来源，各类别仅1个测试机制，分类得分不能代表整个能力领域。改写仍共享作者与构造习惯，真实叙事适用性待验证。','',
        '本轮变更训练起点、数据量与关系难度，不是只改变单一因素的消融。物品所有人与借用者均受影响、明确不满足条件时不执行等判据是本轮草稿约定，尚需人工确认与正式D03契约对齐。','',
        '没有蒸馏、产品接线或上传模型。若继续，应针对新开发集暴露的问题设计更丰富且独立审核的数据；本轮测试已曝光，必须保留为回归，不能改题再声称未见泛化。','',
        '## 新测试错例','']
    if not errors: lines+=['本轮新测试没有集合错误。','']
    for error in errors:
        lines += [f"### {error['sceneId']}",'',error['input']['world'],'',error['input']['action'],'',
                  '应选：'+('、'.join(error['expectedNames']) or '空集')+'。',
                  '实选：'+('、'.join(error['predictedNames']) or '空集')+'。','']
    lines+=['## 文件与验证','',
        '9项工程测试通过，新增核对来源分组、对照/改写完整性、只复习旧train、2–3人约束、标签不进入输入及完整事实保留。报告重验数据、协议、源码、父/子模型SHA，并从原始预测复算三个评测的指标。','',
        '- [协议](protocol.md)、[数据](scenes.jsonl)、[清单](data-manifest.json)。',
        '- [指标](summary.json)、[新测试预测](test-predictions.json)、[父模型同题预测](parent-on-new-test.json)、[旧题回归](r2-regression-predictions.json)。',
        '- [新错例](test-errors.json)、[回归错例](regression-errors.json)、[学习记录](learning-curve.json)。',
        '- 本地模型与日志：`.local/d03-macbert/runs/macbert-r3/`。R1/R2保持原样。','']
    (dest/'report.md').write_text('\n'.join(lines))
    print(json.dumps({'verified':True,'testErrors':len(errors),'regressionErrors':len(regression_errors),'report':str(dest/'report.md')},ensure_ascii=False))

if __name__=='__main__':
    main()
