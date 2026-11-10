"""Verify R2 identities and export metrics and every test prediction."""
import json
from pathlib import Path
import shutil
from train_r2 import DATA, ROOT, load_data, metrics, sha

def main():
    run=ROOT/'.local/d03-macbert/runs/macbert-r2'
    dest=DATA.parent
    result=json.loads((run/'summary.json').read_text())
    config=json.loads((run/'run.json').read_text())
    predictions=json.loads((run/'test-predictions.json').read_text())
    assert sha(DATA)==config['datasetSha256']
    assert sha(Path(__file__).with_name('train_r2.py'))==config['codeSha256']
    assert sha(dest/'protocol.md')==config['protocolSha256']
    assert sha(run/'model/model.safetensors')==result['checkpointSha256']
    assert metrics(predictions,result['threshold'])==result['test']
    rows={r['sceneId']:r for r in load_data() if r['split']=='test'}
    assert set(rows)=={p['sceneId'] for p in predictions}
    errors=[]
    for pred in predictions:
        row=rows[pred['sceneId']]
        names={c['id']:c['name'] for c in row['input']['characters']}
        assert set(pred['scores'])==set(names)
        assert pred['targetIds']==row['targetIds']
        selected={cid for cid,score in pred['scores'].items() if score>=result['threshold']}
        expected=set(row['targetIds'])
        if selected!=expected:
            errors.append({'sceneId':row['sceneId'],'characterCount':row['characterCount'],
                           'input':row['input'],'targetIds':sorted(expected),'predictedIds':sorted(selected),
                           'expectedNames':[names[c] for c in sorted(expected)],
                           'predictedNames':[names[c] for c in sorted(selected)],
                           'missedNames':[names[c] for c in sorted(expected-selected)],
                           'extraNames':[names[c] for c in sorted(selected-expected)],'scores':pred['scores']})
    for name in ['run.json','summary.json','test-predictions.json','base-manifest.json']:
        shutil.copyfile(run/name,dest/name)
    (dest/'test-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2))
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    audit=next(e for e in events if e['kind']=='audit')
    epochs=[e for e in events if e['kind']=='epoch']
    (dest/'learning-curve.json').write_text(json.dumps(epochs,ensure_ascii=False,indent=2))
    def table(label,m):
        return (f"| {label} | {m['exactCount']}/{m['scenes']} ({m['exactMatch']:.1%}) | "
                f"{m['fn']} | {m['fp']} | {m['emptyCorrect']}/{m['emptyCount']} |")
    text=[
        '# D03 第二轮：2–3 角色训练结果','', '日期：2026-11-10。','',
        '**'+('通过本轮简化场景探索门，未达到生产验收。' if result['exploratoryQualityGate'] else
              '未通过本轮简化场景探索门，不启动蒸馏。')+'**','',
        '角色数量含行动者：2 人场景有 1 个其他角色，3 人场景有 2 个其他角色。只考直接接触、给予和明确物品归属；同一机制的所有变体在同一划分中。没有删除候选或在输出后修正行动者标签。','',
        '## 实际训练','',
        '- 从原始 MacBERT-base 重新训练全部 102,269,186 个参数，不续训 R1；同一基座 revision 和下载哈希。',
        '- 8 轮 / 256 步，FP32 / MPS；seed42、batch8、lr2e-5；超参沿用首轮。',
        '- 24 个助手编写机制组，144 个实例、384 个候选对。训练/开发/测试：16/4/4 组，96/24/24 个实例。',
        f"- 最长输入 {audit['maxTokens']} tokens，全部事实和候选进入模型，没有截断。",
        f"- 开发集选中第 {result['selectedEpoch']} 轮、阈值 {result['threshold']:.2f}。保存重载后进行一次最终测试。",
        f"- 运行内计时 {result['seconds']:.1f} 秒。",'',
        '## 结果','',
        '| 数据范围 | 完整目标集合正确 | 漏目标 | 错选目标 | 空集正确 |',
        '|---|---:|---:|---:|---:|',
        table('训练（拟合诊断）',result['train']), table('开发（用于选择）',result['development']),
        table('测试总计',result['test']), table('测试：2人',result['testByCharacterCount']['2']),
        table('测试：3人',result['testByCharacterCount']['3']), table('测试：全空基线',result['allNoneBaseline']), '',
        f"非空测试集合正确 {result['testNonempty']['exactCount']}/{result['testNonempty']['scenes']}；测试逐关系 precision {result['test']['precision']:.1%}，recall {result['test']['recall']:.1%}；4 个来源机制组的全部6变体同时正确率为 {result['test']['groupExactMatch']:.1%}。",'',
        f"本机完整名册推理中位数 {result['testLatencyMs']['median']:.1f} ms，最大 {result['testLatencyMs']['max']:.1f} ms，包含重新分词与设备同步，排除模型首次加载。不是浏览器或完整非叙事链500ms验收。",'',
        '## 边界','',
        '数据全部为助手合成草稿，人工复核数为0；不同机制仍共享句式模板。即使本轮分数提高，也只证明这个简化分布下的表现，不能证明自然故事中的影响推理或正式教师资格。', '',
        '与 R1 相比，本轮不仅减少角色数，也简化了关系、动作和背景；测试集不同，不能把成绩差值当作“仅减少人数”的因果收益。R1 数据、模型和报告完整保留。', '',
        '本轮没有进入小模型蒸馏、浏览器或产品接线。后续若继续，应先在2–3人约束下补充独立措辞、真实空集、否定及对象归属混淆，并另建来源隔离测试。失败也不能据此断定 MacBERT 架构不适用。','',
        '## 错例','',
    ]
    if not errors:
        text+=['本次测试无集合错误；样本与构造方式的限制仍然成立。','']
    for error in errors:
        text += [f"### {error['sceneId']}",'',error['input']['world'],'',error['input']['action'],'',
                 '应选：'+('、'.join(error['expectedNames']) or '空集')+'。',
                 '实选：'+('、'.join(error['predictedNames']) or '空集')+'。','']
    text += ['## 文件和验证','',
             '7项工程测试通过（包括原4项和新增3项）：分组及哈希、2–3人约束、标签隔离、全空基线和集合计分。报告重验数据、协议、训练源码、权重身份及原始测试指标。','',
             '- [协议](protocol.md)、[数据](scenes.jsonl)、[清单](data-manifest.json)。',
             '- [指标](summary.json)、[每轮开发结果](learning-curve.json)、[测试预测](test-predictions.json)、[错例](test-errors.json)。',
             '- [源码说明](../../../../experiments/d03-macbert/README.md)。',
             '- 本地权重及原始日志：`.local/d03-macbert/runs/macbert-r2/`。',
             '- 未提交、推送或发布模型。','']
    (dest/'report.md').write_text('\n'.join(text))
    print(json.dumps({'verified':True,'errors':len(errors),'report':str(dest/'report.md')},ensure_ascii=False))

if __name__=='__main__':
    main()
