from pathlib import Path
from copy import deepcopy
import sys,json
sys.path.insert(0,'/Users/davidz/Documents/GitHub/jity-eval')
from jity_eval.question_bank import read,pointer,checkpoint,source_name,leaves
from jity_eval.storage import digest,atomic_json
B=Path('/Users/davidz/Documents/GitHub/jity-eval/question_banks/full-games-20261106-v1.1')
OUT=B.parent/'full-games-20261106-v1.2-authoring'
SRC=B/'frozen/source'; RAW='/Users/davidz/Documents/GitHub/jity-eval/runs/full-games-20261106/'
author=read(B/'private/authoring.json'); pub=read(B/'public/questions.json')['records']
refs=[]; questions=[]

def select(short):
 global q,qpub,qid,game,stop,points,decisions
 q=deepcopy(next(x for x in author['questions'] if x['id'].endswith(short)))
 qpub=next(x for x in pub if x['id']==q['id']);qid=q['id'];game=q['game_id'];stop=q['checkpoint_action'];points=[];decisions=[]

def h(a,ptr,excerpt=None,classification='explicit_answer',kind='checkpoints'):
 cp=checkpoint(SRC,game,a); rel=source_name(game,a,kind);v=pointer(read(SRC/rel),ptr)
 if excerpt is None:excerpt=v
 assert (excerpt in v) if isinstance(v,str) else excerpt==v,(qid,a,ptr,excerpt)
 rid=qid+'.r%03d'%(sum(x['question_id']==qid for x in refs)+1)
 refs.append(dict(id=rid,question_id=qid,game_id=game,action_index=a,campaign_turn=cp['progress']['turns_total'],timeline_node=cp['head'],frozen_path='frozen/source/'+rel,source_path=RAW+rel,json_pointer=ptr,excerpt=excerpt,classification=classification,evidence_role='committed_history'))
 return rid

def st(a,ptr,excerpt=None):
 r=h(a,ptr,excerpt,'persistent_state')
 if ptr=='/state/items':
  ref=hist(r);ref['excerpt']=[x.get('name') for x in ref['excerpt']];ref['projection']='names'
 return r
def topic(a,ptr,excerpt=None):return h(a,ptr,excerpt,'topic_only')
def hist(r):return next(x for x in refs if x['id']==r)
def at(r):
 if r is None:return None
 r=hist(r);return {k:r[k] for k in ('action_index','campaign_turn','timeline_node')}|{'gap_actions':stop-r['action_index'],'gap_campaign_turns':qpub['checkpoint']['campaign_turn']-r['campaign_turn'],'evidence_ids':[r['id']]}

def inp(mode,ptr,excerpt=None):
 path=f'public/inputs/{qid}/{mode}.json';v=pointer(read(B/path),ptr)
 if excerpt is None:excerpt=v
 assert (excerpt in v) if isinstance(v,str) else excerpt==v,(qid,mode,ptr,excerpt)
 a=stop; node=qpub['checkpoint']['timeline_node']; classification='persistent_memory' if '/historical_narrative_memory/' in ptr else 'persistent_state'
 if ptr.startswith('/context/recent_context/'):
  i=int(ptr.split('/')[3]);row=read(B/path)['context']['recent_context'][i];a=row['action_index'];node=row['timeline_node'];classification='recent_explicit'
 rid=qid+'.r%03d'%(sum(x['question_id']==qid for x in refs)+1)
 refs.append(dict(id=rid,question_id=qid,game_id=game,action_index=a,timeline_node=node,frozen_path=path,source_path=str(B/path),json_pointer=ptr,excerpt=excerpt,classification=classification,evidence_role='actual_frozen_input'))
 return rid

