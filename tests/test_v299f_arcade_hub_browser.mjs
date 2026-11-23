// v2.9.9f — five-game Arcade Hub UI, progress, search/filter, resume and Classic.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const source=readFileSync(path.join(root,"arcade-hub-v299f.js"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
const win={};
vm.runInNewContext(source,{window:win,console});
const hub=win.SnowfallArcadeHubV299f;
const name=[
 ["gallery","Snowball Target Gallery","Reflexes",true,"paused",true,28,1,17],
 ["safe","Frozen Safecracker","Precision",true,"ready",false,57,2,0],
 ["snowman","Snowman Builder","Creativity",true,"active",true,0,0,5],
 ["catch","Snowflake Catch","Reflexes",true,"ready",false,0,0,0],
 ["trivia","Christmas Trivia","Knowledge",false,"unavailable",false,0,0,0],
];
function snapshot(){
 return {
  version:"2.9.9f",player_id:"101",day:1,practice:true,competitive:false,
  available_games:4,resumable_games:2,completed_practice_runs:3,
  suggested_mode:"gallery",
  modes:name.map(([key,title,skill,enabled,status,can_resume,best,runs,progress])=>({
   key,name:title,skill,description:"Play "+title.toLowerCase(),
   enabled,status,can_resume,personal_best:best,finished_runs:runs,
   progress_percent:progress,progress_label:progress+"% saved",
   duration_label:"45 sec",
   session_id:can_resume?"sensitive-session-id":null,
  })),
 };
}
function makeRoot(){
 const slots={};
 const listeners={};
 const make=()=>({innerHTML:"",textContent:"",dataset:{},disabled:false,
  hasAttribute:()=>false,setAttribute(){}});
 const root={
  innerHTML:"",classList:{add(){},remove(){}},
  contains:()=>true,
  addEventListener(k,fn){listeners[k]=fn},
  removeEventListener(k){delete listeners[k]},
  querySelector(sel){
   const m=sel.match(/data-hub-slot='([^']+)'/);
   if(!m)throw Error("Unexpected hub selector: "+sel);
   return slots[m[1]]??(slots[m[1]]=make());
  },
  querySelectorAll:()=>[],
 };
 const click=(action,mode)=>listeners.click({target:{
  closest:()=>({dataset:{hubAction:action,mode},disabled:false})
 }});
 const input=(value)=>listeners.input({target:{
  value,matches:sel=>sel==="[data-hub-search]"
 }});
 const filter=value=>listeners.change({target:{
  value,matches:sel=>sel==="[data-hub-filter]"
 }});
 return {root,slots,listeners,click,input,filter};
}
async function drain(){
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
}
test("Arcade Hub keeps all five original game modules and Classic arcade separate",()=>{
 assert.equal(typeof hub.mount,"function");
 assert.equal(typeof hub.renderCards,"function");
 assert.equal(Object.keys(hub.MODES).length,5);
 assert.match(html,/id="arcadeHub"/);
 assert.match(html,/id="arcadeClassic"/);
 assert.match(html,/id="arcadeRun"/);
 assert.match(html,/id="arcadeLobby"/);
 assert.match(html,/id="arcadeStamps"/);
 assert.match(html,/id="arcadeBoard"/);
 assert.match(html,/arcade-hub-v299f\.js\?v=299f/);
 assert.match(css,/@media\(max-width:430px\)/);
 assert.match(css,/\.arcade-hub-card/);
 assert.match(app,/hub_v299f_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/hub/);
 assert.match(app,/hub\.player_id!==id/);
 for(const key of ["gallery","safecracker","snowman","catch","trivia"]){
  assert.match(app,new RegExp('/v1/game/arcade/'+key+'/start'));
 }
 assert.match(app,/\/v1\/game\/arcade\/move/); // Discord Classic stays.
});
test("Five cards show grounded records, clearly separate pending QA modes",()=>{
 const s=snapshot(),cards=hub.renderCards(s);
 assert.equal((cards.match(/class='arcade-hub-card'/g)||[]).length,5);
 assert.match(cards,/28<\/strong> \/ 100 best/);
 assert.match(cards,/Continue game/);
 assert.match(cards,/Not enabled/);
 assert.match(cards,/data-hub-card='trivia'/);
 assert.match(cards,/data-hub-card='safe'/);
 assert.match(cards,/role='progressbar'/);
 assert.match(cards,/aria-valuenow='17'/);
 assert.doesNotMatch(cards,/sensitive-session-id/);
 assert.doesNotMatch(cards,/data-arcade='start'/);
});
test("Filter includes correct resumable, unplayed and completed games",()=>{
 const s=snapshot();
 assert.deepEqual(Array.from(hub.visibleModes(s,"resume").map(m=>m.key)),[
  "gallery","snowman"]);
 assert.deepEqual(Array.from(hub.visibleModes(s,"new").map(m=>m.key)),[
  "snowman","catch"]);
 assert.deepEqual(Array.from(hub.visibleModes(s,"played").map(m=>m.key)),[
  "gallery","safe"]);
 assert.deepEqual(Array.from(hub.visibleModes(s,"all","craft").map(m=>m.key)),[
  "snowman"]);
 assert.deepEqual(Array.from(hub.visibleModes(s,"all","CRACK").map(m=>m.key)),[
  "safe"]);
});
test("Escapes unexpected game text; only known keys can produce artwork",()=>{
 const s=snapshot();
 s.modes[0].name="<img src=x onerror=alert(1)>";
 s.modes[0].description="<script>alert(1)</script>";
 const rendered=hub.renderCards(s);
 assert.doesNotMatch(rendered,/<script>|onerror=alert/);
 assert.match(rendered,/&lt;script&gt;/);
 assert.match(rendered,/&lt;img/);
 s.modes.push({key:"custom",name:"Unknown"});
 assert.equal(hub.visibleModes(s).length,5);
});
test("Launcher opens recommended saved session without browser-created session or score",async()=>{
 const view=makeRoot(),launched=[],refreshes=[],classic=[];
 const component=hub.mount({
  root:view.root,
  onLaunch:async name=>launched.push(name),
  onRefresh:async()=>refreshes.push("refresh"),
  onClassic:()=>classic.push("classic"),
 });
 assert.match(view.root.innerHTML,/Search games or skills/);
 assert.match(view.root.innerHTML,/Classic Arcade/);
 component.update(snapshot());
 assert.match(view.slots.feature.innerHTML,/Pick up where you left off/);
 assert.match(view.slots.stats.innerHTML,/2<\/strong> saved games/);
 assert.match(view.slots.cards.innerHTML,/Continue game/);
 view.click("launch","gallery");await drain();
 assert.deepEqual(launched,["gallery"]);
 view.click("launch","trivia");await drain(); // disabled mode stays disabled.
 assert.deepEqual(launched,["gallery"]);
 view.click("refresh");await drain();
 assert.deepEqual(refreshes,["refresh"]);
 view.click("classic");await drain();
 assert.deepEqual(classic,["classic"]);
 component.dispose();
 assert.equal(view.listeners.click,undefined);
 assert.equal(view.listeners.input,undefined);
});
test("Search and filters remain usable after server refresh",async()=>{
 const view=makeRoot();
 const component=hub.mount({
  root:view.root,onLaunch:async()=>{},onRefresh:async()=>{},onClassic:()=>{},
 });
 component.update(snapshot());
 view.input("snowman");
 assert.match(view.slots.count.textContent,/1 of 5/);
 assert.match(view.slots.cards.innerHTML,/Snowman Builder/);
 assert.doesNotMatch(view.slots.cards.innerHTML,/Frozen Safecracker/);
 view.input("");
 view.filter("resume");
 assert.equal(component.getFilter(),"resume");
 assert.match(view.slots.count.textContent,/2 of 5/);
 assert.doesNotMatch(view.slots.cards.innerHTML,/Snowflake Catch/);
 component.update(snapshot());
 assert.match(view.slots.count.textContent,/2 of 5/);
 view.filter("all");
 assert.match(view.slots.count.textContent,/5 of 5/);
 component.dispose();
});
test("Missing/stale hub state reports error and keeps Classic fallback",()=>{
 const view=makeRoot();
 const component=hub.mount({
  root:view.root,onLaunch:async()=>{},onRefresh:async()=>{},onClassic:()=>{},
 });
 component.setLoading(true);
 assert.match(view.slots.message.textContent,/Loading/);
 component.setError(new Error("Offline"));
 assert.match(view.slots.message.textContent,/Classic Arcade is still available/);
 assert.throws(()=>component.update({
  ...snapshot(),modes:snapshot().modes.slice(0,4),
 }),/unexpected game catalogue/);
 component.update(snapshot());
 assert.match(view.slots.stats.innerHTML,/games available/);
 component.reset();
 assert.match(view.slots.message.textContent,/Sign in/);
 component.dispose();
});
