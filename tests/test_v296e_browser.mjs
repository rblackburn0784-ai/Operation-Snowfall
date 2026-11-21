import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";
const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const ctx=vm.createContext({document:{addEventListener(){}},URL});
vm.runInContext(js,ctx);
const run=s=>vm.runInContext(s,ctx);
run(`S.items=[
 {key:"gold_frame",category:"frame",cost:15,name:"Golden Gutter Frame",detail:"Gold",rarity:"Epic"},
 {key:"ice_frame",category:"frame",cost:8,name:"Icy Noir Frame",detail:"Frost",rarity:"Common"},
 {key:"frost_spectre_f",category:"portrait",cost:18,name:"Frost Spectre — Female",detail:"Frost",rarity:"Legendary"},
 {key:"snow_trail",category:"trail",cost:6,name:"Snowstorm Trail",detail:"Snow",rarity:"Common"}];
 S.shop={balance:10,unlocked:["ice_frame","snow_trail"],equipped:{frame:"ice_frame"}};
 S.session={player_id:"42",links:[{provider:"underworld"}]};
 S.me={player_id:"42",registered:true,phase:"live"};
 S.config={staging:true};S.catalogReady=true;`);
test("preview can combine unowned items without changing actual wardrobe",()=>{
 const result=run(`fittingLayers(S.shop,{frame:"gold_frame",portrait:"frost_spectre_f",trail:"snow_trail"},S.items)`);
 assert.equal(result.frame.key,"gold_frame");assert.equal(result.portrait.key,"frost_spectre_f");assert.equal(result.trail.key,"snow_trail");
 assert.equal(run("profileLayers(S.shop).frame.key"),"ice_frame");
 assert.equal(run("profileLayers(S.shop).portrait.key"),null);
 assert.equal(run("S.shop.balance"),10);
 assert.equal(run("S.shop.unlocked.includes('gold_frame')"),false);
});
test("preview rejects unknown items and wrong slots, all existing artwork is committed",()=>{
 for(const src of Object.values(run("COSMETIC_ART")))assert.ok(existsSync(path.join(root,"graphics",src)),src);
 const v=run(`fittingLayers(S.shop,{frame:"frost_spectre_f",portrait:"../../private"},S.items)`);
 assert.equal(v.frame.key,"ice_frame");assert.equal(v.portrait.key,null);
 for(const id of ["fitPortrait","fitFrame","fitBanner","fitGear","fitTrail","fitReset","featuredTry","marketCategory","marketOwnership","marketSearch","craftArtwork","hqPortrait","heroBossArt"])assert.equal([...html.matchAll(new RegExp('id="'+id+'"',"g"))].length,1,id);
});
test("filters combine ownership rarity and price without modifying catalogue",()=>{
 const filter=(f,w="S.shop")=>Array.from(run("filterMarket(S.items,{category:'all',ownership:'all',rarity:'all',sort:'catalogue',search:'',..."+JSON.stringify(f)+"},"+w+").map(i=>i.key)"));
 assert.deepEqual(filter({ownership:"owned",sort:"low"}),["snow_trail","ice_frame"]);
 assert.deepEqual(filter({ownership:"equipped"}),["ice_frame"]);
 assert.deepEqual(filter({rarity:"Legendary",search:"female"}),["frost_spectre_f"]);
 assert.deepEqual(filter({ownership:"affordable"}),[]);
 assert.deepEqual(filter({ownership:"unowned"},"null"),[]);
 assert.equal(run("S.items[0].key"),"gold_frame");
});
test("purchase and equip require current canonical wardrobe and actual eligibility",()=>{
 assert.equal(run("marketEligible(S.items[0],'buy')"),false);
 assert.equal(run("marketEligible(S.items[3],'equip')"),true);
 assert.equal(run("marketEligible(S.items[1],'equip')"),false);
 run("S.shop.balance=20;S.me.phase='paused'");
 assert.equal(run("marketEligible(S.items[0],'buy')"),false);
 assert.equal(run("marketEligible(S.items[3],'equip')"),true);
 run("S.me.phase='live'");
 assert.equal(run("marketEligible(S.items[0],'buy')"),true);
 run("S.session.player_id='43'");
 assert.equal(run("marketEligible(S.items[0],'buy')"),false);
 run("S.session=null");
 assert.equal(run("marketWardrobe()"),null);
});