def sp(ptr,ex=None):return ('/context/structured_state'+ptr,ex)
def mp(ptr,ex=None):return ('/context/historical_narrative_memory'+ptr,ex)
def rp(a,ptr,ex=None):return ('/context/recent_context/'+str(a-(stop-5))+ptr,ex)
def support(levels=('full','not_provided','full'),S=(),M=(),R=(),notes=None,absence=False):
 result={}
 for mode,level in zip(('full','recent','state'),levels):
  selections=list(R)+(list(S) if mode in ('full','state') else [])+(list(M) if mode=='full' else [])
  # Pure topic prompts do not become positive evidence for an absent point.
  evidence=[inp(mode,*s) for s in selections] if level!='not_provided' else []
  note=(notes or {}).get(mode, '现有输入完整支持此语义要点。' if level=='full' else ('仅保留部分内容；不能以相关实体命中替代完整答案。' if level=='partial' else '逐字段审查当前输入，未提供此要点；相关话题或实体不算答案。'))
  result[mode]=dict(support=level,evidence_ids=evidence,note=note,input_context_sha256=digest(read(B/f'public/inputs/{qid}/{mode}.json')['context']),basis='bounded_input_absence' if absence else 'explicit_fields',target_value_provided=not absence and level=='full')
 return result

def point(key,criterion,score,first,last,history,sup,partial='未完整表达该语义点为0；准确同义或清楚蕴含给满分。',updates=(),note='',null=None):
 id=qid+'.p%02d'%(len(points)+1)
 p=dict(id=id,semantic_key=key,criterion=criterion,score=score,partial_credit=partial)
 audit=dict(id=id,historical_evidence_exists=bool(history),target_value_explicitly_disclosed=not bool(null),historical_support_method="bounded_prefix_review" if null else "explicit_history",historical_evidence_ids=list(dict.fromkeys(history)),chronology=dict(first_explicit=at(first),latest_explicit=at(last),updates=list(updates),note=note,null_reason=null),inputs=sup,answer_correctness='not_run')
 points.append((p,audit));return id

def finish(question=None,answer=None,accepted=None,errors=None,purpose='long_term_fact',what='',why='',meaning='',review=()):
 gold=deepcopy(q['gold']);gold.update(answer=answer or gold['answer'],acceptable_phrasings=accepted or gold['acceptable_phrasings'],required_points=[p['criterion'] for p,a in points],typical_errors=errors or gold['typical_errors'])
 gold['rubric']={'max_score':sum(p['score'] for p,a in points),'policy':'private/scoring-policy.json','points':[p for p,a in points],'partial_credit':'逐要点评分，适用统一语义规则；不奖励未犯错、不重复计分。'}
 questions.append(dict(id=qid,question=question or q['question'],gold=gold,points=[a for p,a in points],purpose=purpose,semantic_decisions=decisions,review=['逐要点披露、通道支持和同义评分仍待人工复核。',*review],change=dict(what=what,why=why,scoring_meaning=meaning)))

select('G01-Q01')
w='/output/memory_updates/world_facts_upserted/0/description';si=sp('/world_facts/7/description')
a=h(7,w);b=h(9,'/output/dialogue/1/text')
for key,crit,first,last,mem in [
 ('greenhouse_task','东侧旧温室夜间异常光源调查（观察/记录其性质或规律）。',a,b,'东侧旧温室异常光源调查（三天）'),
 ('greenhouse_deadline','该调查当时期限为三天。',a,b,'东侧旧温室异常光源调查（三天）'),
 ('patrol_task','夜间巡逻，与指定高年级生组队。',a,a,None),
 ('patrol_deadline','夜间巡逻期限为一周/七天。',a,a,'夜间巡逻（一周）'),
 ('third_pending','第三项当时待定，尚未给出具体任务和期限。',a,a,'第三项待导师面谈解锁'),
 ('third_unlock','第三项需导师面谈后解锁。',a,a,'第三项待导师面谈解锁')]:
 point(key,crit,.5,first,last,[a,b] if last==b else [a],support(S=[si],M=[mp('/recap_compressed',mem)] if mem else []),note='首次任务框架A7；第一任务及三天期限A9明确重述。第二项和第三项无更晚完整重述。持久world_facts在检查点可见，不算新披露。')
