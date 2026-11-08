from pathlib import Path
import sys,json,shutil,hashlib
sys.path.insert(0,'/Users/davidz/Documents/GitHub/jity-eval')
from jity_eval.question_bank import read,leaves,checkpoint,source_name
from jity_eval.storage import atomic_json
from jity_eval.question_bank_revision import inventory,file_sha
root=Path('/Users/davidz/Documents/GitHub/jity-eval');b=root/'question_banks/full-games-20261106-v1.2';prev=root/'question_banks/full-games-20261106-v1.1'
readme='''# Jity 长期一致性题库 v1.2 人工审阅版

版本 `1.2.0-review`，12个稳定ID、4局、原检查点及最近6次提交行动窗口不变。全部 `pending_human_review`；用户意见是修订依据，自动核验不等于人工验收。本次无模型回答、付费API、游戏行动或Git提交。

## 交付文件与隐私边界

- `public/questions.json`：题目、稳定ID、游戏、数据版本、检查点指纹；只有通用recall/action类型。
- `public/inputs/<ID>/{full,recent,state}.json`：36份冻结输入，每题未来独立作答，每次只提供相应一份。没有未知、诊断、控制或评分提示。
- `private/answers.json`：标准答案、可接受表述、33个语义评分要点、分值、部分分、典型错误。
- `private/scoring-policy.json`：统一的正确、遗漏、错误、额外无依据断言、矛盾及来源归属规则。
- `private/authoring.json`、`private/revision-spec.json`：作者稿和本次机器可读修订规格。
- `audit/evidence.json`：200条原始/冻结输入引用，路径、JSON Pointer、最小摘录、行动、节点及指纹。清单缺失证据用名称投影，不把整个无关物品文本作为答案。
- `audit/points.json`：逐要点首次、最近明确披露、更新、两种间隔、实际三组支持程度及对应字段证据。`historical_evidence_exists`表示答案或不足判断有历史支持；`target_value_explicitly_disclosed`另行区分具体值是否曾披露。
- `audit/items.json`：保留整题最近公开相关话题间隔，附逐要点审计链接、原冲突及待复核项。
- `audit/disclosure-scan.json`：完整output（含选项、检定条件、提交更新）及实际行动的检索候选。命中是候选，不自动等于明确重述；语义裁决见points。未选择的未来行动/失败条件不当已发生事件。
- `audit/unknown-scope-search.json`：沿用并核验的未知题完整历史前缀排查；分别限定initial0–A42及initial0–A38。
- `audit/dataset.json`、`private/candidates.json`：原来源资格、异常和候选区原样保留。
- `audit/changes.json`、`CHANGES.md`：逐题修改、原因和评分含义变化。
- `reports/review.html`：浏览器私有审阅报告，可按历史事实、诊断或控制用途筛选，展开逐要点原文和组内证据。
- `manifest.json` / `manifest.sha256`：题目、输入、答案、审计的核心版本指纹；`delivery.sha256.json` / `.sha256`：包括报告、说明、测试和浏览器核验的完整交付文件指纹。

除public单题输入外，上述材料都不能交给待测模型。原始近期记录自然携带的答案事实是合法内容，不用答案关键词过滤来删改输入。验证器逐项比对v1.1并从原始冻结记录重建，输入中只有问题和统一说明发生改变，context完全相等。题库版本独立于未变的数据封存版本。

统一模型说明：**仅依据本次提供的记录回答；无法确定时明确说明，不补造事实。行动题只判断和解释，不执行行动。**

## 评分与间隔

按准确表达或清楚蕴含的语义事实评分，不要求内部字段、逐字匹配或重复免责声明。同一语义不重复给分；“没犯错”本身不给分。遗漏为0，部分表达按各点规则；额外无依据断言单列标记，如改变所问结论或依据使相关点为0。结论与理由互相矛盾时，相关判断/依据点不能靠堆词得分。各题总分不同，尚未定义跨题汇总或模型成绩。

G02-Q02只答不知道可得未知结论1/3分，人物描述与芬格尔搬箱角色必须正面正确才得其分。G03-Q03只答不知道为1/2分，准确指出记录未给出值等依据再得1分。二者均接受“本次提供的信息不足”，不要求近期组替未见的全局历史作断言。

保留整题话题间隔。逐点明确披露间隔分别为检查点行动序号差、`progress.turns_total`战役推进差。时间线节点仅作标识，链路由已验证录制核对，不用节点ID直接相减。持久world_facts、摘要与物品账本在检查点持续可见，单列通道曝光，不计作新剧情披露。

未知姓名/数值本身没有首次明确披露；对应位置及间隔为null并说明原因。支持“不足”结论的正面线索有各自证据位置；完整前缀审查不注入模型输入。其输入支持“完整”表示有界不足判断可成立，不表示目标姓名或数值已经提供。

G03-Q01首次结构化持有为initial0，首次叙事A1，移交A24。检查点A35距首次持有35次提交/34次推进；原最近相关话题A27及8次提交/7次推进不变。

## 用途、覆盖和解释限制

四局已有真实结束及严格重放通过证据；提交行动分别55、52、52、51，有效推进均50。均以预算结束的“未竟的追寻”收束，不代表主线通关。本轮只读核对既有重放结果及原始封存934文件，没有重新重放。未结束smoke和冲突事件仍在候选区。PCB提取失败、嵌入404/回退、解析及结局重试等原始限制继续保留。

历史事实/状态判断题考察任务、人物证言、物品遗失/移交、后证据更新及可行性。没有明确consumed账本事件，不将遗失、移交或毁坏冒称消耗。没有补造正向行动事件；目前三道行动题的核心结论均为否定，存在标签分布偏向。

- G02-Q03是记忆保留诊断题：历史有“七枚、三枚较新”，当前full/recent/state均不含这两个数量。
- G04-Q03兼有历史事实与保留诊断用途：实际full/state保留试锁失败及反应，兜帽人的解释和来源已经遗漏；recent仅有相关实体。历史标准答案及解释评分要求仍保留。
- G03-Q03是近期未知控制，不代表长间隔遗忘。
- G04-Q02是0间隔近期状态控制，不作为长期记忆优势证据。
- G04-Q01身份、档案记载、亲手封存数字分别审计；帮助理由只透露部分。亲手细节full需跨真实摘要与状态合并，指代仍待人工复核。

多题答案合法存在world_facts、人物信息及物品账本，state可以答对。full为录制时实际摘要，不等于全历史或完美记忆。未保留证据的题可诊断系统，但不能单独证明回答模型在已得到全部证据条件下的能力。历史支持是否存在、输入是否保留、未来回答是否正确分开存储，最后一项全部not_run。

12题来自4局内部相关观察，不能视为12个独立游戏样本；36份输入也不是36个回答。未来实验应独立启动每个题目×组别，禁止前题答案进入后题记忆；应按游戏处理相关性，不在本次计算成绩。

## 离线使用

在jity-eval目录，用已有Python 3.11环境执行（不联网）：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank_revision validate question_banks/full-games-20261106-v1.2 --check-original
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m unittest discover -s tests -p 'test_question_bank_revision.py' -v
```

直接在浏览器打开`reports/review.html`审阅。旧版本验证器仍用于v1.1；新版输入公共说明不同，请使用上述revision验证器。不要把本库交给旧模拟器当作真实模型实验。

需要重建时必须选择不存在的新输出目录，禁止覆盖版本：

```sh
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/envs/jity-backend/bin/python -m jity_eval.question_bank_revision build --previous question_banks/full-games-20261106-v1.1 --spec question_banks/full-games-20261106-v1.2-authoring/spec.json --output question_banks/my-new-review-copy
```

该命令只构建核心JSON和冻结源，HTML由revision report命令生成。报告和说明是私有派生交付；任何后续修订须建立新版本，并重做核心/交付指纹与离线检查。验证通过仅表示格式、引用、隔离及源数据一致性通过，语义评分仍需人工审阅。
'''
(b/'README.md').write_text(readme)
changes=read(b/'audit/changes.json')['records']
lines=['# v1.2 修改清单','', '全部12题保留ID、游戏、检查点和最近6次提交窗口。所有题仍待人工审阅；没有模型实验。旧分值与新分值不应未经说明直接混合比较。','']
for c in changes:
 lines.extend(['## '+c['id'],'',f"- 改动：{c['what']}",f"- 原因：{c['why']}",f"- 评分含义：{c['scoring_meaning']}",f"- 总分：{c['old_max_score']} → {c['new_max_score']}",f"- 当前问题：{c['new_question']}",''])
