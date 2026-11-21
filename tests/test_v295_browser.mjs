/* v2.9.5 — Browser requests retain their idempotency key after an uncertain outcome. */
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";

const source=readFileSync(new URL("../src/snowfall/platform/static/app.js",import.meta.url),"utf8");

function harness(fetchImpl){
 let sequence=0;
 const context=vm.createContext({
  fetch:fetchImpl,
  crypto:{randomUUID:()=>`v295-${++sequence}-client-action`},
  document:{addEventListener:()=>{}},
  AbortController,Map,setTimeout,clearTimeout,
 });
 vm.runInContext(source,context);
 vm.runInContext('S.session={player_id:"6000000000000000002",csrf:"csrf-test"}',context);
 return context;
}
function invoke(ctx,path,body){
 return vm.runInContext(
  `request(${JSON.stringify(path)},"POST",${JSON.stringify(body)},true,true)`,ctx);
}
const ok=(body)=>({ok:true,status:200,json:async()=>body});
const fail=(code)=>({ok:false,status:code,json:async()=>({detail:"request blocked"})});

test("lost response may have committed: retry uses exact original action key",async()=>{
 const seen=[];
 let count=0;
 const ctx=harness(async(_url,options)=>{
  seen.push(options.headers["Idempotency-Key"]);
  if(++count===1)throw new Error("connection lost");
  return ok({text:"Crafted cocoa"});
 });
 await assert.rejects(invoke(ctx,"/v1/game/craft",{item:"cocoa"}),/may have succeeded/i);
 assert.equal(vm.runInContext("S.pendingActions.size",ctx),1);
 assert.deepEqual(await invoke(ctx,"/v1/game/craft",{item:"cocoa"}),{text:"Crafted cocoa"});
 assert.equal(seen.length,2);
 assert.equal(seen[0],seen[1],"replayed request must preserve its ID");
 assert.equal(vm.runInContext("S.pendingActions.size",ctx),0);
});

test("5xx preserves a key; business-rule 409 ends that attempt",async()=>{
 const seen=[];
 const responses=[fail(503),fail(409),ok({repeated:false})];
 const ctx=harness(async(_url,options)=>{
  seen.push(options.headers["Idempotency-Key"]);
  return responses.shift();
 });
 await assert.rejects(invoke(ctx,"/v1/game/boss",{}),/uncertain/i);
 assert.equal(vm.runInContext("S.pendingActions.size",ctx),1);
 await assert.rejects(invoke(ctx,"/v1/game/boss",{}),/request blocked/i);
 assert.equal(vm.runInContext("S.pendingActions.size",ctx),0);
 await invoke(ctx,"/v1/game/boss",{});
 assert.equal(seen[0],seen[1]);
 assert.notEqual(seen[1],seen[2]);
});

test("two successful player actions get distinct IDs and valid CSRF",async()=>{
 const seen=[];
 const ctx=harness(async(_url,options)=>{
  seen.push(options.headers);
  return ok({repeated:false});
 });
 await invoke(ctx,"/v1/game/craft",{item:"fort"});
 await invoke(ctx,"/v1/game/craft",{item:"fort"});
 assert.notEqual(seen[0]["Idempotency-Key"],seen[1]["Idempotency-Key"]);
 assert.equal(seen[0]["X-Snowfall-CSRF"],"csrf-test");
});

test("an uncertain request from another canonical player cannot reuse the key",async()=>{
 const seen=[];
 const ctx=harness(async(_url,options)=>{
  seen.push(options.headers["Idempotency-Key"]);
  if(seen.length===1)throw new Error("connection lost");
  return ok({repeated:false});
 });
 await assert.rejects(invoke(ctx,"/v1/game/craft",{item:"cocoa"}));
 vm.runInContext('S.session={player_id:"6000000000000000003",csrf:"other-csrf"}',ctx);
 await invoke(ctx,"/v1/game/craft",{item:"cocoa"});
 assert.notEqual(seen[0],seen[1]);
});
