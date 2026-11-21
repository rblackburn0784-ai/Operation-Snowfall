import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";
const root=new URL("../src/snowfall/platform/static/",import.meta.url);
const js=readFileSync(new URL("app.js",root),"utf8");
const html=readFileSync(new URL("index.html",root),"utf8");
const ctx=vm.createContext({document:{addEventListener(){}},URL});
vm.runInContext(js,ctx);
const run=s=>vm.runInContext(s,ctx);
run('const fixture={session:{links:[{provider:"underworld"}]},config:{staging:true,play_rules:{boss_limit:6,siege_limit:4,boss_cap:50,pvp_cap:300,craft_costs:{fort:8},item_caps:{fort:2}}},me:{registered:true,phase:"live",day:2,resources:{snowballs:2,snowflakes:6,today_pvp:0}},hq:{timers:{}},world:{boss_attempts:1,boss_points:4},progress:{inventory:{golden:0,fort:0}},now:Date.parse("2026-12-01T10:00:00Z"),kind:"boss"};');
test("quick play honors identity, phases, cooldown, ammo, caps and exact replay",()=>{
 assert.equal(run("playBlock(fixture)"),"");
 assert.match(run('playBlock({...fixture,session:{links:[{provider:"discord"}]}})'),/Underworld/);
 assert.match(run('playBlock({...fixture,me:{...fixture.me,phase:"paused"}})'),/paused/i);
 assert.match(run('playBlock({...fixture,world:{boss_attempts:6}})'),/limit/);
 assert.match(run('playBlock({...fixture,hq:{timers:{throw:"2026-12-01T10:00:20Z"}}})'),/20s/);
 assert.match(run('playBlock({...fixture,me:{...fixture.me,resources:{snowballs:0}}})'),/Out of snowballs/);
 assert.equal(run('playBlock({...fixture,me:{...fixture.me,resources:{snowballs:0}},pending:true})'),"");
 assert.match(run('playBlock({...fixture,kind:"throw",style:"golden"})'),/Golden Snowball/);
 assert.equal(run('playBlock({...fixture,kind:"craft",item:"fort"})'),"");
 assert.match(run('playBlock({...fixture,kind:"craft",item:"fort",progress:{inventory:{fort:2}}})'),/maximum/);
 assert.equal(run('playBlock({...fixture,me:{...fixture.me,review_state:"flagged"}})'),"");
});
test("primary action remains navigation rather than automatic attack",()=>{
 assert.equal(run('chooseQuickPlay({phase:"live",targets:0,bossBlocked:"",throwBlocked:""}).route'),"boss");
 assert.equal(run('chooseQuickPlay({phase:"live",targets:2,bossBlocked:"",throwBlocked:""}).route'),"combat");
 assert.equal(run('chooseQuickPlay({phase:"closed"}).route'),"wire");
 assert.equal(run('chooseQuickPlay({phase:"paused"}).route'),"cities");
 assert.ok(html.indexOf('id="playPrimary"')<html.indexOf('id="hqCollector"'));
 assert.ok(html.indexOf('id="ammoValue"')<html.indexOf('id="hqCollector"'));
 for(const id of ["playStatus","playPrimary","combatOutcome","playFeedback","underworldLogin","qaLoginTools","targetDetail","craftHint","fitPortrait","cityMapOverlay","wirePaper","heroBossArt"])assert.equal([...html.matchAll(new RegExp('id="'+id+'"',"g"))].length,1,id);
});
test("Underworld link only accepts configured HTTPS origin",()=>{
 assert.equal(run('safeUnderworldUrl("https://qa.example")'),"https://qa.example/");
 for(const url of ["javascript:alert(1)","http://qa.example","https://a:b@qa.example","https://qa.example/path","https://qa.example?token=secret"])assert.equal(run("safeUnderworldUrl("+JSON.stringify(url)+")"),"");
});
