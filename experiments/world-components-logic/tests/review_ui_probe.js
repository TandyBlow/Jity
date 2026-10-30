// In-memory logic probe with a synthetic packet. No browser, real storage,
// real project decisions, file exports, or network. This is not visual QA.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(process.argv[2],'utf8'),packet=JSON.parse(fs.readFileSync(0,'utf8'));
assert(packet.cases.every(c=>c.caseId.startsWith('qa-only-')));
const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.value='';this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(){}
  click(){if(this.onclick)this.onclick();}
}
function boot(raw=null,failWrites=false){
  const ids=Object.fromEntries(['packet','progress','filter','reviewer','export','list','detail','storageStatus'].map(id=>[id,new Element(id)]));
  ids.packet.textContent=JSON.stringify(packet);ids.filter.value='all';
  let stored=raw,writes=0;const blobs=[],alerts=[];
  const context={document:{getElementById:id=>ids[id],createElement:tag=>new Element(tag)},
    localStorage:{getItem:()=>stored,setItem:(key,value)=>{writes++;if(failWrites)throw Error('quota');stored=value;}},
    Blob,URL:{createObjectURL:blob=>{blobs.push(blob);return 'blob:unit-test';},revokeObjectURL(){}},
    alert:text=>alerts.push(text),setTimeout:fn=>fn(),window:{scrollTo(){}}};
  vm.runInNewContext(script,context);
  const flatten=node=>[node,...node.children.flatMap(flatten)];
  const find=text=>{const node=flatten(ids.detail).find(n=>n.tag==='button'&&n.textContent===text);assert(node,text);return node;};
  const note=()=>{const node=flatten(ids.detail).find(n=>n.tag==='textarea');assert(node);return node;};
  return {ids,blobs,alerts,find,note,get stored(){return stored;},get writes(){return writes;},
    name(){ids.reviewer.value='QA SYNTHETIC ONLY';ids.reviewer.oninput({target:ids.reviewer});}};
}
(async()=>{
  let checks=0;
  const a=boot();assert.match(a.ids.progress.textContent,/已记录 0 \/ 2/);checks++;
  a.ids.export.onclick();assert.equal(a.blobs.length,0);assert.match(a.alerts.at(-1),/称呼/);
  checks++;
  a.name();let n=a.note();n.value='仅合成测试：需要修改';n.oninput();
  a.find('下一题').click();a.find('上一题').click();assert.equal(a.note().value,'仅合成测试：需要修改');
  a.ids.export.onclick();assert.equal(a.blobs.length,0);assert.match(a.alerts.at(-1),/未确认/);
  checks++;
  a.find('需要修改').click();assert.match(a.ids.progress.textContent,/需改 1/);
  a.ids.export.onclick();const first=JSON.parse(await a.blobs.at(-1).text());
  assert.equal(first.formalEvaluationAllowed,false);assert.equal(first.decisions.length,1);
  checks++;
  const restored=boot(a.stored);assert.match(restored.ids.progress.textContent,/已记录 1 \/ 2/);
  n=restored.note();n.value='再次改动说明';n.oninput();assert.match(restored.ids.progress.textContent,/已记录 0 \/ 2/);
  assert.equal(restored.find('需要修改').className,'');checks++;
  const damaged='{"reviewer":"old","decisions":null}',b=boot(damaged);
  assert.match(b.ids.storageStatus.textContent,/无法读取/);b.name();assert.equal(b.stored,damaged);assert.equal(b.writes,0);
  b.find('暂不确定').click();b.ids.export.onclick();const second=JSON.parse(await b.blobs.at(-1).text());
  assert.equal(second.decisions[0].decision,'uncertain');assert.equal(b.stored,damaged);
  checks++;
  const c=boot(null,true);c.name();c.find('暂不确定').click();
  assert.match(c.ids.storageStatus.textContent,/保存失败/);c.ids.export.onclick();assert.equal(c.blobs.length,1);
  checks++;
  process.stdout.write(JSON.stringify({checks,exports:[first,second]}));
})().catch(error=>{console.error(error);process.exitCode=1;});
