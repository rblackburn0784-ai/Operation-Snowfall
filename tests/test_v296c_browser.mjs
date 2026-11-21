import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";
const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const source=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
function setup(){
 const nodes=new Map();
 const node=id=>{
  if(!nodes.has(id)){
   const classes=new Set();
   nodes.set(id,{dataset:{},style:{},classList:{toggle:(k,v)=>v?classes.add(k):classes.delete(k),contains:k=>classes.has(k),remove:k=>classes.delete(k)},
    getAttribute(k){return this[k]??null},
    parentElement:{setAttribute(){},removeAttribute(){}}});
  }
  return nodes.get(id);
 };
 const ctx=vm.createContext({document:{addEventListener(){},getElementById:node},URL});
 vm.runInContext(source,ctx);
 return {node,run:s=>vm.runInContext(s,ctx)};
}
test("same read-only snapshot renders boss and splash including victory and reset",()=>{
 const {node,run}=setup();
 for(const [hp,state,tier,scene] of [[150,"healthy",100,"phase_ice"],[112,"cracked",80,"rage_tommy"],[75,"wounded",50,"rage_snowball"],[37,"critical",30,"phase_frostfire"],[0,"defeated",0,"final_defeat"],[150,"healthy",100,"phase_ice"]]){
  const portrait=tier===0?"/art/v290/boss/snow_don_0.webp":"/art/boss/snow_don_"+tier+".png";
  const splash="/art/v290/boss/"+scene+".webp";
  run("S.raid="+JSON.stringify({day:4,season_phase:"live",state,tier,hp,max_hp:150,portrait,splash,title:"Test",hit_count:8,misses:3,contributors:2,echo_attacks:0})+";showBoss()");
  assert.equal(node("heroBossArt").src,splash);
  assert.equal(node("bossPortrait").src,portrait);
  assert.equal(node("heroBossArt").dataset.tier,String(tier));
  assert.equal(node("bossScene").dataset.bossState,state);
  assert.equal(node("heroDefeatTitle").classList.contains("hidden"),state!=="defeated");
  assert.equal(node("bossButton").textContent,state==="defeated"?"Attack frozen echo":"Attack the Snow Don");
  assert.equal(node("bossButton").disabled,false);
  assert.ok(existsSync(path.join(root,"graphics",portrait.slice(1))));
  assert.ok(existsSync(path.join(root,"graphics",splash.slice(1))));
 }
});
test("waiting and disabled boss never present a false victory; stale status is labelled",()=>{
 const {node,run}=setup();
 run("S.raid={state:'disabled',hp:0,max_hp:150,tier:null,title:'Boss disabled'};showBoss()");
 assert.equal(node("bossButton").disabled,true);
 assert.equal(node("heroDefeatTitle").classList.contains("hidden"),true);
 run("S.raid=null;S.bossStale=true;showBoss()");
 assert.match(node("bossFreshness").textContent,/refresh pending/i);
 assert.equal(node("heroDefeatTitle").classList.contains("hidden"),true);
});
