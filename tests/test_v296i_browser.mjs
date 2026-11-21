import assert from "node:assert/strict";
import {readFileSync,existsSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";
import path from "node:path";
import {fileURLToPath} from "node:url";
const root=fileURLToPath(new URL("../src/snowfall/",import.meta.url));
const js=readFileSync(path.join(root,"platform/static/app.js"),"utf8");
const html=readFileSync(path.join(root,"platform/static/index.html"),"utf8");
const ctx=vm.createContext({document:{addEventListener(){}},URL});
vm.runInContext(js,ctx);
const run=s=>vm.runInContext(s,ctx);
run('const siegeWorld={city:"Chicago",day:2,siege_hp:42,siege_max_hp:72,siege_attempts:1,siege_points:8};const siegeMe={city:"Chicago",registered:true,day:2};const siegeConfig={rival_schedule:{"1":[["Chicago","Los Angeles"]],"2":[["Chicago","Detroit"]]}};');
test("siege is in City Wars only and uses original artwork",()=>{
 const boss=html.split('id="page-boss"')[1].split('id="page-shop"')[0];
 const cities=html.split('id="page-cities"')[1].split('id="page-wire"')[0];
 assert.doesNotMatch(boss,/id="siegeButton"/);
 assert.match(cities,/id="siegeButton"/);
 assert.equal([...html.matchAll(/id="siegeButton"/g)].length,1);
 assert.ok(existsSync(path.join(root,"graphics/art/v290/items/siege.png")));
});
test("actual shared world day selects rival independent of map selection and archive",()=>{
 assert.equal(run("siegeAssignment(siegeWorld,siegeMe,siegeConfig).rival"),"Detroit");
 assert.equal(run("S.territoryDay='1';S.citySelected='Philadelphia';siegeAssignment(siegeWorld,siegeMe,siegeConfig).rival"),"Detroit");
 assert.equal(run('siegeAssignment({...siegeWorld,city:"New York"},siegeMe,siegeConfig)'),null);
 assert.equal(run('siegeAssignment({...siegeWorld,day:1},siegeMe,siegeConfig)'),null);
 assert.equal(run('siegeAssignment(siegeWorld,null,siegeConfig)'),null);
 assert.equal(run('siegeAssignment({...siegeWorld,siege_hp:0},siegeMe,siegeConfig).cleared'),true);
 assert.equal(run('siegeAssignment({...siegeWorld,siege_max_hp:0},siegeMe,siegeConfig).known'),false);
});
test("all portraits have calibrated gear and side trail placements",()=>{
 assert.equal(run("Object.keys(PORTRAIT_FIT).length"),8);
 for(const key of Array.from(run("Object.keys(PORTRAIT_FIT)"))){
  for(const framed of [true,false]){
   const calc=gear=>run("cosmeticPlacement("+JSON.stringify(key)+","+JSON.stringify(gear)+","+framed+")");
   const eyes=calc("goggles"),neck=calc("scarf"),trail=calc("snow_trail");
   assert.ok(eyes.top>=19&&eyes.top<=30,key);
   assert.ok(eyes.left>49&&eyes.left<58,key);
   assert.ok(eyes.width<37&&eyes.width>27,key);
   assert.ok(neck.top>eyes.top+12,key);
   assert.ok(trail.left>60&&trail.left+trail.width<=100,key);
   assert.deepEqual(calc("candy_trail"),trail);
  }
 }
 assert.notEqual(run('cosmeticPlacement("winter_enforcer","goggles",true).top'),run('cosmeticPlacement("recruit_f","goggles",true).top'));
 assert.equal(run('cosmeticPlacement("recruit","invalid",true)'),null);
});
