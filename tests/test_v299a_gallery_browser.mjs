// v2.9.9a — shared scene, complete Gallery and API boundaries (Node smoke).
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const gallery=readFileSync(path.join(root,"arcade-gallery-v299a.js"),"utf8");
const engine=readFileSync(path.join(root,"arcade-v299.js"),"utf8");
const app=readFileSync(path.join(root,"app.js"),"utf8");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const css=readFileSync(path.join(root,"app.css"),"utf8");
const listeners={},documentListeners={};
const win={
 requestAnimationFrame:()=>1,cancelAnimationFrame(){},
 matchMedia:()=>({matches:false}),document:{
  addEventListener(k,fn){documentListeners[k]=fn},
  removeEventListener(k){delete documentListeners[k]}
 }
};
const mockImg=class Image {src="";complete=false;naturalWidth=0};
const sandbox={window:win,Image:mockImg,console,performance:{now:()=>1000}};
vm.runInNewContext(engine,sandbox);
vm.runInNewContext(gallery,sandbox);

function dom(){
 const buttons={},labels={};
 const make=()=>({textContent:"",dataset:{},disabled:false,attrs:{},
  setAttribute(k,v){this.attrs[k]=v}});
 const context={};
 const canvas={
  getContext:()=>context,
  getBoundingClientRect:()=>({left:0,top:0,width:640,height:360}),
  addEventListener(k,fn){listeners[k]=fn},
  removeEventListener(k){delete listeners[k]},focus(){}
 };
 const feedback=make();
 const root={
  innerHTML:"",classList:{remove(){},add(){}},
  querySelector(sel){
   if(sel==="canvas")return canvas;
   if(sel===".arcade-training-feedback")return feedback;
   const key=sel.match(/data-scene='([^']+)'/);
   if(key)return buttons[key[1]]??(buttons[key[1]]=make());
   const label=sel.match(/data-scene-label='([^']+)'/);
   if(label)return labels[label[1]]??(labels[label[1]]=make());
   throw Error("unexpected selector "+sel);
  },
  addEventListener(k,fn){listeners[k]=fn},
  removeEventListener(k){delete listeners[k]}
 };
 const click=action=>listeners.click({target:{closest:()=>({dataset:{scene:action}})}});
 return {root,canvas,feedback,click,buttons,labels};
}
const fresh=()=>({
 session_id:"a".repeat(32),mode:"gallery",day:1,status:"paused",
 duration_ms:45000,elapsed_ms:0,server_epoch_ms:0,
 schedule:[{id:0,kind:"normal",wave:1,start:450,life:2000,
  x0:320,y:180,amp:35,rate:2,phase:0,radius:28}],
 claimed:[],ammo:32,shots_used:0,hits:0,misses:0,decoys:0,
 combo:0,best_combo:0,score:0,accuracy:0,feedback:"",
});

test("scene system is reusable, Gallery asset is cached and classic Discord stays separate",()=>{
 assert.equal(typeof win.SnowfallArcadeV299.mount,"function");
 assert.equal(typeof win.SnowfallArcadeV299.mountScene,"function");
 assert.equal(typeof win.SnowfallGalleryV299a.mount,"function");
 assert.match(html,/arcade-v299\.js\?v=299g/);
 assert.match(html,/arcade-gallery-v299a\.js\?v=299g/);
 assert.match(html,/id="arcadeGallery"/);
 assert.match(css,/arcade-full-gallery/);
 assert.match(css,/touch-action:none/);
 assert.match(app,/gallery_v299a_enabled/);
 assert.match(app,/\/v1\/game\/arcade\/gallery\/shot/);
 assert.match(app,/\/v1\/game\/arcade\/move/); // untouched Discord choice gameplay
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-gallery-v299a.js"));
});
test("server snapshot drives responsive stage, clicks send coordinates, not a chosen score",async()=>{
 const ui=dom();const attempts=[];const base=fresh();
 let view=base;
 const runtime=win.SnowfallGalleryV299a.mount({
  root:ui.root,session:view,
  start:async()=>view=({...view,status:"active"}),
  control:async(_id,action)=>view=({...view,status:action==="resume"?"active":"paused"}),
  shot:async body=>{
   attempts.push(body);
   return view=({...view,shots_used:1,ammo:31,hits:1,score:7,accuracy:100,
    last_event:{outcome:"hit",target_id:0,feedback:"Clean hit!"}});
  },
  refresh:async()=>view,onExit:()=>{}
 });
 assert.match(ui.root.innerHTML,/45 seconds|Start \/ resume/);
 ui.click("start");
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(ui.buttons.start.textContent,"Playing");
 assert.equal(typeof listeners.pointerdown,"function");
 listeners.pointerdown({type:"pointerdown",clientX:300,clientY:185,preventDefault(){}});
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(JSON.parse(JSON.stringify(attempts)),[
  {session_id:"a".repeat(32),shot_index:0,x:300,y:185}
 ]);
 assert.equal(runtime.getSnapshot().score,7);
 assert.equal(runtime.getSnapshot().ammo,31);
 assert.equal(runtime.getSnapshot().hits,1);
 assert.equal(ui.feedback.textContent,"Clean hit!");
 runtime.dispose();
 assert.equal(listeners.pointerdown,undefined);
});
test("target motion follows authoritative sine equation and is stable on resuming",()=>{
 const t=fresh().schedule[0];
 const position=win.SnowfallGalleryV299a.position;
 const a=position(t,450),b=position(t,1450);
 assert.ok(Math.abs(a.x-320)<.001);
 assert.ok(Math.abs(b.x-(320+35*Math.sin(2)))<.001);
 assert.equal(a.y,b.y);
 assert.notEqual(a.x,b.x);
});