(b/'CHANGES.md').write_text('\n'.join(lines))
coverage=read(b/'coverage.json');coverage['bank_version']='1.2.0-review';coverage['scoring_points']=33
coverage['purposes']={q['id']:q['purpose'] for q in read(b/'audit/points.json')['records']}
coverage['limits'].extend(['三道行动题核心结论均为否定，有标签分布偏向；不新增虚构正例。','G03-Q03为近期未知控制；G04-Q02为0间隔状态控制；二者不证明长期记忆优势。'])
atomic_json(b/'coverage.json',coverage)
# Reproducible lexical candidate inventory, with semantic judgments separately curated.
queries={'G01-Q01':['一周','三天','待定','面谈','旧温室','夜间巡逻'],'G01-Q02':['钥匙'],'G01-Q03':['不否认','不确认','该问的人','问导师'],'G02-Q01':['填死','填土','死墙','缝后','那面墙','撬不开'],'G02-Q02':['旁观','不动手','芬格尔'],'G02-Q03':['七枚','三枚','烟蒂'],'G03-Q01':['通行卡'],'G03-Q02':['报告','抽走'],'G03-Q03':['手背','数字','编号'],'G04-Q01':['外勤','殉职','亲手','封进','理由'],'G04-Q02':['簧片','划伤','血迹'],'G04-Q03':['锁没有开','锁舌','权限开','门不认卡','试锁','裂纹','锁芯','簧片']}
scans=[]
for q in read(b/'public/questions.json')['records']:
 terms=queries[q['id'][-7:]];hits=[];files={}
 for a in range(q['checkpoint']['action_index']+1):
  name=source_name(q['game_id'],a);cp=checkpoint(b/'frozen/source',q['game_id'],a)
  files[name]=file_sha(b/'frozen/source'/name)
  corpus=[(name,'/output'+p,s) for p,s in leaves(cp['output'])]
  if a:
   name=source_name(q['game_id'],a,'intents');files[name]=file_sha(b/'frozen/source'/name)
   corpus.append((name,'/request/player_action',read(b/'frozen/source'/name)['request']['player_action']))
  for name,ptr,s in corpus:
   if any(t in s for t in terms):hits.append(dict(action_index=a,campaign_turn=cp['progress']['turns_total'],timeline_node=cp['head'],frozen_path='frozen/source/'+name,json_pointer=ptr,excerpt=s,lexical_candidate_only=True))
 scans.append(dict(id=q['id'],range=[0,q['checkpoint']['action_index']],terms=terms,files=files,hits=hits,semantic_review='See audit/points.json semantic_decisions; keyword hits alone never determine support or latest answer disclosure.'))
