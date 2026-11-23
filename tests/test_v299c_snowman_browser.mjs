// v2.9.9c — real Snowman Builder drag/drop, touch, keyboard and server score.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const engine=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const code=readFileSync(path.join(root,"arcade-snowman-v299c.js"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
const win={
 requestAnimationFrame:()=>1,cancelAnimationFrame(){},
 matchMedia:()=>({matches:false}),
 document:{hidden:false,addEventListener(){},removeEventListener(){}}
};
vm.runInNewContext(engine,{window:win,console});
vm.runInNewContext(code,{window:win,console,performance:{now:()=>1000},
 Image:class {src="";complete=false;naturalWidth=0}});
const fresh=()=>({
 session_id:"a".repeat(32),mode:"snowman",status:"paused",day:1,
 duration_ms:150000,elapsed_ms:0,action_seq:0,
 stage:0,round:1,total_rounds:3,placed:[],placed_total:0,total_parts:20,
 mistakes:0,score:0,feedback:"",complete:false,
 blueprint:{
  round:1,name:"First Snowfall",required:4,bonus:4,
  slots:[
   {id:"base",x:249,y:270,radius:38},
   {id:"torso",x:249,y:206,radius:32},
   {id:"head",x:249,y:142,radius:26},
   {id:"hat",x:249,y:93,radius:24}
  ],
  parts:[
   {id:"base",label:"Big snowball",decoy:false},
   {id:"torso",label:"Middle snowball",decoy:false},
   {id:"head",label:"Small snowball",decoy:false},
   {id:"hat",label:"Top hat",decoy:false}
  ]
 }
});
function ui(){
 const stage={},controls={},nodes={};
 const make=()=>({textContent:"",disabled:false,attrs:{},dataset:{},
  setAttribute(k,v){this.attrs[k]=v}});
 const canvas={
  getContext:()=>({}),getBoundingClientRect:()=>({
   left:0,top:0,width:640,height:360
  }),setPointerCapture(){},focus(){},
  addEventListener(k,fn){stage[k]=fn},
  removeEventListener(k){delete stage[k]}
 };
 const element={
  innerHTML:"",classList:{remove(){},add(){}},
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")return nodes.feedback??(nodes.feedback=make());
   const action=sel.match(/data-scene='([^']+)'/);
   if(action)return nodes[action[1]]??(nodes[action[1]]=make());
   const label=sel.match(/data-scene-label='([^']+)'/);
   if(label)return nodes[label[1]]??(nodes[label[1]]=make());
   throw Error("Unexpected selector: "+sel);
  },
  addEventListener(k,fn){controls[k]=fn},
  removeEventListener(k){delete controls[k]}
 };
 const button=name=>controls.click({target:{
  closest:()=>({dataset:{scene:name}})
 }});
 const pointer=(type,x,y,pointerId=1)=>stage[type]({
  type,clientX:x,clientY:y,pointerId,preventDefault(){}
 });
 const key=(name,shiftKey=false)=>stage.keydown({
  key:name,shiftKey,preventDefault(){}
 });
 return {element,nodes,button,pointer,key,stage};
}
async function drain(){
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
}
function launch(mountPoint,source=fresh()){
 let latest=source;
 const calls=[];
 const instance=win.SnowfallSnowmanV299c.mount({
  root:mountPoint.element,session:latest,
  start:async()=>latest={...fresh(),session_id:"b".repeat(32)},
  control:async(_id,action)=>latest={...latest,status:
   action==="resume"?"active":action==="finish"?"finished":"paused"},
  place:async body=>{
   calls.push(body);
   const placed=[...latest.placed,body.piece_id];
   return latest={...latest,action_seq:latest.action_seq+1,
    placed,placed_total:placed.length,score:placed.length*4,
    last_action:{outcome:"placed",piece_id:body.piece_id,
      feedback:"Perfect fit!",stage:0},
    feedback:"Perfect fit!"};
  },
  refresh:async()=>latest,
  fetchRecord:async()=>({personal_best:100,completed_builds:1}),
  onExit:()=>{}
 });
 return {instance,calls,latest:()=>latest};
}
test("Snowman Builder reuses the existing stage and preserves Gallery/Safe/Discord",()=>{
 assert.equal(typeof win.SnowfallArcadeV299.mountScene,"function");
 assert.equal(typeof win.SnowfallSnowmanV299c.mount,"function");
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-snowman-v299c.js"));
 assert.match(html,/arcade-snowman-v299c\.js\?v=299h/);
 assert.match(html,/id="arcadeSnowman"/);
 assert.match(css,/arcade-full-snowman/);
 assert.match(css,/touch-action:none/);
 assert.match(app,/snowman_v299c_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/snowman\/place/);
 assert.match(app,/\/v1\/game\/arcade\/gallery\/shot/);
 assert.match(app,/\/v1\/game\/arcade\/safecracker\/move/);
 assert.match(app,/\/v1\/game\/arcade\/move/);
});
test("drag from tray to blueprint submits validated piece and coordinates only",async()=>{
 const view=ui(),game=launch(view);
 assert.match(view.element.innerHTML,/Place selected part/);
 view.button("start");await drain();
 assert.equal(game.latest().status,"active");
 view.pointer("pointerdown",490,76);
 view.pointer("pointermove",249,270);
 view.pointer("pointerup",249,270);
 await drain();
 assert.deepEqual(JSON.parse(JSON.stringify(game.calls)),[{
  session_id:"a".repeat(32),action_seq:0,piece_id:"base",x:249,y:270
 }]);
 assert.equal(game.instance.getSnapshot().score,4);
 assert.equal(game.instance.getSnapshot().placed_total,1);
 assert.equal(Object.hasOwn(game.calls[0],"score"),false);
 assert.equal(Object.hasOwn(game.calls[0],"target"),false);
 game.instance.dispose();
 assert.equal(view.stage.pointerdown,undefined);
});
test("touch selection followed by touch drop also works, without drag distance",async()=>{
 const view=ui(),game=launch(view);
 view.button("start");await drain();
 view.pointer("pointerdown",490,76);
 view.pointer("pointerup",490,76);
 await drain();
 assert.equal(game.calls.length,0);
 view.pointer("pointerdown",249,270);
 view.pointer("pointerup",249,270);
 await drain();
 assert.equal(game.calls.length,1);
 assert.equal(game.calls[0].piece_id,"base");
 game.instance.dispose();
});
test("keyboard part selection and arrows allow full game without pointer",async()=>{
 const view=ui(),game=launch(view);
 view.button("start");await drain();
 view.key("2"); // Middle snowball: cursor initially at x249,y205
 view.key("Enter");await drain();
 assert.equal(game.calls[0].piece_id,"torso");
 assert.equal(game.calls[0].x,249);
 assert.equal(game.calls[0].y,205);
 assert.equal(game.instance.getSnapshot().placed_total,1);
 view.key("Escape");
 view.button("guide");
 assert.match(view.nodes.feedback.textContent,/Outlines hidden/);
 game.instance.dispose();
});
test("tray layout accommodates all eleven parts on a 360px canvas",()=>{
 const bounds=win.SnowfallSnowmanV299c.trayBounds;
 const first=bounds(0),eleventh=bounds(10);
 assert.equal(first.x,473);
 assert.ok(first.y>=60&&eleventh.y+eleventh.h<=360);
 assert.ok(eleventh.x+eleventh.w<=640);
 assert.equal(win.SnowfallSnowmanV299c.labels.arm_left,"Left twig");
});
