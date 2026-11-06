import json, pathlib, hashlib, re, sys
from collections import Counter
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/world-components/organize_wording'))
import train_ab as T
pairs_rows=[json.loads(l) for l in (ROOT/'artifacts/world-components/organize-wording/pairs-v2.jsonl').read_text(encoding='utf-8').splitlines()]
pairs={r['sourceId']:r for r in pairs_rows}
clean=[json.loads(l) for l in (ROOT/'artifacts/world-components/organize-wording/clean-group-v1.jsonl').read_text(encoding='utf-8').splitlines()]
clean_by={r['sourceId']:r for r in clean}
base=ROOT/'experiments/world-components/n4_narrative_dev'
corpus={}
for fn in ('corpus.jsonl','corpus_v1.jsonl','corpus_v2.jsonl'):
 for l in (base/fn).read_text(encoding='utf-8').splitlines():
  if l.strip():
   r=json.loads(l); corpus[r['id']]=r
gp=json.loads((ROOT/'artifacts/world-components/n4-group-plan-r1.json').read_text(encoding='utf-8'))
n4split={s['sourceId']:s['split'] for s in gp['sources']}

def plan_for(facts):
 out=[]; cur=[]
 for f in facts:
  if f.get('kind')=='time': continue
  if cur and f.get('name')==cur[-1].get('name'): cur.append(f)
  else:
   if cur: out.append(cur)
   cur=[f]
 if cur: out.append(cur)
 return out

def norm_n4(sid):
 r=corpus[sid]; fs=[]
 for f in r['facts']:
  if f.get('kind')=='time': continue
  x=dict(f)
  if x['kind']=='outcome': x['text']=x.get('resultText','')
  if (x.get('entityId') or '').startswith('char_'): x['entityGroup']='characters'
  elif x.get('entityId'): x['entityGroup']='objects'
  fs.append(x)
 sb=r.get('sceneBrief',{})
 return {'sourceId':sid,'sceneGroup':sb.get('locationId',r.get('title','')),
         'context':{'place':sb.get('location',''),'visible':'、'.join(sb.get('props',[])),
                    'scene':f"{sb.get('time','')}；{sb.get('weather','')}",'viewpoint':'第三人称'},
         'facts':fs}

def single_target(f):
 k=f['kind']; n=f.get('name') or ''
 if k=='appearance_changed': return f"{n}的{f.get('text','')}。"
 if k=='outcome': return f"{n}{f.get('text','')}。"
 if k=='moved': return f"{n}从{f.get('from','')}走到{f.get('to','')}。"
 if k=='sanity_changed': return f"{n}心里松快了些。" if f.get('to',0)>f.get('from',0) else f"{n}心里发紧。"
 if k=='personality_changed': return f"{n}{f.get('text','')}。"
 if k=='no_change': return "什么也没有再发生。"
 if k=='position_relative': return f"{n}的{f.get('text','')}。"
 raise ValueError(k)

def group_target(g):
 parts=[]; prev=None
 for f in g:
  s=single_target(f)[:-1]
  n=f.get('name') or ''
  if prev is not None and n==prev:
   if s.startswith(n+'的'): s=s[len(n)+1:]
   elif s.startswith(n): s=s[len(n):]
  parts.append(s); prev=n
 return "，".join(parts)+"。"

def make_plan(groups):
 gs=[]; refs={}
 for i,g in enumerate(groups):
  ids=[f['factId'] for f in g]
  names=[f.get('name') for f in g]
  links=['continuation']*(len(g)-1) if len(set(names))==1 else ['parallel']*(len(g)-1)
  gs.append({'facts':ids,'links':links})
  for j,f in enumerate(g):
   refs[f['factId']]='name' if j==0 or f.get('name')!=g[j-1].get('name') else 'omit'
 return {'groups':gs,'refs':refs,'edges':[]}

def new_row(sid, split, meta=None):
 if sid.startswith('n4n-'):
  src=norm_n4(sid); facts=src['facts']; ctx=src['context']; sg=src['sceneGroup']
 elif sid in pairs:
  p=pairs[sid]; facts=[]; ctx=p['context']; sg=p.get('sceneGroup','')
  for f in p['facts']:
   if f.get('kind')=='time': continue
   x=dict(f)
   if x['kind']=='outcome' and 'text' not in x: x['text']=x.get('resultText','')
   facts.append(x)
 else: raise KeyError(sid)
 groups=plan_for(facts)
 if sid in pairs:
  pg=pairs[sid]['plan']['groups']
  if sorted([i for g in pg for i in g['facts']])==sorted([f['factId'] for f in facts]):
   groups=[[next(f for f in facts if f['factId']==i) for i in g['facts']] for g in pg]
 plan=make_plan(groups)
 if sid in pairs:
  plan['edges']=pairs[sid]['plan'].get('edges',[])
  plan['refs']=pairs[sid]['plan'].get('refs',plan['refs'])
 A={'calls':[{'callId':f'{sid}:{f["factId"]}','factIds':[f['factId']],'target':single_target(f)} for f in facts]}
 B={'calls':[{'callId':f'{sid}:g{i+1}','factIds':[f['factId'] for f in g],'target':group_target(g)} for i,g in enumerate(groups)]}
 row={'sourceId':sid,'split':split,'sceneGroup':sg,'context':ctx,'facts':facts,'plan':plan,'A':A,'B':B,
      'factCount':len(facts),'groupCount':len(B['calls']),'multiGroups':[[f['factId'] for f in g] for g in groups if len(g)>1],
      'targetOrigin':'authored-render-v2','bSmallTrain':False}
 if meta: row.update(meta)
 return row