decisions += ['A8的“导师面谈”目标仅为话题，未重新列出第三任务框架。A7选项重提组队对象；已纳入A7披露。','六个评分要点对应三个任务及期限/解锁状态，避免使用一个整题间隔代表所有答案。']
finish(what='三个任务拆为六个可分别核查的小要点，各0.5分；分别记录披露和可见性。',why='任务与期限可独立遗漏，第一任务A9重述不应覆盖另外两项的间隔。',meaning='总分仍3；部分分更细。第三项不得编造任务或期限；不另设不编造奖励。')

select('G01-Q02')
a=h(25,'/output/items_lost/0/description');acq=st(12,'/state/items/4');ledger=st(40,'/state/_memory_controller/score_tracker/4');inv=st(40,'/state/items')
point('key_current_lost','钥匙已遗失，因此当前不持有可用钥匙。',1,a,a,[acq,a,ledger,inv],support(S=[sp('/item_ledger/4')],M=[mp('/nsb/level2/0/summary','玩家丢失钥匙')]),partial='只说目前不持有/不能用但未说明遗失，0.5；明确钥匙丢失已蕴含当前不持有，1；声称仍持有或已找回，0。',updates=[{'action':12,'meaning':'已获得（旧状态）','evidence_ids':[acq]},{'action':25,'meaning':'遗失更新','evidence_ids':[a]}],note='当前遗失要点首次A25；实体曾在A12获得，不把获得位置冒充遗失首次。')
decisions += ['A24局部物品名切分报错与当时active账本冲突，不作为遗失证据。A25找回选项/检定条件只是拟议行动，没有重新取得。']
finish(answer='钥匙已经遗失，当前不持有可用钥匙。A25提交后账本转为lost；至检查点A40没有重新获得。精确掉落位置未证实。',accepted=['钥匙丢了，现在不在身上，不能用。','已经遗失，当前没有可用钥匙。'],what='合并“遗失”和由此蕴含的“不持有”重复评分；保留遗失经过和权威状态双重证据。',why='避免同一语义事实计两次分。',meaning='总分2→1；只给当前不持有结论可得0.5，说明丢失即满分，无需字段名。')

select('G01-Q03')
a=h(8,'/output/dialogue/0/text','我不否认，也不确认');b=h(8,'/output/narration','档案室里的导师才是该问的人')
point('nono_reservation','诺诺既不确认也不否认刻痕与任务的关联。',1,a,a,[a],support(S=[sp('/world_facts/9/description')]))
point('refer_to_mentor','她让玩家向档案室导师了解。',1,b,b,[b],support(S=[sp('/world_facts/9/description')]))
decisions += ['“既不确认也不否认，让我问导师”已蕴含未证实关联，不再另要免责声明。A9问导师取档人外貌是另一问题，不是本点重述。']
finish(accepted=['她既不确认也不否认，让我问导师。','她没有给出肯定或否定的答复，表示应由档案室导师来说。'],errors=['说诺诺已确认关联：态度点0。','问询对象说成门房：导师点0。'],what='删除与保留态度重复的免责声明评分点。',why='自然表达已清楚蕴含关联未证实。',meaning='总分3→2；不额外要求“不是已证实事实”，显式反向断言仍按矛盾规则处理。')

