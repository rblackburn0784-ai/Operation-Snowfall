import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";

const dir=fileURLToPath(new URL("../src/snowfall/platform/static/",import.meta.url));
const js=readFileSync(path.join(dir,"app.js"),"utf8");
const css=readFileSync(path.join(dir,"app.css"),"utf8");
const html=readFileSync(path.join(dir,"index.html"),"utf8");

function harness(){
 const elements=new Map();
 let w=320;
 const labels={"hq":"SnowDude","fit":"SnowDude","rival":"TheSnowman"};
 const widths={"hq":320,"fit":320,"rival":180};
 for(const prefix of Object.keys(labels)){
  const style={fontSize:"",overflow:"",transform:""};
  const name={style,textContent:labels[prefix]};
  Object.defineProperty(name,"clientWidth",{get:()=>widths[prefix]});
  Object.defineProperty(name,"scrollWidth",{get:()=>{
   const size=parseFloat(name.style.fontSize)||20;
   return Math.ceil(labels[prefix].length*10.3*size/20);
  }});
  const well={dataset:{banner:"none"},get clientWidth(){return widths[prefix];}};
  elements.set(prefix+"BannerText",name);
  elements.set(prefix+"BannerWell",well);
 }
 const context=vm.createContext({document:{addEventListener(){},getElementById:id=>elements.get(id)||null},
   window:{getComputedStyle:()=>({fontSize:"20px"})},URL,requestAnimationFrame:fn=>fn()});
 vm.runInContext(js,context);
 return {run:s=>vm.runInContext(s,context),elements,widths,labels,setWidth:val=>{w=val}};
}

test("each original banner fits the whole one-line username inside its centre",()=>{
 const h=harness();
 for(const [key,ratio] of [["gilded_banner",.34],["aurora_banner",.37],["midnight_banner",.38]]){
  const well=h.elements.get("fitBannerWell"),node=h.elements.get("fitBannerText");
  well.dataset.banner=key;
  h.run('fitBannerName("fit")');
  const finalSize=parseFloat(node.style.fontSize)||20;
  const scale=node.style.transform?Number(node.style.transform.match(/scaleX\(([^)]+)\)/)?.[1]):1;
  assert.ok(node.scrollWidth*scale<=h.widths.fit*ratio+1.5,key);
  assert.ok(finalSize<=20,key);
  assert.equal(node.style.overflow,"");
 }
});

test("narrow rival stage keeps the entire long name, not a clipped substring",()=>{
 const h=harness();h.widths.rival=90;
 const name=h.elements.get("rivalBannerText"),well=h.elements.get("rivalBannerWell");
 well.dataset.banner="gilded_banner";
 h.run('fitBannerName("rival")');
 assert.equal(name.textContent,"TheSnowman");
 assert.ok(parseFloat(name.style.fontSize)<=8);
 assert.match(name.style.transform,/scaleX\(/);
 const factor=Number(name.style.transform.match(/scaleX\(([^)]+)\)/)[1]);
 assert.ok(factor<1);
 assert.ok(name.scrollWidth*factor<=90*.34+1.3);
});

test("unbannered names retain their normal size, names refit when banner is removed",()=>{
 const h=harness(),well=h.elements.get("hqBannerWell");
 h.widths.hq=160;
 well.dataset.banner="gilded_banner";
 h.run('fitBannerName("hq")');
 assert.notEqual(h.elements.get("hqBannerText").style.fontSize,"");
 well.dataset.banner="none";
 h.run('fitBannerName("hq")');
 assert.equal(h.elements.get("hqBannerText").style.fontSize,"");
 assert.equal(h.elements.get("hqBannerText").style.transform,"");
});

test("scarf is smaller and nearer throat for all original portrait poses",()=>{
 const h=harness();
 const keys=Array.from(h.run("Object.keys(PORTRAIT_FIT)"));
 for(const k of keys){
  const raw=h.run("PORTRAIT_FIT["+JSON.stringify(k)+"].neck");
  for(const framed of [false,true]){
   const fit=h.run("cosmeticPlacement("+JSON.stringify(k)+",'scarf',"+framed+")");
   const inset=framed?10:4,scale=(100-2*inset)/100;
   const oldTop=inset+raw[1]*scale,oldWidth=raw[2]*scale;
   assert.ok(fit.top<oldTop,k);
   assert.ok(fit.width<oldWidth*.81,k);
   assert.ok(fit.width>oldWidth*.74,k);
  }
 }
 assert.match(css,/mask-image:linear-gradient\(to bottom,black/);
 assert.match(css,/\.gear-layer\[data-cosmetic="scarf"\]/);
 assert.match(js,/COSMETIC_ART/);
 assert.match(js,/\/art\/v290\/cosmetics\/gear\/scarf\.png/);
});

test("banner never clips a name and old wardrobe/portrait layer IDs remain",()=>{
 assert.match(css,/\.collector-profile \.collector-banner-name,\s*\.rival-appearance \.collector-banner-name\{/);
 assert.match(css,/width:max-content;max-width:none/);
 assert.match(css,/overflow:visible;text-overflow:initial/);
 assert.match(css,/translate:-50% -50%/);
 for(const p of ["hq","fit","rival"]){
  assert.match(html,new RegExp('id="'+p+'BannerText"'));
  assert.match(html,new RegExp('id="'+p+'PortraitWell"'));
 }
 assert.match(js,/BANNER_NAME_SAFE_WIDTH/);
 assert.match(js,/requestAnimationFrame\(\(\)=>fitBannerName\(prefix\)\)/);
 assert.match(html,/snowfall-web-release" content="2\.9\.8j"/);
 assert.match(html,/app\.css\?v=298j/);
 assert.match(html,/app\.js\?v=298j/);
});