# selection
bs=[r['sourceId'] for r in clean if r['split']=='train']
cd=[r['sourceId'] for r in clean if r['split']=='dev']
reg=[r['sourceId'] for r in clean if r['split']=='holdout']
extra=['v03','v11','v22','v19']
n4multi=sorted([sid for sid,s in n4split.items() if s=='formal-train' and any(len(g)>1 for g in plan_for(corpus[sid]['facts']))])
n4single=sorted([sid for sid,s in n4split.items() if s=='formal-train' and not any(len(g)>1 for g in plan_for(corpus[sid]['facts']))])
n4hold=sorted([sid for sid,s in n4split.items() if s=='formal-holdout'])
train_ids=bs+cd+extra+n4multi[:50]
dev_ids=n4single[:15]
fixed_ids=n4hold+['v05','v21','v24']
# rows
rows=[]
for sid in bs:
 r=json.loads(json.dumps(clean_by[sid])); r['split']='train'; r['bSmallTrain']=True; r['targetOrigin']='existing-clean-v1'; r['notes']='B-small original train; targets preserved'
 rows.append(r)
for sid in cd:
 r=json.loads(json.dumps(clean_by[sid])); r['split']='train'; r['bSmallTrain']=False; r['targetOrigin']='existing-clean-v1'; r['notes']='clean-group dev source moved to large train; targets preserved'
 rows.append(r)
for sid in reg:
 r=json.loads(json.dumps(clean_by[sid])); r['split']='regression'; r['bSmallTrain']=False; r['targetOrigin']='existing-clean-v1'; r['notes']='old clean-group holdout; regression only'
 rows.append(r)
for sid in extra: rows.append(new_row(sid,'train',{'notes':'pairs-v2 extra source'}))
for sid in n4multi[:50]: rows.append(new_row(sid,'train',{'notes':'n4 old formal-train multi-fact source; new target'}))
for sid in dev_ids: rows.append(new_row(sid,'dev',{'notes':'n4 old formal-train all-single source; dev only; no selection'}))
for sid in n4hold: rows.append(new_row(sid,'fixed',{'notes':'n4 old formal-holdout; fixed holdout; seen'}))
for sid in ['v05','v21','v24']: rows.append(new_row(sid,'fixed',{'notes':'pairs-v2 old holdout; fixed holdout; seen'}))
# sort
order={'train':0,'dev':1,'fixed':2,'regression':3}
rows.sort(key=lambda r:(order[r['split']],r['sourceId']))
# audits
def audit_row(r):
 errs=[]; fs={f['factId']:f for f in r['facts']}
 if len(fs)!=r['factCount']: errs.append('factCount')
 if sorted([i for c in r['A']['calls'] for i in c['factIds']])!=sorted(fs): errs.append('A coverage')
 if sorted([i for c in r['B']['calls'] for i in c['factIds']])!=sorted(fs): errs.append('B coverage')
 for c in r['A']['calls']:
  f=fs[c['factIds'][0]]; t=c['target']
  if re.search(r'[他她0-9]',t): errs.append('A pronoun/digit '+c['callId'])
  ok,_,_=T.fact_span(f,T.sent_split(t))
  if not ok: errs.append('A fact '+c['callId'])
 for c in r['B']['calls']:
  t=c['target']
  if '随后' in t: errs.append('B 随后 '+c['callId'])
  if re.search(r'[他她0-9]',t): errs.append('B pronoun/digit '+c['callId'])
  for i in c['factIds']:
   ok,_,_=T.fact_span(fs[i],T.sent_split(t))
   if not ok: errs.append('B fact '+c['callId']+':'+i)
 return errs
allerrs=[]
for r in rows:
 e=audit_row(r)
 if e: allerrs.append((r['sourceId'],e))
print('rows',len(rows),'errors',len(allerrs))
for x in allerrs[:30]: print(x)
print('split',Counter(r['split'] for r in rows),'bsmall',sum(1 for r in rows if r['bSmallTrain']))
# counts
def stats(sel):
 facts=groups=multi=0; sizes=Counter()
 for r in rows:
  if r['sourceId'] in sel:
   facts+=r['factCount']; groups+=r['groupCount']; multi+=len(r['multiGroups'])
   for g in r['multiGroups']: sizes[len(g)]+=1
 return {'sources':len(sel),'facts':facts,'groups':groups,'multi_groups':multi,'sizes':dict(sizes)}
for name,ids in [('train',train_ids),('dev',dev_ids),('fixed',fixed_ids),('reg',reg),('bsmall',bs)]:
 print(name,stats(ids))
print('fixed multi sources',sum(1 for r in rows if r['sourceId'] in fixed_ids and r['multiGroups']))
print('overlaps')
S={n:set(ids) for n,ids in [('train',train_ids),('dev',dev_ids),('fixed',fixed_ids),('reg',reg),('bsmall',bs)]}
for a in S:
 for b in S:
  if a<b: print(a,b,len(S[a]&S[b]))
path=ROOT/'artifacts/world-components/organize-wording/sentence-scale-v1.jsonl'
path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n',encoding='utf-8',newline='\n')
print('wrote',path,len(path.read_bytes()))