select('G02-Q01')
old=h(30,'/output/dialogue/1/text');a=h(31,'/output/quests_updated/0/description');b=h(31,'/output/memory_updates/world_facts_upserted/0/description');t=topic(33,'/output/narration','你不再去碰那面墙')
S=[sp('/world_facts/58/description')];M=[mp('/nsb/level1/0/summary','诺诺在岔口摸墙发现裂缝，但撬开灰泥后确认缝被填死')]
point('wall_feasibility','依据已有检查结果，不能直接把该墙缝作为可通行退路。',1,a,a,[a,b],support(S=S,M=M),note='结论有A31已提交任务更新及实际观察支撑；A33仅话题。')
point('wall_revised_evidence','后续实际摸查发现缝后填实、撬不开，更新了先前“有风”的判断。',1,b,b,[old,b],support(S=S,M=M),partial='说清后续实查填实/撬不开即可1分；不强制重复早先有风原话。只复述有风而未给实查结果，0。',updates=[{'action':30,'meaning':'早先有风的初步判断','evidence_ids':[old]},{'action':31,'meaning':'实查填实更新','evidence_ids':[b]}])
decisions += ['保留整题最近话题A33，答案明确披露A31。仅有风不证明通行；“永久不可能打开”超出证据，不因未说这句话而加分。']
finish(question='如果返回先前躲避监视者的岔口，诺诺检查过的那处墙缝能否直接作为退路通行？请依据已有检查结果判断并解释。',what='问法改为中性可行性判断并锁定原岔口墙缝；取消“不声称永久不通”的奖励分。',why='避免预设否定结论，区分实际证据与推断边界。',meaning='总分3→2；核心判断与实查依据各1分。永久性断言作为边界错误处理。')

select('G02-Q02')
a=h(25,'/output/dialogue/0/text');b=h(25,'/output/memory_updates/world_facts_upserted/1/description');c=h(26,'/output/narration','他搬的箱子从旧档案室后门出去')
point('observer_name_unknown','本次提供的信息不足以确定该旁观者的名字。',1,None,None,[a,b],support(levels=('full','full','full'),absence=True,notes={m:'只对本组提供记录作有界不足判断；没有给出名字或唯一身份映射。完整历史前缀另行私有审查，不要求模型声称看过整个历史。' for m in ('full','recent','state')}),null='目标姓名未披露；“不足以确定”是有界历史审查的结论，不是有姓名答案的首次/最近披露。')
point('observer_role','诺诺描述的是穿执行部外套、在拐角旁观而未动手的人。',1,b,b,[b],support(S=[sp('/world_facts/43/description')],M=[mp('/recap_compressed','拐角还站着个只看不动的执行部人员')]),partial='明确诺诺说执行部人员在旁观/没有动手得1；仅泛称执行部人员而无旁观行为得0.5；只说不知道得0。')
point('mover_fengel','芬格尔是诺诺所说搬箱的人，与被问姓名的旁观角色不同。',1,a,c,[a,c],support(S=[sp('/world_facts/42/description')],M=[mp('/recap_compressed','上个月搬封存箱的是高年级的芬格尔')]),partial='明确芬格尔是搬箱人得1；只说“不是芬格尔”或没有提及角色内容得0。',note='A26叙述明确重述他搬的箱子；A26一般替人搬东西的介绍只算部分描述，不用A34封条关联重置搬箱角色的完整披露。')
decisions += ['完整私有审查范围initial0–A42，含选项、检定、实际行动和提交状态。没有发现姓名或唯一可推导身份。','只答“不知道/本次提供的信息不足”得1/3；不凭没有错认芬格尔给角色分。后来的守卫、监视者不可无依据合并。']
finish(question='诺诺提到上个月在搬箱现场旁观的那名执行部人员叫什么名字？请说明依据。',accepted=['本次提供的信息不足以确定名字。（仅结论1分）','不知道名字。诺诺只说一个执行部的人旁观没动手；芬格尔是搬箱的人。（3分）'],what='去掉单独拒答提示；明确不知道仅得结论分，把不误认改为需正面说明芬格尔角色。',why='不给未犯错奖励，也不要求近期组替未见的全历史作断言。',meaning='总分仍3；角色两分必须有正确内容，未知结论无需全局历史宣称。')

select('G02-Q03')
a=h(24,'/output/dialogue/0/text','七枚，三枚新的');b=h(25,'/request/player_action',kind='intents');c=h(25,'/output/narration')
# Minimize long actual action/narration references to exact seven-count substrings.
for rid in [b,c]:
 r=hist(rid); v=r['excerpt']; start=v.index('七枚');r['excerpt']=v[max(0,start-8):min(len(v),start+18)]
