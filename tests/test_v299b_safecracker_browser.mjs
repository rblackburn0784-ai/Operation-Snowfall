// v2.9.9b — tactile dial, shared scene, auditable action payload and keyboard.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const engine=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const code=readFileSync(path.join(root,"arcade-safe-v299b.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
const win={
 requestAnimationFrame:()=>1,cancelAnimationFrame(){},
 matchMedia:()=>({matches:false}),
 document:{hidden:false,addEventListener(){},removeEventListener(){}}
};
const sandbox={window:win,console,performance:{now:()=>1000},
 Image:class {src="";complete=false;naturalWidth=0}};
vm.runInNewContext(engine,sandbox);
vm.runInNewContext(code,sandbox);

const fresh=()=>({
 session_id:"a".repeat(32),mode:"safe",status:"paused",practice:true,
 competitive:false,day:1,duration_ms:90000,elapsed_ms:0,
 dial:0,stage:0,direction:1,turn_required:40,travel:0,
 signal:"turn",mistakes:0,attempts:0,action_seq:0,
 score:0,feedback:"",combination:null,unlocked:false,
});
function harness(){
 const stageEvents={},controls={},nodes={};
 const node=()=>({textContent:"",disabled:false,attrs:{},dataset:{},
  setAttribute(k,v){this.attrs[k]=v}});
 const canvas={
  getContext:()=>({}),
  getBoundingClientRect:()=>({left:0,top:0,width:640,height:360}),
  setPointerCapture(){},focus(){},
  addEventListener(k,fn){stageEvents[k]=fn},
  removeEventListener(k){delete stageEvents[k]}
 };
 const rootEl={
  innerHTML:"",classList:{remove(){},add(){}},
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")
    return nodes.feedback??(nodes.feedback=node());
   const b=sel.match(/data-scene='([^']+)'/);
   if(b)return nodes[b[1]]??(nodes[b[1]]=node());
   const l=sel.match(/data-scene-label='([^']+)'/);
   if(l)return nodes[l[1]]??(nodes[l[1]]=node());
   throw Error("unexpected selector "+sel);
  },
  addEventListener(k,fn){controls[k]=fn},
  removeEventListener(k){delete controls[k]}
 };
 const button=key=>controls.click({
  target:{closest:()=>({dataset:{scene:key}})}
 });
 const touch=(type,x,y,pointerId=1)=>stageEvents[type]({
  type,pointerId,clientX:x,clientY:y,preventDefault(){}
 });
 const key=(name,shiftKey=false)=>stageEvents.keydown({
  key:name,shiftKey,preventDefault(){}
 });
 return {root:rootEl,nodes,stageEvents,controls,button,touch,key};
}
async function drain(){
 await new Promise(r=>setImmediate(r));
 await new Promise(r=>setImmediate(r));
}
function boot(ui,base=fresh(),handlers={}){
 let saved=base;
 const calls=[];
 const runtime=win.SnowfallSafecrackerV299b.mount({
  root:ui.root,session:saved,
  start:async()=>saved={...fresh(),session_id:"b".repeat(32)},
  control:async(_sid,op)=>saved={...saved,status:op==="resume"?"active":
   op==="finish"?"finished":"paused"},
  move:async body=>{
   calls.push(body);
   if(handlers.move)return saved=await handlers.move(body,saved,calls);
   const dial=win.SnowfallSafecrackerV299b.mod(saved.dial+body.ticks);
   return saved={...saved,action_seq:saved.action_seq+1,
    dial,travel:saved.travel+Math.abs(body.ticks),
    feedback:"Dial turning",signal:"turn"};
  },
  refresh:async()=>saved,fetchRecord:async()=>({
   personal_best:95,vaults_opened:1,finished_runs:1}),
  onExit:()=>{},
 });
 return {runtime,calls,getView:()=>saved};
}
test("Safecracker uses the shared scene with a unique default-off launch, no classic mutations",()=>{
 assert.equal(typeof win.SnowfallArcadeV299.mountScene,"function");
 assert.equal(typeof win.SnowfallSafecrackerV299b.mount,"function");
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-safe-v299b.js"));
 assert.match(html,/arcade-safe-v299b\.js\?v=299b/);
 assert.match(html,/id="arcadeSafe"/);
 assert.match(css,/arcade-full-safe/);
 assert.match(css,/touch-action:none/);
 assert.match(app,/safe_v299b_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/safecracker\/move/);
 assert.match(app,/\/v1\/game\/arcade\/move/); // original Discord choice game
 assert.match(app,/\/v1\/game\/arcade\/gallery\/shot/); // Gallery still there
});
test("touching the dial rotates ten notches clockwise and submits only a server action",async()=>{
 const ui=harness(),game=boot(ui);
 assert.match(ui.root.innerHTML,/SET TUMBLER/);
 assert.match(ui.root.innerHTML,/90s/);
 ui.button("start");
 await drain();
 assert.equal(game.getView().status,"active");
 ui.touch("pointerdown",426,179);
 ui.touch("pointermove",326,279);
 ui.touch("pointerup",326,279);
 await drain();
 assert.deepEqual(JSON.parse(JSON.stringify(game.calls)),[{
  session_id:"a".repeat(32),action_seq:0,action:"turn",ticks:10,
 }]);
 assert.equal(game.runtime.getSnapshot().dial,10);
 assert.equal(game.runtime.getSnapshot().action_seq,1);
 assert.equal(Object.hasOwn(game.calls[0],"score"),false);
 assert.equal(Object.hasOwn(game.calls[0],"combination"),false);
 game.runtime.dispose();
 assert.equal(ui.stageEvents.pointerdown,undefined);
});
test("anti-clockwise keyboard input, set tumbler and per-session sequence",async()=>{
 const ui=harness(),game=boot(ui);
 ui.button("start");await drain();
 ui.key("ArrowLeft");await drain();
 assert.equal(game.calls[0].ticks,-1);
 assert.equal(game.calls[0].action_seq,0);
 ui.key("ArrowRight",true);await drain();
 assert.equal(game.calls[1].ticks,4);
 assert.equal(game.calls[1].action_seq,1);
 ui.button("set");await drain();
 assert.equal(game.calls[2].action,"set");
 assert.equal(game.calls[2].ticks,0);
 assert.equal(game.calls[2].action_seq,2);
 game.runtime.dispose();
});
test("wheel label at the pointer matches server-selected dial number",()=>{
 const positions=win.SnowfallSafecrackerV299b.tickPositions;
 const zero=positions(0),five=positions(5);
 assert.equal(zero.length,40);
 assert.equal(five.length,40);
 const topOfZero=zero.find(p=>p.n===0);
 const topOfFive=five.find(p=>p.n===5);
 assert.ok(Math.abs(topOfZero.x-326)<.001);
 assert.ok(Math.abs(topOfZero.y-94)<.001);
 assert.ok(Math.abs(topOfFive.x-326)<.001);
 assert.ok(Math.abs(topOfFive.y-94)<.001);
 assert.equal(win.SnowfallSafecrackerV299b.mod(-1),39);
});
test("unauthoritative timing and codes never appear in the move body",()=>{
 assert.doesNotMatch(code,/client_score|guessedCombination/);
 assert.match(code,/onPointer:pointer,onKey:key,showAim:false/);
 assert.match(code,/getStatus:\(\)=>current\.status/);
 assert.match(code,/setFeedback\(/);
 assert.match(code,/pending=body/);
});
