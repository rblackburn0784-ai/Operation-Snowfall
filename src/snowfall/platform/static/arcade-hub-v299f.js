/* v2.9.9f — Arcade Hub 2.0.
   Lightweight shared launcher for all five interactive web practice games.
   Classic Discord-shared scores and daily starts are a separate section.
   No client-side score claims and no session writes until player clicks Play. */
(function(global){
"use strict";
const MODES=Object.freeze({
 gallery:{icon:"🎯",art:"/art/v290/arcade/gallery.webp",hint:"Aim with mouse or touch"},
 safe:{icon:"🔐",art:"/art/v290/arcade/safe.webp",hint:"Turn the dial in three stages"},
 snowman:{icon:"⛄",art:"/art/v290/arcade/snowman.webp",hint:"Drag parts onto the blueprint"},
 catch:{icon:"❄️",art:"/art/v290/arcade/catch.webp",hint:"Catch falling winter bonuses"},
 trivia:{icon:"🎁",art:"/art/v290/arcade/trivia.webp",hint:"Open gifts and solve word puzzles"},
});
const safe=value=>String(value??"").replace(/[&<>"']/g,ch=>({
 "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;",
}[ch]));
const count=value=>Number.isInteger(value)&&value>=0?value:0;
const clamp=n=>Math.max(0,Math.min(100,Number.isFinite(n)?n:0));
const isMode=m=>m&&Object.hasOwn(MODES,m.key)&&typeof m.name==="string";
const findMode=(hub,key)=>Array.isArray(hub?.modes)?
 hub.modes.find(m=>m.key===key&&isMode(m)):null;
function card(mode,{suggested=null}={}){
 if(!isMode(mode))return "";
 const meta=MODES[mode.key],enabled=mode.enabled===true;
 const resumable=enabled&&mode.can_resume===true&&
  ["active","paused"].includes(mode.status);
 const played=count(mode.finished_runs),best=clamp(mode.personal_best);
 const progress=clamp(mode.progress_percent);
 const action=enabled?(resumable?"Continue game":"Play free"):"Not enabled";
 const recommend=suggested===mode.key;
 const label=(resumable?"Saved game":played>0?"Personal best":"New challenge");
 const description=typeof mode.description==="string"?mode.description:"Winter skill game";
 const skill=typeof mode.skill==="string"?mode.skill:"Skill";
 const duration=typeof mode.duration_label==="string"?mode.duration_label:"Timed";
 const stat=enabled?(played+" practice "+(played===1?"run":"runs")):"QA not activated";
 const progressText=resumable?(mode.progress_label||"Saved session available"):
  played?"Ready for another round":"Your first adventure awaits";
 return "<article class='arcade-hub-card' data-hub-card='"+safe(mode.key)+"' data-state='"+
   (enabled?(resumable?"resume":"ready"):"off")+"'"+
   (recommend?" data-recommended='true'":"")+">"+
  "<div class='arcade-hub-art'><img src='"+meta.art+"' alt='' loading='lazy'>"+
   "<span class='arcade-hub-state'>"+(resumable?"Saved game":enabled?"Unlimited QA":"Locked")+"</span></div>"+
  "<div class='arcade-hub-card-copy'>"+
   "<p class='eyebrow'>"+meta.icon+" "+safe(skill)+" · "+safe(duration)+"</p>"+
   "<h4>"+safe(mode.name)+"</h4><p>"+safe(description)+"</p>"+
   "<p class='arcade-hub-hint'>"+safe(meta.hint)+"</p>"+
   "<div class='arcade-hub-card-stats' aria-label='Your practice records'>"+
    "<span><strong>"+best+"</strong> / 100 best</span>"+
    "<span>"+safe(stat)+"</span></div>"+
   "<div class='arcade-hub-progress'><div class='arcade-hub-progress-head'>"+
    "<span>"+safe(label)+"</span><span>"+safe(progressText)+"</span></div>"+
    "<div class='arcade-hub-track' role='progressbar' aria-label='"+
     safe(mode.name)+" current saved run progress' aria-valuemin='0'"+
     " aria-valuemax='100' aria-valuenow='"+(resumable?progress:0)+"'>"+
     "<span style='width:"+(resumable?progress:0)+"%'></span></div></div>"+
   "<button type='button' class='button "+
    (resumable?"button-gold":"button-outline")+
    "' data-hub-action='launch' data-mode='"+safe(mode.key)+"'"+
    (enabled?"":" disabled aria-disabled='true'")+
    " aria-label='"+safe(action+" "+mode.name)+"'>"+safe(action)+"</button>"+
   "</div></article>";
}
function visibleModes(hub,filter="all",query=""){
 if(!Array.isArray(hub?.modes))return [];
 const normal=String(query||"").toLocaleLowerCase().trim();
 return hub.modes.filter(isMode).filter(mode=>{
  if(filter==="resume"&&!mode.can_resume)return false;
  if(filter==="new"&&(count(mode.finished_runs)>0||!mode.enabled))return false;
  if(filter==="played"&&count(mode.finished_runs)===0)return false;
  return !normal||[
   mode.name,mode.description,mode.skill,MODES[mode.key].hint,
  ].some(s=>String(s||"").toLocaleLowerCase().includes(normal));
 });
}
function renderCards(hub,filter="all",query=""){
 const modes=visibleModes(hub,filter,query);
 if(!modes.length)return "<p class='arcade-hub-empty' role='status'>"+
  "No games match your filters. Try All games or clear the search.</p>";
 return modes.map(mode=>card(mode,{suggested:hub.suggested_mode})).join("");
}
function mount({root,onLaunch,onRefresh,onClassic}){
 if(!root||typeof onLaunch!=="function"||typeof onRefresh!=="function")
  throw Error("Invalid Arcade Hub container");
 let data=null,filter="all",query="",busy=false,loading=false,
     message="Loading your personal arcade…",disposed=false;
 root.classList.remove("hidden");
 root.innerHTML="<div class='arcade-hub-heading'>"+
   "<div><p class='eyebrow'>ARCADE 2.0 · FIVE REAL MINI-GAMES</p>"+
   "<h3>Choose your winter challenge</h3>"+
   "<p>Play the interactive games as much as you like. Practice scores are "+
   "private to this website and never spend your Classic Discord daily starts.</p></div>"+
   "<button type='button' class='button button-outline' data-hub-action='refresh'>"+
   "Refresh practice records</button></div>"+
   "<div class='arcade-hub-summary' data-hub-slot='stats' aria-live='polite'></div>"+
   "<div class='arcade-hub-feature' data-hub-slot='feature'></div>"+
   "<div class='arcade-hub-toolbar'>"+
    "<label for='arcadeHubSearch'>Find a game"+
     "<input type='search' id='arcadeHubSearch' data-hub-search placeholder='Search games or skills' autocomplete='off'></label>"+
    "<label for='arcadeHubFilter'>Show"+
     "<select id='arcadeHubFilter' data-hub-filter>"+
      "<option value='all'>All five games</option>"+
      "<option value='resume'>Continue saved games</option>"+
      "<option value='new'>Not played yet</option>"+
      "<option value='played'>My completed games</option>"+
     "</select></label>"+
    "<span class='arcade-hub-count' data-hub-slot='count' aria-live='polite'>5 games</span>"+
   "</div>"+
   "<div class='arcade-hub-grid' data-hub-slot='cards' aria-live='off'></div>"+
   "<p class='arcade-hub-message' role='status' aria-live='polite' data-hub-slot='message'></p>"+
   "<div class='arcade-hub-classic-link'><div><strong>Looking for the Classic Arcade?</strong>"+
    "<p>Discord-shared three daily starts, stamps, and honorary rankings are still here.</p></div>"+
    "<button class='button button-outline' type='button' data-hub-action='classic'>Open Classic Arcade</button></div>";
 const slot=name=>root.querySelector("[data-hub-slot='"+name+"']");
 const controls=()=>root.querySelectorAll("[data-hub-action]");
 function setBusy(value){
  busy=!!value;
  for(const button of controls())
   if(button.dataset.hubAction!=="classic"&&
       !(button.dataset.hubAction==="launch"&&button.hasAttribute("aria-disabled")))
    button.disabled=busy;
 }
 function draw(){
  if(disposed)return;
  if(!data){
   slot("stats").innerHTML="<span>Five festive games · Unlimited practice</span>";
   slot("feature").innerHTML="";
   slot("cards").innerHTML="";
   slot("count").textContent="5 games";
   slot("message").textContent=message;
   return;
  }
  const available=count(data.available_games),resume=count(data.resumable_games),
        completed=count(data.completed_practice_runs);
  slot("stats").innerHTML=
   "<span><strong>"+available+"/5</strong> games available</span>"+
   "<span><strong>"+resume+"</strong> saved "+(resume===1?"game":"games")+"</span>"+
   "<span><strong>"+completed+"</strong> completed practice runs</span>"+
   "<span class='arcade-hub-stat-free'>✓ 0 competitive starts spent</span>";
  const selected=findMode(data,data.suggested_mode);
  const enabled=selected?.enabled===true;
  if(enabled){
   const continueNow=selected.can_resume===true;
   const head=continueNow?"Pick up where you left off":
    "Your next winter adventure";
   slot("feature").innerHTML="<div class='arcade-hub-spotlight'>"+
    "<div><p class='eyebrow'>"+(continueNow?"SAVE & RESUME":"RECOMMENDED NEXT")+"</p>"+
     "<h4>"+safe(head)+"</h4><p><strong>"+safe(selected.name)+
     "</strong> · "+safe(selected.description)+"</p>"+
    "</div><button type='button' class='button button-gold' data-hub-action='launch'"+
      " data-mode='"+safe(selected.key)+"'>"+
      (continueNow?"Continue game":"Play this game")+"</button></div>";
  }else slot("feature").innerHTML="";
  slot("cards").innerHTML=renderCards(data,filter,query);
  const shown=visibleModes(data,filter,query).length;
  slot("count").textContent=shown+" of 5 games";
  slot("message").textContent=loading?"Updating your saved games…":message;
  setBusy(busy);
 }
 function update(value){
  if(disposed)return;
  if(!value||value.version!=="2.9.9f"||!Array.isArray(value.modes)||
     value.modes.length!==5||new Set(value.modes.map(m=>m.key)).size!==5||
     value.modes.some(m=>!isMode(m)))
   throw Error("Arcade Hub received an unexpected game catalogue");
  data=value;message="Your practice records are up to date.";
  loading=false;draw();
 }
 function setLoading(yes){
  if(disposed)return;loading=!!yes;
  if(!data)message="Loading your personal arcade…";
  draw();
 }
 function setError(error){
  if(disposed)return;loading=false;
  message="Practice hub unavailable: "+String(error?.message||error||"Unknown error")+
   ". Your Classic Arcade is still available below.";
  draw();
 }
 async function trigger(name,mode){
  if(disposed||busy)return;
  if(name==="classic"){onClassic?.();return}
  if(name==="refresh"){
   setBusy(true);
   try{await onRefresh()}
   catch(e){setError(e)}
   finally{setBusy(false)}
   return;
  }
  if(name==="launch"){
   const candidate=findMode(data,mode);
   if(!candidate?.enabled)return;
   setBusy(true);
   try{await onLaunch(mode)}
   catch(e){
    message="Could not launch "+candidate.name+": "+
      String(e?.message||"Please try again.");
    draw();
   }finally{setBusy(false)}
  }
 }
 function click(event){
  const button=event.target.closest("[data-hub-action]");
  if(!button||!root.contains(button)||button.disabled)return;
  void trigger(button.dataset.hubAction,button.dataset.mode);
 }
 function input(event){
  if(event.target.matches("[data-hub-search]")){
   query=String(event.target.value||"").slice(0,80);
   draw();
  }
 }
 function change(event){
  if(event.target.matches("[data-hub-filter]")){
   filter=["all","resume","new","played"].includes(event.target.value)?
    event.target.value:"all";
   draw();
  }
 }
 root.addEventListener("click",click);
 root.addEventListener("input",input);
 root.addEventListener("change",change);
 draw();
 return {
  update,setLoading,setError,
  reset(){
   data=null;message="Sign in to see your arcade progress.";draw();
  },
  dispose(){
   if(disposed)return;disposed=true;
   root.removeEventListener("click",click);
   root.removeEventListener("input",input);
   root.removeEventListener("change",change);
   root.classList.add("hidden");
  },
  getFilter:()=>filter,
 };
}
global.SnowfallArcadeHubV299f=Object.freeze({
 mount,card,renderCards,visibleModes,findMode,MODES,
});
})(window);