point('cigarette_total','烟蒂总数七枚。',1,a,c,[a,b,c],support(levels=('not_provided',)*3),note='A25实际玩家行动和叙述再次出现七枚，不能只扫描主持正文。')
point('cigarette_new','其中三枚较新。',1,a,a,[a],support(levels=('not_provided',)*3),note='A25只重述七枚总数，未重述三枚较新。')
decisions += ['历史有完整数量证据；当前full/recent/state均未保留两个数量。world_facts烟草味/近期有人待过只提供相关背景。不得补写记忆或删去数量要求。']
finish(purpose='retention_diagnostic',what='逐数量记录最近披露和三组均缺失事实；标明记忆保留诊断用途。',why='输入遗失不能全部归因为作答模型遗忘。',meaning='总分2、历史标准答案不变；不计算或推测模型表现。',review=['复核数量是否存在同义数字表达或可唯一推导线索；目前完整输入逐字段审查未发现。'])

select('G03-Q01')
init=st(0,'/state/items/0');narr=h(1,'/output/narration');r=hist(narr);v=r['excerpt'];ix=v.index('通行卡');r['excerpt']=v[max(0,ix-10):ix+26]
a=h(24,'/output/items_lost/0');b=h(27,'/output/memory_updates/player_status_patch/condition');c=h(25,'/output/narration','他把通行卡收进外套内袋');ledger=st(35,'/state/_memory_controller/score_tracker/0');inv=st(35,'/state/items')
point('card_no_possession','移交后尚未取回，当前不持有卡，不能直接出示。',1,a,b,[init,narr,a,b,ledger,inv],support(S=[sp('/item_ledger/0')]),updates=[{'action':0,'meaning':'首次结构化owned','evidence_ids':[init]},{'action':1,'meaning':'首次叙事出现','evidence_ids':[narr]},{'action':24,'meaning':'移交后从玩家持有物中移除','evidence_ids':[a]}],note='本点的“不持有”首次A24；物品首次持有证据另列initial0，不能混作A1叙事。')
point('card_transfer','卡交给了执行部核查员。',1,a,c,[a,c],support(S=[sp('/world_facts/35/description')]),note='A25核查员收进内袋明确重述归属变化；A27被收走状态没有再次指明收卡人。')
decisions += ['首次结构化持有A0，首次叙事A1，移交A24；全题距首次更正为35次提交/34次推进，最近话题A27不变。','“卡交给核查员，后来没取回，所以现在不能出示”满足全部要点。无需另说不是消耗或销毁；若主动误称消耗，相关状态/依据点按错误处理。']
finish(accepted=['卡交给核查员，后来没取回，所以现在不能出示。'],what='更正首次状态证据；删除“非消耗/销毁”的重复独立分。',why='初始状态已owned；自然解释移交后不持有已足够。',meaning='总分3→2；当前不持有和核查员移交依据各1分，首次间隔纠正。')

select('G03-Q02')
a=h(22,'/output/quests_updated/0/description');b=h(22,'/output/memory_updates/world_facts_upserted/0/description');c=h(25,'/output/narration','桌上那份报告也不在你这一侧');ledger=st(40,'/state/_memory_controller/score_tracker/5');inv=st(40,'/state/items')
point('report_unavailable','当前不具备亲手直接递交报告原件的持有条件。',1,a,c,[a,c,ledger,inv],support(S=[sp('/item_ledger/5')],M=[mp('/nsb/level2/0/summary','报告被没收')]),note='A25明确仍不在玩家一侧；A32桌对面展示报告仅是位置线索，不是重新获得或明确重复同一原件移交。')
point('report_confiscation','报告被核查员收走，尚未实际取回。',1,b,b,[b,ledger,inv],support(S=[sp('/world_facts/32/description'),sp('/item_ledger/5')],M=[mp('/nsb/level2/0/summary','报告被没收')]),note='没收事实首次/最近明确披露A22；未取回由至检查点的提交账本支持，持续状态不算新披露。')
decisions += ['保留整题话题A32，但明确移交事件仍为A22，当前不可用由检查点账本判定。A28抽走的是另一张纸，不替代报告证据。','不强制列举未被问及的纸条或记忆替代物。若主动把纸条当成报告，才按依据错误处理。']
finish(question='现在若想亲手把血统检测异常报告的原件递给诺诺核对，你是否具备直接执行所需的物品条件？请解释。',accepted=['报告被收走且未取回，所以不能递交。','不行，报告原件被执行部核查员抽走了，尚未拿回来。'],what='移除逐题重复执行提示，使用统一说明；取消替代纸条的强制评分点。',why='问题只问报告原件的直接递交条件。',meaning='总分3→2；正确结论及收走未取回的解释足够满分。')

