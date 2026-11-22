import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";

const root=new URL("../src/snowfall/platform/static/",import.meta.url);
const script=readFileSync(new URL("app.js",root),"utf8");
function classes(...initial){
 const items=new Set(initial);
 return {add:v=>items.add(v),remove:v=>items.delete(v),contains:v=>items.has(v),
  toggle:(v,force)=>{if(force===undefined)force=!items.has(v);if(force)items.add(v);else items.delete(v);return force;}};
}
function trigger(){
 const attrs=new Map([["aria-expanded","false"]]);
 return {classList:classes(),getAttribute:k=>attrs.get(k),setAttribute:(k,v)=>attrs.set(k,v),
   removeAttribute:k=>attrs.delete(k),focus(){this.focused=true;}};
}
const groups=["combat boss cities","shop activities arcade","wire community staff"].map(routes=>{
 const button=trigger();
 return {dataset:{navGroup:routes},classList:classes(),
  querySelector:sel=>sel===".nav-group-trigger"?button:null,button};
});
const nav={classList:classes("open")};
const toggle=trigger();
toggle.setAttribute("aria-expanded","true");
const doc={
 addEventListener(){},
 getElementById:id=>id==="primaryNav"?nav:id==="menuToggle"?toggle:null,
 querySelectorAll:sel=>sel===".nav-group"?groups:[],
 querySelector:sel=>sel===".nav-group.open .nav-group-trigger"
   ?groups.find(g=>g.classList.contains("open"))?.button||null:null,
};
const context=vm.createContext({document:doc,URL});
vm.runInContext(script,context);
const run=x=>vm.runInContext(x,context);

test("group highlight follows active section without losing route identity",()=>{
 run('reflectNavigationGroup("boss")');
 assert.equal(groups[0].classList.contains("active"),true);
 assert.equal(groups[0].button.classList.contains("active"),true);
 assert.equal(groups[0].button.getAttribute("aria-current"),"true");
 assert.equal(groups[1].classList.contains("active"),false);
 run('reflectNavigationGroup("activities")');
 assert.equal(groups[0].button.getAttribute("aria-current"),undefined);
 assert.equal(groups[1].button.classList.contains("active"),true);
 run('reflectNavigationGroup("community")');
 assert.equal(groups[2].classList.contains("active"),true);
 assert.equal(groups[1].classList.contains("active"),false);
});
test("closing dropdown restores aria state and keyboard focus",()=>{
 groups[1].classList.add("open");
 groups[1].button.setAttribute("aria-expanded","true");
 run('closeNavigationMenus({mobile:false,restoreFocus:true})');
 assert.equal(groups[1].classList.contains("open"),false);
 assert.equal(groups[1].button.getAttribute("aria-expanded"),"false");
 assert.equal(groups[1].button.focused,true);
 assert.equal(nav.classList.contains("open"),true);
});
test("closing mobile menu removes open surfaces and stale expanded state",()=>{
 groups[2].classList.add("open");
 groups[2].button.setAttribute("aria-expanded","true");
 run("closeNavigationMenus()");
 assert.equal(nav.classList.contains("open"),false);
 assert.equal(toggle.getAttribute("aria-expanded"),"false");
 assert.ok(groups.every(g=>g.button.getAttribute("aria-expanded")==="false"));
});