atomic_json(b/'audit/disclosure-scan.json',{'status':'editor_reviewed_pending_human','records':scans})
# Freeze only this revision's newly added tools; previous tooling remains identified as inherited.
tool=b/'audit/tooling/revision';tool.mkdir(parents=True,exist_ok=True)
for path in ['jity_eval/question_bank_revision.py','tests/test_question_bank_revision.py']:
 shutil.copyfile(root/path,tool/Path(path).name)
shutil.copyfile('/tmp/build_jity_v12_spec.py',tool/'author_revision.py')
shutil.copyfile('/tmp/jity_v12_docs.py',tool/'package_review.py')
# No mutation of previously existing files is permitted.
base=read('/tmp/jity-bank-v12-baseline.json');checks=[]
for folder,files in base.items():
 changed=[]
 for name,expected in files.items():
  p=Path(folder)/name;actual=file_sha(p) if p.is_file() else None
  if actual!=expected:changed.append(name)
 checks.append({'root':folder,'baseline_files':len(files),'changed_preexisting_files':changed})
assert not any(c['changed_preexisting_files'] for c in checks),checks
atomic_json(b/'audit/preservation.json',{'status':'passed','checks':checks,'scope':'Every pre-existing tracked/untracked nonignored repo file and every file under the raw run directory at task start. New files are not original modifications.','paid_api_calls':0,'model_answers_generated':0,'game_actions_executed':0,'git_commit_push_merge':False})
# Refresh the core manifest after adding offline audit/documentation artifacts.
m=read(b/'manifest.json');m['files']=inventory(b,excluded=['manifest.json','manifest.sha256','delivery.sha256.json','delivery.sha256'])
m['files']={k:v for k,v in m['files'].items() if not k.startswith('validation/')}
atomic_json(b/'manifest.json',m);(b/'manifest.sha256').write_text(file_sha(b/'manifest.json')+'  manifest.json\n')
print('docs, disclosure scan, provenance checks, and core manifest ready',checks)
