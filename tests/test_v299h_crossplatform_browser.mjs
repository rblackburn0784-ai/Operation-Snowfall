// v2.9.9h — browser session-epoch boundary and all-five Arcade 2.0 mounting.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import path from "node:path";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const app=readFileSync(path.join(root,"app.js"),"utf8").replace(/\r\n/g,"\n");
const html=readFileSync(path.join(root,"index.html"),"utf8");
const hub=readFileSync(path.join(root,"arcade-hub-v299f.js"),"utf8");
const scripts=[
 "arcade-v299.js","arcade-gallery-v299a.js","arcade-safe-v299b.js",
 "arcade-snowman-v299c.js","arcade-catch-v299d.js",
 "arcade-trivia-v299e.js","arcade-hub-v299f.js",
];
test("all seven arcade scripts are bundled, loaded once, and fresh for v2.9.9h",()=>{
 assert.match(html,/snowfall-interactive-arcade-release" content="2\.9\.9h"/);
 for(const script of scripts){
  const matches=html.match(new RegExp(script.replace(".","\\.")+"\\?v=299h","g"))||[];
  assert.equal(matches.length,1,script+" must be loaded and cache-busted once");
  assert.ok(readFileSync(path.join(root,script)).length>300);
 }
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-gallery-v299a.js"));
 assert.ok(html.indexOf("arcade-v299.js")<html.indexOf("arcade-hub-v299f.js"));
 assert.match(hub,/Classic Arcade/);
 assert.ok(app.includes("/v1/game/arcade/move")); // Discord Classic preserved
});
test("every full game rejects late AJAX updates and onExit from old owner epoch",()=>{
 for(const mode of ["Gallery","Safe","Snowman","Catch","Trivia"]){
  const start=app.indexOf("function mountArcade"+mode+"(){");
  assert.ok(start>=0,"Missing "+mode+" controller");
  const next=app.indexOf("\nfunction ",start+10);
  const code=app.slice(start,next<0?undefined:next);
  assert.match(code,/const owner=arcadeOwner\(\);ensureArcadeOwner\(owner\);/);
  assert.match(code,/const accepted=view=>/);
  assert.match(code,/ensureArcadeOwner\(owner\);/);
  assert.match(code,/onExit:\(\)=>\{if\(!isArcadeOwner\(owner\)\)return;/);
 }
});
test("same player relogin, different player and logout all invalidate old requests",()=>{
 const start=app.indexOf("function arcadeOwner(){");
 const end=app.indexOf("function syncPlayIdentity(){");
 assert.ok(start>0&&end>start);
 const code=app.slice(start,end);
 const S={arcadeEpoch:4,session:{player_id:"101"}};
 const ctx={S};vm.createContext(ctx);
 vm.runInContext(code+";this.capture=arcadeOwner;"+
    "this.valid=isArcadeOwner;this.guard=ensureArcadeOwner;",ctx);
 const pending=ctx.capture();
 assert.equal(ctx.valid(pending),true);
 S.session={player_id:"202"};S.arcadeEpoch++;
 assert.equal(ctx.valid(pending),false);
 assert.throws(()=>ctx.guard(pending),/Account changed/);
 S.session={player_id:"101"};S.arcadeEpoch++;
 assert.equal(ctx.valid(pending),false);
 const newer=ctx.capture();
 assert.equal(ctx.valid(newer),true);
 S.session=null;S.arcadeEpoch++;
 assert.equal(ctx.valid(newer),false);
});
test("all arcade and private-data async paths verify character after awaits",()=>{
 assert.ok(app.includes('const playerView=await get("/v1/game/me");\n  if(!isArcadeOwner(owner))return;'));
 assert.match(app,/if\(!isArcadeOwner\(owner\)\)return;\n  if\(results.some/);
 assert.match(app,/ensureArcadeOwner\(owner\);\n if\(view.mode!==key/);
 assert.match(app,/S\.arcadeEpoch\+\+/);
 for(const url of [
  "trivia/start","catch/start","snowman/start",
  "safecracker/start","gallery/start",
 ]){
  assert.ok(app.includes("/v1/game/arcade/"+url));
 }
 assert.match(app,/X-Snowfall-Player/);
 assert.match(app,/X-Snowfall-CSRF/);
 assert.match(app,/Idempotency-Key/);
 assert.match(app,/sessionStorage/);
 assert.doesNotMatch(app,/localStorage\.setItem\([^\n]*(password|csrf|token)/i);
});
