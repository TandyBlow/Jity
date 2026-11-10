"""Verify and publish a compact report from the completed, immutable run."""
import json
from pathlib import Path
import shutil
from train import ROOT, DATA, load_data, metrics, sha

def main():
    run = ROOT / '.local/d03-macbert/runs/macbert-r1'
    dest = DATA.parent
    result = json.loads((run / 'summary.json').read_text())
    config = json.loads((run / 'run.json').read_text())
    records = json.loads((run / 'test-predictions.json').read_text())
    assert metrics(records, result['threshold']) == result['test']
    assert sha(DATA) == config['datasetSha256']
    assert sha(Path(__file__).with_name('train.py')) == config['codeSha256']
    assert sha(dest / 'protocol.md') == config['protocolSha256']
    assert sha(run / 'model/model.safetensors') == result['checkpointSha256']
    rows = {r['sceneId']:r for r in load_data() if r['split'] == 'test'}
    assert set(rows) == {r['sceneId'] for r in records}
    errors = []
    for record in records:
        row = rows[record['sceneId']]
        roster = {c['id']:c['name'] for c in row['input']['characters']}
        assert set(record['scores']) == set(roster)
        assert record['targetIds'] == row['targetIds']
        pred = {cid for cid, score in record['scores'].items() if score >= result['threshold']}
        gold = set(record['targetIds'])
        if pred != gold:
            errors.append({'sceneId':row['sceneId'], 'world':row['input']['world'],
                           'action':row['input']['action'],
                           'expectedNames':[roster[c] for c in sorted(gold)],
                           'predictedNames':[roster[c] for c in sorted(pred)],
                           'missedNames':[roster[c] for c in sorted(gold-pred)],
                           'extraNames':[roster[c] for c in sorted(pred-gold)],
                           'scores':record['scores']})
    for source in ['summary.json','run.json','base-manifest.json','test-predictions.json']:
        shutil.copyfile(run/source, dest/source)
    (dest/'test-errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2))
    def line(label, metric):
        return (f"| {label} | {metric['exactCount']}/{metric['scenes']} "
                f"({metric['exactMatch']:.1%}) | {metric['precision']:.1%} | {metric['recall']:.1%} "
                f"| {metric['fn']} | {metric['fp']} | {metric['emptyCorrect']}/{metric['emptyCount']} |")
    lines = [
        '# D03 MacBERT 实测结果', '', '日期：2026-11-10。', '',
        '**结论：' + ('通过短场景探索门，尚未达到正式教师或上线验收。' if result['exploratoryQualityGate'] else
                       '本轮未通过预登记质量门，不启动 MiniRBT 蒸馏。') + '**', '',
        '已完成 MacBERT 全参数微调、保存重载和冻结测试。不是只搭建脚本，也不是随机模型演示。', '',
        '## 实验身份', '',
        '- 官方模型：hfl/chinese-macbert-base；revision a986e004d2a7f2a1c2f5a3edef4e20604a974ed1。',
        '- 102,269,186 个可训练参数，FP32 / Apple MPS；8 轮、256 个优化步。',
        '- 48 个新编来源场景，96 个正负对照实例，384 个候选对；训练/开发/测试来源组 32/8/8。',
        '- 输入保留每条短场景的全部事实和完整候选名册，实测最长 181 tokens，无截断。',
        f"- 仅开发集选择第 {result['selectedEpoch']} 轮检查点和阈值 {result['threshold']:.2f}，之后一次最终测试。",
        f"- 运行内计时 {result['seconds']:.1f} 秒；不包括下载和环境准备。", '',
        '## 分数', '',
        '| 集合 | 完整目标集合正确 | 精确率 | 召回率 | 漏目标 | 错选目标 | 空集正确 |',
        '|---|---:|---:|---:|---:|---:|---:|',
        line('训练（拟合诊断）',result['train']), line('开发（用于选择）',result['development']),
        line('测试（未用于拟合/选择）',result['test']), line('测试全空基线',result['allNoneBaseline']), '',
        f"测试按来源组的双对照同时正确率：{result['test']['groupExactMatch']:.1%}。不能把角色对数量当作独立样本量。", '',
        f"完整 4 人候选批次本机推理中位数 {result['testLatencyMs']['median']:.1f} ms，最大 {result['testLatencyMs']['max']:.1f} ms。包含重新分词和设备同步，不包含模型首次加载，不等于浏览器或完整非叙事链的 500ms 验收。", '',
        '## 测试错误', '',
    ]
    if not errors: lines += ['本次 16 个短场景实例无集合错误；样本和来源规模仍很小。', '']
    for error in errors:
        lines += [f"### {error['sceneId']}", '', error['world'], '', error['action'], '',
                  '应选：' + ('、'.join(error['expectedNames']) or '空集') + '。',
                  '实选：' + ('、'.join(error['predictedNames']) or '空集') + '。', '']
    lines += [
        '## 证据边界与下一步', '',
        '本轮 8 个非空测试实例仅 2 个完整集合正确，而 8 个空目标实例全部正确；总体 62.5% 不应掩盖目标身份判断的失败。训练集完整集合也只有 65.6%，因此不能仅将失败归因为过拟合或跨场景泛化不足。', '',
        '例如：解开井中人物的安全绳时选中了井外人物；递交密信时漏掉收件人并选中旁人。错误说明当前训练结果尚不能稳定绑定行动与正确角色；是否来自样本规模、角色表示、训练不足或其他因素，需要后续对照，当前不能确定因果。', '',
        '数据全部为助手编写草稿，人工复核数为 0。测试与训练有共同作者、构造方法和正负对照风格，不能声称独立泛化、真实游戏表现或人审通过。', '',
        '本轮只支持对这套短场景训练设置的判断，不能据此证明 MacBERT 不适合 D03，也不能证明教师已具备完整因果理解。尚未覆盖长世界输入、复杂关系链、连续组上下文及生产接口；原始完整世界输入的适配仍待实现。', '',
        '下一轮应先扩大并复核场景和影响边界，增加难负例、条件/否定/阻挡关系、远端物品或任务影响及更多目标数；本测试集已经曝光，应作为回归资料保留，新一轮另建来源隔离测试，不以本轮错误改题后再宣称未见泛化。', '',
        '## 工程验证与文件', '',
        '4 项工程测试通过：分组及数据身份、跨集合泄漏拒绝、标签独立输入与事实/候选覆盖、集合指标对漏选/误选/空集的正确计数。报告生成重新核验数据、协议、训练源码、模型 SHA 与原始测试分数。', '',
        '初次使用旧环境在导入依赖阶段阻塞，未进入训练或创建运行记录；检查发现旧依赖存在云端占位文件，停止该进程后新建独立 Python 3.12 环境。实际训练仅此一轮，未改变数据和超参。完整依赖版本见 environment-lock.txt。', '',
        '- [实验协议](protocol.md)、[数据清单](data-manifest.json)、[原始场景](scenes.jsonl)。',
        '- [指标](summary.json)、[测试原始分数](test-predictions.json)、[错例](test-errors.json)。',
        '- [源码与运行说明](../../../experiments/d03-macbert/README.md)。',
        '- 权重/事件日志：仓库本地 `.local/d03-macbert/runs/macbert-r1/`。', '',
        '没有修改产品、旧 D 训练产物或其他并行任务；没有提交、推送或发布权重。',
    ]
    (dest/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'verified':True,'errors':len(errors),'report':str(dest/'report.md')},ensure_ascii=False))

if __name__ == '__main__':
    main()