select('G03-Q03')
a=h(30,'/output/memory_updates/world_facts_upserted/0/description');b=h(31,'/output/memory_updates/player_status_patch/notes');c=h(33,'/output/dialogue/1/text');d=topic(36,'/output/options/0');e=topic(37,'/output/dialogue/0/text')
point('hand_digit_unknown','本次提供的信息不足以确定具体数值。',1,None,None,[a,c],support(levels=('full','full','full'),absence=True),null='没有披露具体数值；不足结论来自有界审查，不能指定一个虚构的数值披露时刻。')
point('hand_digit_justification','记录只提到一个数字、角色记住/声称知道或编号关联，却未给出足以确定数值的内容。',1,None,None,[a,b,c,d,e],support(levels=('full','full','full'),S=[sp('/world_facts/49/description')],R=[rp(33,'/output/dialogue/1/text')],notes={m:'该组有“你手背上那个数字，我们已经知道了”等无数值描述；角色声称知道不等于向回答者披露数值。未发现唯一映射，审查边界是本组输入。' for m in ('full','recent','state')}),partial='准确指出记录中的无值描述或角色知道不等于文本披露，可得1；仅重复不知道而无依据，0。不要求机械罗列所有线索。',null='这是带负面查核的综合解释，没有一个完整明确披露结论的事件；正面前提A30/A31/A33，最近相关问话A37单列。',note='前提位置：A30划数字，A31玩家默记，A33审查者声称知道；不把这些当成数值已披露。')
decisions += ['私有完整历史前缀initial0–A38仍保留。审查包括编号、末两位相同、纸条和选项，未发现具体数值或唯一映射。','A36“编号后半段”是未选择选项，不是已确认世界事实；即便作为线索也没有数值。A37追问只重提话题。','这是近期未知控制，不代表长间隔遗忘。仅答不知道得1/2。']
finish(question='诺诺在你手背划下的具体数字是多少？请说明依据。',accepted=['本次提供的信息不足。（仅结论1分）','无法确定。记录只说手背上有个数字，角色声称知道，但没有给出具体值。（2分）'],purpose='recent_unknown_control',what='去掉专门拒答暗示；合并重复的未知边界解释，保留完整前缀私有排查。',why='允许依据实际提供的信息承认不足，避免把角色知道当成读者已获数值。',meaning='总分3→2；未知结论1、正确无值依据1，不要求罗列所有未问线索。')

