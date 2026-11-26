# -*- coding: utf-8 -*-
"""Score the real 2026-11-26 condition/fact rows with the trained int8 model."""
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODEL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / '.local/micro-heads/task-condition-int8.onnx'
WITH_GOAL = len(sys.argv) > 2 and sys.argv[2] == 'goal'
LABELS = ['none', 'keyword', 'attempt', 'satisfied']

ROWS = [
    ('goggles/item', '把胸前护目镜戴好并确认镜片没有裂纹', 'item：路明非的护目镜', '路明非拿起护目镜。（达到目的）'),
    ('goggles/action-turn1', '把胸前护目镜戴好并确认镜片没有裂纹', 'action：戴好', '路明非拿起护目镜。（达到目的）'),
    ('goggles/action-turn2', '把胸前护目镜戴好并确认镜片没有裂纹', 'action：戴好', '路明非把护目镜戴好。（达到目的）'),
    ('goggles/conf-turn3', '把胸前护目镜戴好并确认镜片没有裂纹', 'confirmation：确认', '路明非检查镜片有没有裂纹。（达到目的）'),
    ('kit/action-turn1', '在进入交火区前拿到可用的护目镜与演习装备', 'action：进入', '路明非拿起护目镜。（达到目的）'),
    ('match/conf-turn3', '在自由一日结束前作出自己的参赛选择，并完成一次能由在场人确认的有效行动后安全离场', 'confirmation：确认', '路明非检查镜片有没有裂纹。（达到目的）'),
    ('choice/conf-turn3', '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', 'confirmation：问清', '路明非检查镜片有没有裂纹。（达到目的）'),
    ('chu/action', '守住钟楼顶层', 'action：守住', '楚子航守住顶层。（达到目的）'),
    ('fingel/action', '把相机备用电池换上并拍到有辨识度的争旗场面', 'action：换上', '在芬格尔的相机备用电池和检修门插闩的指引下，准备拍摄有辨识度的争旗场面（达到目的）'),
    ('tang/ammo', '从器材棚取回备用弹匣并换上', 'action：更换', '拦住靠近的敌人（达到目的）'),
]


def main():
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    session = ort.InferenceSession(str(MODEL), providers=['CPUExecutionProvider'])
    for name, goal, condition, fact in ROWS:
        context = f'任务：{goal}\n条件：{condition}' if WITH_GOAL else f'条件：{condition}'
        enc = tok(context, fact, truncation=True, max_length=160)
        ids = np.array([enc['input_ids']], dtype=np.int64)
        mask = np.array([enc['attention_mask']], dtype=np.int64)
        logits = session.run(['labels'], {'input_ids': ids, 'attention_mask': mask})[0][0]
        probs = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum()
        best = int(probs.argmax())
        print(f'{name:22} {LABELS[best]:9} {probs[best]:.3f}  {condition} | {fact[:38]}')


if __name__ == '__main__':
    main()
