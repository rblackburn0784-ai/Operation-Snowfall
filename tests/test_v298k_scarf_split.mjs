import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const app=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const css=readFileSync(path.join(root,"platform/static/app.css"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const ctx=vm.createContext({document:{addEventListener(){}},URL});
vm.runInContext(app,ctx);
const run=expr=>vm.runInContext(expr,ctx);
const oldAsset="/art/v290/cosmetics/gear/scarf.png";
const wornAsset="/art/v290/cosmetics/gear/scarf_worn.png";

test("catalogue product art never changes, worn art is a separate file",()=>{
 assert.equal(run("COSMETIC_ART.scarf"),oldAsset);
 assert.equal(run('wornCosmeticArt("scarf")'),wornAsset);
 assert.equal(run('wornCosmeticArt("goggles")'),run("COSMETIC_ART.goggles"));
 assert.notEqual(run("WORN_COSMETIC_ART.scarf"),run("COSMETIC_ART.scarf"));
 const oldPath=path.join(root,"graphics",oldAsset.slice(1));
 const newPath=path.join(root,"graphics",wornAsset.slice(1));
 assert.ok(existsSync(oldPath),"existing original Market art must remain");
 assert.ok(existsSync(newPath),"new transparent worn art must exist");
 const buff=readFileSync(newPath);
 assert.deepEqual([...buff.subarray(0,8)],[137,80,78,71,13,10,26,10]);
 assert.ok(buff.includes(Buffer.from("tRNS")),"PNG must preserve alpha transparency");
 assert.ok(buff.readUInt32BE(16)>=180&&buff.readUInt32BE(20)>=180);
});

test("equipped HQ and eligible rival use new image with same unlock",()=>{
 const wardrobe={unlocked:["scarf","goggles"],equipped:{gear:"scarf"}};
 const layers=run("profileLayers("+JSON.stringify(wardrobe)+")");
 assert.equal(layers.gear.key,"scarf");
 assert.equal(layers.gear.src,wornAsset);
 assert.equal(layers.frame.key,null);
 const rival=run('rivalWardrobe({gear:"scarf"})');
 assert.equal(rival.equipped.gear,"scarf");
 const rivalLayers=run('profileLayers(rivalWardrobe({gear:"scarf"}))');
 assert.equal(rivalLayers.gear.src,wornAsset);
 assert.equal(run('profileLayers({unlocked:[],equipped:{gear:"scarf"}}).gear.src'),null);
 assert.equal(run('profileLayers({unlocked:["goggles"],equipped:{gear:"goggles"}}).gear.src'),
              run("COSMETIC_ART.goggles"));
});

test("free Market fitting preview uses worn overlay, without buying/equipping",()=>{
 const wardrobe={unlocked:[],equipped:{}};
 const items=[{key:"scarf",category:"gear",name:"Snow Don Scarf",cost:18,rarity:"Epic",detail:""}];
 const before=JSON.stringify(wardrobe);
 const layers=run("fittingLayers("+JSON.stringify(wardrobe)+",{gear:'scarf'},"+JSON.stringify(items)+")");
 assert.equal(layers.gear.key,"scarf");
 assert.equal(layers.gear.src,wornAsset);
 assert.equal(JSON.stringify(wardrobe),before);
 const catalogHtml=run("marketCard("+JSON.stringify(items[0])+",null)");
 assert.ok(catalogHtml.includes(oldAsset));
 assert.ok(!catalogHtml.includes(wornAsset));
 assert.ok(app.includes('art.setAttribute("src",COSMETIC_ART[chosen.key])'),
           "featured Market display must also retain original item artwork");
 assert.ok(app.includes('Object.hasOwn(COSMETIC_ART,i.key)?COSMETIC_ART[i.key]:null'),
           "catalogue art must never be the worn overlay");
});

test("worn scarf geometry stays aligned to the eight source portraits",()=>{
 const keys=Array.from(run("Object.keys(PORTRAIT_FIT)"));
 assert.equal(keys.length,8);
 for(const key of keys){
  for(const framed of [false,true]){
   const neck=run("cosmeticPlacement("+JSON.stringify(key)+",'scarf',"+framed+")");
   const eyes=run("cosmeticPlacement("+JSON.stringify(key)+",'goggles',"+framed+")");
   assert.ok(neck.left>45&&neck.left<57,key);
   assert.ok(neck.top>eyes.top+9&&neck.top<eyes.top+25,key);
   assert.ok(neck.width>22&&neck.width<38,key);
   assert.equal(neck.transform,"translateX(-50%)");
  }
 }
 assert.ok(css.includes("mask-image:none;"),"new tassels must remain visible");
 assert.match(css,/scarf_worn\.png|v2\.9\.8k/);
});

test("web release and prior IDs remain unchanged",()=>{
 assert.match(html,/snowfall-web-release" content="2\.9\.8k"/);
 assert.match(html,/app\.css\?v=298k/);
 assert.match(html,/app\.js\?v=298k/);
 for(const prefix of ["hq","fit","rival"]){
  assert.ok(html.includes('id="'+prefix+'Gear"'));
  assert.ok(html.includes('id="'+prefix+'PortraitWell"'));
 }
});