select('G04-Q01')
a=h(38,'/output/memory_updates/npcs_upserted/0/description');b=h(42,'/output/memory_updates/npcs_upserted/0/description');c=h(45,'/output/memory_updates/npcs_upserted/1/description');d=h(38,'/output/dialogue/0/text');e=h(38,'/output/memory_updates/world_facts_upserted/0/notes')
point('hooded_identity','他自述为三年前被撤销科室的末批外勤。',1,a,b,[a,b],support(levels=('full','full','full'),S=[sp('/world_facts/64/description')],R=[rp(42,'/output/memory_updates/npcs_upserted/0/description')]),partial='仅正确说曾是外勤但缺科室/时间/末批限定，0.5；准确还原身份1。',note='A39–42提交更新反复完整重述，最近完整A42；A43–45仍提外勤身份但缺限定，属于部分重述。')
point('hooded_recorded_death','他称档案把自己记为殉职；这不是实际死亡的独立证明。',1,a,c,[a,c],support(levels=('full','full','full'),S=[sp('/world_facts/64/description')],R=[rp(45,'/output/memory_updates/npcs_upserted/1/description')]),partial='“他称档案上已殉职”即满分，已表达来源边界，不另需免责声明；明确断言实际死亡复活则0。')
point('hooded_partial_reason','他称编号里的一个数字是自己亲手封进那扇门后的，这是帮助理由已透露的一部分。',1,d,d,[d,e],support(levels=('full','not_provided','partial'),S=[sp('/world_facts/64/notes'),sp('/world_facts/65/notes')],M=[mp('/nsb/level1/1/summary','因编号中一个数字由他亲手封存而协助')],notes={'full':'摘要保留亲手封存数字，world_facts保留理由只说半句及门后封存编号；合并同一场景支持。需人工复核跨字段指代。','state':'保留理由与编号数字有关、只说半句及门后封存编号，遗漏“亲手封存”的主语动作细节。'}),partial='只准确说明帮助与编号中的数字有关，0.5；亲手封存数字及同一门后的含义表达完整，1；不要求额外免责声明，但不得声称完整动机已揭晓。',note='此细节首次/最近明确A38；近期身份重述不等于理由细节重述。')
decisions += ['A45保留身份/档案信息，所以不能把整题称为长间隔未重提。P1最近完整A42、P2 A45、P3 A38。','state人物条目和world_facts可合法提供身份与档案信息；完整记忆通过实际摘要额外保留亲手封存。帮助动机仍只透露部分。']
finish(answer='他自称是三年前被撤销科室的末批外勤，档案上记为殉职；他说编号中的一个数字是自己亲手封进那扇门后的。这只是帮助理由已透露的一部分，不是完整动机，也不是实际死亡或复活的独立证明。',accepted=['他称自己是三年前撤销科室的最后一批外勤，档案记作殉职；提到编号中有他亲手封在门后的数字，作为部分帮助理由。'],what='分别审计身份、档案记录、亲手封存数字；补回帮助理由只透露部分的边界。',why='整题0间隔掩盖各要点的时间和通道差异。',meaning='总分仍3；自然来源表述足够，保留原亲手封存要求，不因state缺失而删减。',review=['复核完整记忆跨摘要与world_facts合并门后指代是否足以支持理由要点。'])

select('G04-Q02')
a=h(41,'/output/action_check');b=h(41,'/output/items_gained/0');state=st(41,'/state/items/5');ledger=st(41,'/state/_memory_controller/score_tracker/5');c=h(41,'/output/memory_updates/player_status_patch/condition');d=h(41,'/output/memory_updates/quests_upserted/0/notes')
point('spring_check_failure','取簧片检定失败。',1,a,a,[a],support(levels=('full','full','full'),R=[rp(41,'/output/action_check')]),partial='自然说明失败即1；无需主动报骰点。若主动报错骰点/目标，或将结果说成成功，检定说明点为0。')
point('spring_owned','虽然检定失败，仍取得并持有半截铜色簧片。',1,b,b,[b,state,ledger],support(levels=('full','full','full'),R=[rp(41,'/output/items_gained/0')],S=[sp('/items/5'),sp('/item_ledger/5')]),note='持有以提交items与账本为准；A40仅弹出/提议拿走，还未取得。')
point('finger_injury','掰取时手指被划伤、出血。',.5,c,c,[c],support(levels=('full','full','full'),R=[rp(41,'/output/memory_updates/player_status_patch/condition')],S=[sp('/player_status/condition')]))
point('blood_traces','留下血迹/铜屑等可暴露行踪的痕迹。',.5,d,d,[d],support(levels=('full','full','full'),R=[rp(41,'/output/memory_updates/quests_upserted/0/notes')],S=[sp('/quests/1/notes')]))
decisions += ['所有实际结果首次/最近A41，间隔0。A40选项与失败条件只是预告，不是受伤或获得已经发生。','持有用自然语言即可，不要求owned、active或账本名。该题是近期状态控制，不作为长期记忆优势证据。']
finish(answer='检定失败，但仍取得并持有半截铜色簧片。掰取时手指被铜屑划伤出血，并留下血迹与更多追踪痕迹。若报告数值，骰点为2、目标为12。',accepted=['检定没过，但簧片拿到了、还在手里；手指划伤流血，留下了痕迹。'],purpose='recent_state_control',what='持有评分改为自然语义；把代价细分为受伤与痕迹各0.5分。',why='无需内部字段名，也避免将两个可独立遗漏的代价捆绑。',meaning='总分仍3；结果1、持有1、受伤0.5、痕迹0.5；0间隔控制定位不变。')

