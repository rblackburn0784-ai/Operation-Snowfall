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
run('const fixture={day:1,current_day:2,phase:"live",banners:[{city:"Chicago"}],matches:[{city_a:"Chicago",city_b:"Los Angeles",rally_owner:"Chicago",duel_owner:null,rally_a:8,rally_b:0,hits_a:0,hits_b:0}],districts:[{kind:"home",owner:"Chicago",contenders:["Chicago"]},{kind:"rally",owner:"Chicago",contenders:["Chicago","Los Angeles"]},{kind:"duel",owner:null,contenders:["Chicago","Los Angeles"]}]};');
test("all six original city art sets and outcome assets are present",()=>{
 for(const city of Object.keys(run("CITY_META")))for(const type of ["skyline","crest","banner"]){
  const src=run("cityAsset("+JSON.stringify(city)+","+JSON.stringify(type)+")");
  assert.ok(existsSync(path.join(root,"graphics",src.slice(1))),src);
 }
 assert.equal(run('cityAsset("../../private","crest")'),"");
 for(const name of ["map/six_city_territory_map.png","outcomes/city_victory_background.png","outcomes/city_defeat_background.png"])assert.ok(existsSync(path.join(root,"graphics/art/v290/cities",name)),name);
 for(const id of ["cityMapOverlay","citySelectors","cityWarBanner","territoryDay","cityDistricts","cityMatches","cityStandings","heroBossArt","fitPortrait"])assert.equal([...html.matchAll(new RegExp('id="'+id+'"',"g"))].length,1,id);
});
test("ties stay neutral and historical outcomes remain distinct",()=>{
 assert.equal(run('territoryView(fixture,"Chicago").held.length'),2);
 assert.equal(run('territoryView(fixture,"Chicago").outcome'),"victory");
 assert.equal(run('territoryView(fixture,"Los Angeles").outcome'),"defeat");
 assert.equal(run('territoryView(fixture,"Detroit").outcome'),"neutral");
 assert.equal(run('territoryView(fixture,"Chicago").archived'),true);
 assert.equal(run('territoryView({...fixture,current_day:1},"Chicago").archived'),false);
 assert.equal(run('territoryView({...fixture,matches:[{...fixture.matches[0],duel_owner:"Los Angeles"}]},"Chicago").outcome'),"mixed");
});
test("map adopts Discord landmarks, escapes names and retains score precision",()=>{
 const map=run('mapMarkup(fixture,"Chicago")');
 assert.match(map,/cx="648" cy="255"/);
 assert.match(map,/x1="648" y1="255" x2="240" y2="358"/);
 assert.match(map,/#f07a74/);
 assert.match(run('districtMarkup({kind:"duel",name:"<script>",owner:null,contenders:["Chicago"]})'),/&lt;script&gt;/);
 assert.match(run('districtMarkup({kind:"duel",name:"Tie",owner:null,contenders:["Chicago"]})'),/Neutral/);
 assert.equal(run("cityScore(12345)"),"123.45");
});
