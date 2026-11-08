const {chromium}=require('/Users/davidz/Documents/GitHub/Jity/frontend/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const root='/Users/davidz/Documents/GitHub/jity-eval/question_banks/full-games-20261106-v1.2';
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.route('https://**',r=>r.abort());await page.route('http://**',r=>r.abort());
 await page.goto('file://'+root+'/reports/review.html');
 const measure=()=>page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,questions:document.querySelectorAll('article').length,points:document.querySelectorAll('.point').length}));
 const desktop=await measure();await page.screenshot({path:root+'/validation/review-desktop.png'});
 const filterCounts={};
 for(const purpose of ['long_term_fact','retention_diagnostic','mixed_fact_diagnostic','recent_unknown_control','recent_state_control']){
  await page.selectOption('#filter',purpose);filterCounts[purpose]=await page.locator('article:visible').count();
 }
 await page.selectOption('#filter','mixed_fact_diagnostic');
 await page.locator('article:visible').first().scrollIntoViewIfNeeded();
 await page.locator('article:visible').evaluate(el=>el.querySelectorAll('details').forEach(d=>d.open=true));
 await page.screenshot({path:root+'/validation/review-diagnostic-desktop.png'});
 await page.setViewportSize({width:390,height:844});
 const mobile=await measure();await page.screenshot({path:root+'/validation/review-diagnostic-mobile.png'});
 await page.selectOption('#filter','all');await page.evaluate(()=>scrollTo(0,0));
 await page.screenshot({path:root+'/validation/review-mobile.png'});
 const brokenLinks=await page.evaluate(()=>Array.from(document.querySelectorAll('a[href^="#"]')).map(a=>a.hash.slice(1)).filter(id=>!document.getElementById(id)));
 const externalRequests=requests.filter(u=>/^https?:/.test(u));
 if(desktop.questions!==12||desktop.points!==33||desktop.width!==desktop.scrollWidth||mobile.width!==mobile.scrollWidth||errors.length||externalRequests.length||brokenLinks.length||JSON.stringify(Object.values(filterCounts))!=='[8,1,1,1,1]')throw Error(JSON.stringify({desktop,mobile,errors,externalRequests,brokenLinks,filterCounts}));
 fs.writeFileSync(root+'/validation/browser-qa.json',JSON.stringify({status:'passed',desktop,mobile,filterCounts,errors,externalRequests,brokenLinks},null,2));
 console.log(JSON.stringify({status:'passed',desktop,mobile,filterCounts,errors,externalRequests}));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