select('G04-Q03')
a=h(40,'/output/narration','锁没有开，锁舌纹丝不动');b=h(40,'/output/memory_updates/items_upserted/0/notes');c=h(40,'/output/dialogue/0/text');d=h(40,'/output/dialogue/0/speaker')
point('card_lock_result','已有试卡尝试未打开这道锁，不能据此认定通行卡已验证可开门。',1,a,a,[a],support(S=[sp('/world_facts/67/source')],M=[mp('/nsb/level1/1/summary','玩家用临时通行卡试开旧锁失败')]),partial='说明试卡没有开门即清楚支持未验证可开，得1；只给无依据否定而无已知尝试结果得0.5；声称已开门/已验证能开为0。')
point('card_lock_observation','试卡后出现裂纹扩大、响声或锁芯弹出铜簧片等实际反应，至少准确一项。',1,b,b,[b],support(S=[sp('/items/0/notes')],M=[mp('/nsb/level1/1/summary','卡面裂纹扩大，锁芯弹出刻有半截编号的铜簧片')]),note='A41拿到簧片、之后持有簧片仅相关实体/后续处理，不重述A40试卡反应因果。')
point('hooded_lock_explanation','当时的解释是这锁不靠权限打开，或卡认得门、门不认卡。',.5,c,c,[c],support(levels=('not_provided',)*3),note='历史解释保留，不因实际full已遗漏而删去评分要求。')
point('hooded_lock_source','将上一解释正确归属于兜帽人的说法。',.5,d,d,[c,d],support(levels=('not_provided',)*3),partial='准确归属已表达的相关解释才得0.5；仅罗列“兜帽人”名字却未说明他解释什么，不得分。')
decisions += ['试锁观察和兜帽人的解释/来源拆开。完整记忆与state支持尝试失败及反应，但都遗漏解释和来源；recent42–47仅有相关簧片等实体。','整题话题最近A41（间隔6）保留；本题各答案要点最近明确披露均A40（间隔7）。A39选项及检定条件为假设，不是尝试结果。','历史证据有、实际输入缺、模型是否答对未运行，三者分别记录。不得因输入缺失删减解释要求或补写记忆。']
finish(purpose='mixed_fact_diagnostic',what='拆分试锁观察、解释内容和说话者；逐点修正明确答案披露为A40。',why='A41提簧片不等于重新披露试锁结果或解释；避免独立事实捆绑和重复否定奖励。',meaning='总分仍3；尝试结果1、实际反应1、解释0.5、来源0.5；历史解释要求完整保留。',review=['完整记忆缺少解释及来源，未来不能把这部分缺分单独归因作答模型。'])

spec=dict(schema_version='jity.capture-question-bank.revision.v1',bank_version='1.2.0-review',recent_window=6,questions=questions,references=refs)
OUT.mkdir(exist_ok=True)
atomic_json(OUT/'spec.json',spec)
print('wrote',OUT/'spec.json',len(questions),'questions',sum(len(q['points']) for q in questions),'points',len(refs),'references')
