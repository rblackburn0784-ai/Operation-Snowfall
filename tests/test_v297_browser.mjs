import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";
const source=readFileSync(new URL("../src/snowfall/platform/static/app.js",import.meta.url),"utf8");
function harness(fetch,storage=new Map()){
 let sequence=0;
 const ctx=vm.createContext({fetch,crypto:{randomUUID:()=>`v297-${++sequence}-action`},document:{addEventListener(){}},AbortController,Map,setTimeout,clearTimeout,sessionStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}});
 vm.runInContext(source,ctx);
 vm.runInContext('S.session={player_id:"6000000000000000002",csrf:"private-csrf"};S.config={season:"web-qa-2026"};restorePending()',ctx);
 return ctx;
}
const invoke=(c,path,body)=>vm.runInContext(`request(${JSON.stringify(path)},"POST",${JSON.stringify(body)},true,true)`,c);
const ok=data=>({ok:true,status:200,json:async()=>data});
test("unconfirmed throw survives reload and restores original target and action ID",async()=>{
 const storage=new Map(),sent=[];
 const path="/v1/game/throw",body={target_player_id:"6000000000000000003",style:"standard"};
 const first=harness(async(_,options)=>{sent.push(options.headers);throw Error("lost response")},storage);
 await assert.rejects(invoke(first,path,body),/may have succeeded/);
 assert.equal(storage.size,1);assert.doesNotMatch([...storage.values()][0],/private-csrf/);
 const reopened=harness(async(_,options)=>{sent.push(options.headers);return ok({repeated:true})},storage);
 assert.equal(vm.runInContext("S.lastThrow.body.target_player_id",reopened),body.target_player_id);
 await invoke(reopened,path,body);
 assert.equal(sent[0]["Idempotency-Key"],sent[1]["Idempotency-Key"]);
 assert.equal(sent[1]["X-Snowfall-Player"],"6000000000000000002");
 assert.equal(storage.size,0);
});
test("unreadable 200 response and transient proxy errors preserve action ID",async()=>{
 const seen=[];let count=0;
 const c=harness(async(_,options)=>{
  seen.push(options.headers["Idempotency-Key"]);count++;
  if(count===1)return {ok:true,status:200,json:async()=>{throw Error("truncated")}};
  if(count===2)return {ok:false,status:429,json:async()=>({detail:"retry later"})};
  if(count===3)return {ok:false,status:409,json:async()=>({detail:"Account changed in another tab; sign in again"})};
  return ok({repeated:true});
 });
 for(let i=0;i<3;i++)await assert.rejects(invoke(c,"/v1/game/siege",{}));
 await invoke(c,"/v1/game/siege",{});
 assert.equal(new Set(seen).size,1);
});
test("only the matching account and season restore pending keys",async()=>{
 const storage=new Map();
 const first=harness(async()=>{throw Error("offline")},storage);
 await assert.rejects(invoke(first,"/v1/game/craft",{item:"fort"}));
 const second=harness(async()=>ok({}),storage);
 vm.runInContext('S.pendingActions.clear();S.session.player_id="6000000000000000003";restorePending()',second);
 assert.equal(vm.runInContext("S.pendingActions.size",second),0);
 vm.runInContext('S.session.player_id="6000000000000000002";S.config.season="another-season";restorePending()',second);
 assert.equal(vm.runInContext("S.pendingActions.size",second),0);
});
