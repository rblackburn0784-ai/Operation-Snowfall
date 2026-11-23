/* Operation Snowfall v2.9.8l — status and resource artwork integration. */
"use strict";
const S={staffRole:null,staffDirectory:null,staffDossier:null,staffSelected:null,staffDirectoryBusy:false,staffDossierBusy:false,staffReviewBusy:false,staffDirectorySeq:0,staffDossierSeq:0,staffLab:null,staffLabPending:false,staffAllowed:false,staffCheckedIdentity:null,staffAccessCheckedAt:0,staffData:null,staffPending:false,staffStale:false,streetsDrawerOpen:false,streetsReturnFocus:null,streetsEmbedUrl:null,streetsChatOpen:false,community:null,communityPending:false,communityStale:false,privateQueued:false,arcade:null,arcadeRun:null,arcadePractice:null,arcadePracticeRuntime:null,arcadeGallery:null,arcadeGalleryRuntime:null,arcadeSafe:null,arcadeSafeRuntime:null,arcadeSnowman:null,arcadeSnowmanRuntime:null,arcadeCatch:null,arcadeCatchRuntime:null,arcadeTrivia:null,arcadeTriviaRuntime:null,arcadeHub:null,arcadeHubRuntime:null,arcadeHubSeq:0,arcadeEpoch:0,arcadeHubPending:false,arcadeHubError:null,arcadeHubClassicInitialised:false,arcadeBoard:null,arcadeBoardSeq:0,activities:null,session:null,me:null,world:null,raid:null,bossRequest:0,bossPending:false,bossStale:false,hq:null,hqClock:0,shop:null,items:[],catalogReady:false,market:{identity:undefined,featured:0,preview:{},category:'all',ownership:'all',rarity:'all',sort:'catalogue',search:''},board:[],cities:[],citiesReady:false,territory:null,territoryPending:false,territoryStale:false,territoryRequest:0,territoryDay:'current',citySelected:null,wire:null,wireDay:'current',wireRequest:0,wirePending:false,wireStale:false,connection:'loading',targets:[],targetsReady:false,playIdentity:undefined,chosenTarget:false,lastThrow:null,privatePending:false,privateFresh:false,config:null,progress:null,discard:null,verification:null,busy:false,pendingActions:new Map()};
const el=id=>document.getElementById(id);
const txt=(id,v)=>{const node=el(id),value=v==null?"—":String(v);if(node&&node.textContent!==value)node.textContent=value};
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=v=>Number(v??0).toLocaleString("en-GB");
/* v2.9.8l: All thresholds are client-side visual stages. They never influence
   resource caps, regeneration, purchases, score ledger or combat decisions. */
const STATUS_ART_ROOT="/art/v290/status/v298l/";
const STATUS_ART_KINDS=Object.freeze(["snowballs","warmth","cold","currency","points"]);
const COLD_LABELS=Object.freeze(["Comfortable","Chilly","Cold","Freezing"]);
function resourceStage(kind,value){
 if(!STATUS_ART_KINDS.includes(kind)||value==null||value===""||!Number.isFinite(Number(value))||Number(value)<0)return null;
 const amount=Number(value);
 if(kind==="warmth"||kind==="cold")return amount>=75?1:amount>=50?2:amount>=25?3:4;
 if(kind==="snowballs")return amount<=2?1:amount<=5?2:amount<=9?3:4; // actual 0–12 ammo cap
 if(kind==="currency")return amount<=24?1:amount<=74?2:amount<=149?3:4;
 return amount<=99?1:amount<=299?2:amount<=599?3:4;
}
function resourceArtUrl(kind,value,stageKind=kind){
 const stage=resourceStage(stageKind,value);
 return stage===null||!STATUS_ART_KINDS.includes(kind)?null:STATUS_ART_ROOT+kind+"_"+stage+".webp";
}
function paintResourceArt(id,kind,value,stageKind=kind){
 const node=el(id);
 if(!node)return;
 const path=resourceArtUrl(kind,value,stageKind);
 if(!path){
  node.classList?.add("hidden");node.removeAttribute?.("src");
  delete node.dataset.stage;delete node.dataset.empty;
  return;
 }
 if(node.getAttribute?.("src")!==path)node.setAttribute?.("src",path);
 node.classList?.remove("hidden");
 node.dataset.stage=String(resourceStage(stageKind,value));
 node.dataset.empty=kind==="snowballs"&&Number(value)===0?"true":"false";
}
function showResourceArtwork(resources,score){
 const r=resources||{};
 for(const [id,kind,value,stageKind] of [
  ["playAmmoArt","snowballs",r.snowballs],["hqAmmoArt","snowballs",r.snowballs],
  ["alleyAmmoArt","snowballs",r.snowballs],
  ["playWarmthArt","warmth",r.warmth],["hqWarmthArt","warmth",r.warmth],
  ["hqColdArt","cold",r.warmth],["alleyColdArt","cold",r.warmth],
  ["playFlakesArt","currency",r.snowflakes],
  // HQ artwork follows the requested presentation: crystal snowflakes on
  // the left, gold tokens on the right. Stage thresholds still follow the
  // actual snowflake balance and official score respectively.
  ["hqCurrencyArt","points",r.snowflakes,"currency"],
  ["marketCurrencyArt","currency",r.snowflakes],
  ["playPointsArt","points",score],["hqPointsArt","currency",score,"points"]
 ])paintResourceArt(id,kind,value,stageKind);
 const stage=resourceStage("cold",r.warmth),cold=stage===null?"—":COLD_LABELS[stage-1];
 txt("hqColdLabel","Cold status: "+cold);
 txt("alleyColdStatus","Cold status: "+cold);
 txt("alleyAmmoCount",r.snowballs==null?"—":fmt(r.snowballs));
 txt("alleyWarmthCount",r.warmth==null?"Warmth — / 100":"Warmth "+fmt(r.warmth)+" / 100");
}
const CITY_SLUG=Object.freeze({
 "Chicago":"chicago","Detroit":"detroit","Las Vegas":"las_vegas",
 "Los Angeles":"los_angeles","New York":"new_york","Philadelphia":"philadelphia"
});
const COSMETIC_ART=Object.freeze({
 "ice_frame":"/art/v290/cosmetics/frames/ice_frame.png",
 "gold_frame":"/art/v290/cosmetics/frames/gold_frame.png",
 "holly_frame":"/art/v290/cosmetics/frames/holly_frame.png",
 "snow_trail":"/art/v290/cosmetics/trails/snow_trail.png",
 "candy_trail":"/art/v290/cosmetics/trails/candy_trail.png",
 "goggles":"/art/v290/cosmetics/gear/goggles.png",
 "boots":"/art/v290/cosmetics/gear/boots.png",
 "scarf":"/art/v290/cosmetics/gear/scarf.png",
 "midnight_banner":"/art/v290/cosmetics/banners/midnight_banner.png",
 "aurora_banner":"/art/v290/cosmetics/banners/aurora_banner.png",
 "gilded_banner":"/art/v290/cosmetics/banners/gilded_banner.png",
 "noir_detective":"/art/v290/portraits/noir_detective_m.webp",
 "winter_enforcer":"/art/v290/portraits/winter_enforcer_m.webp",
 "frost_spectre":"/art/v290/portraits/frost_spectre_m.webp",
 "recruit_f":"/art/v290/portraits/recruit_f.webp",
 "noir_detective_f":"/art/v290/portraits/noir_detective_f.webp",
 "winter_enforcer_f":"/art/v290/portraits/winter_enforcer_f.webp",
 "frost_spectre_f":"/art/v290/portraits/frost_spectre_f.webp"
});
// Product thumbnails and featured Market art continue to use COSMETIC_ART.
 // The equipped avatar/fitting-room illustration uses the player's supplied
 // transparent neck-wrapped design. Both map to the same existing cosmetic key.
const WORN_COSMETIC_ART=Object.freeze({
 "scarf":"/art/v290/cosmetics/gear/scarf_worn.png"
});
function wornCosmeticArt(key){return WORN_COSMETIC_ART[key]||COSMETIC_ART[key]||null}
const HQ_SLOTS=Object.freeze({
 portrait:["noir_detective","winter_enforcer","frost_spectre","recruit_f","noir_detective_f","winter_enforcer_f","frost_spectre_f"],
 frame:["ice_frame","gold_frame","holly_frame"],
 banner:["midnight_banner","aurora_banner","gilded_banner"],
 gear:["goggles","boots","scarf"],
 trail:["snow_trail","candy_trail"]
});
function ownedEquipped(wardrobe,slot){
 const key=wardrobe?.equipped?.[slot];
 return Array.isArray(wardrobe?.unlocked)&&wardrobe.unlocked.includes(key)&&
     HQ_SLOTS[slot]?.includes(key)?key:null;
}
function profileLayers(wardrobe){
 const layers={};
 for(const slot of Object.keys(HQ_SLOTS)){
  const key=ownedEquipped(wardrobe,slot);
  layers[slot]={key,src:key?wornCosmeticArt(key):slot==="portrait"?"/art/v290/portraits/recruit_m.webp":null};
 }
 return layers;
}
const MARKET_TRAIL_NAMES=Object.freeze({snow_trail:"Snowstorm Trail",candy_trail:"Candy Cane Trail"});
function cosmeticName(key){return S.items.find(item=>item.key===key)?.name||
    MARKET_TRAIL_NAMES[key]||(key?key.split("_").map(word=>word[0].toUpperCase()+word.slice(1)).join(" "):"None");}
// Portrait landmarks measured on the original 530 × 549 artwork.
 // Coordinates use the square cover crop (9.5 source pixels removed top/bottom).
const PORTRAIT_FIT=Object.freeze({
 recruit:{eyes:[53.2,22.9,34,9],neck:[50.5,39.7,40]},
 recruit_f:{eyes:[55.8,24.4,32,5],neck:[51.8,45,38]},
 noir_detective:{eyes:[54,22.1,34,10],neck:[51.3,39.5,40]},
 noir_detective_f:{eyes:[55.5,24,32,1],neck:[51.5,43.8,38]},
 winter_enforcer:{eyes:[53.6,19.4,36,7],neck:[50.5,35.3,43]},
 winter_enforcer_f:{eyes:[55,23,33,6],neck:[51.7,41.2,39]},
 frost_spectre:{eyes:[54,22.3,34,11],neck:[51.7,39,40]},
 frost_spectre_f:{eyes:[55.7,24.6,32,5],neck:[52.2,44.1,38]}
});
function cosmeticPlacement(portrait,gear,framed){
 const p=Object.hasOwn(PORTRAIT_FIT,portrait)?PORTRAIT_FIT[portrait]:PORTRAIT_FIT.recruit;
 // Keep faces, gear and trails aligned after reducing the portrait size inside
 // the original frame artwork. These proportions match CSS portrait insets.
 const inset=framed?10:4,scale=(100-2*inset)/100;
 const point=n=>+(inset+n*scale).toFixed(3),size=n=>+(n*scale).toFixed(3);
 const [ex,ey,ew,angle]=p.eyes,[nx,ny,nw]=p.neck;
 if(gear==="goggles")return {left:point(ex),top:point(ey),width:size(ew),transform:"translate(-50%,-49%) rotate("+angle+"deg)"};
 // The worn scarf is tightly cropped transparent art with an opening for the
 // neck. Its top edge starts just below the chin; the hanging tails follow the
 // coat naturally. Catalogue images never use this transform.
 if(gear==="scarf")return {left:point(nx),top:point(ny+3.5),width:size(nw*.9),transform:"translateX(-50%)"};
 if(gear==="boots")return {left:point(7),top:point(67),width:size(26),transform:"none"};
 if(gear==="snow_trail"||gear==="candy_trail")return {left:point(66),top:point(61),width:size(30),transform:"none"};
 return null;
}
function alignProfileLayer(node,placement){
 for(const prop of ["left","top","width"])node.style[prop]=placement?placement[prop]+"%":"";
 node.style.height=placement?"auto":"";
 node.style.transform=placement?placement.transform:"";
}
/* The decorated edges of Market banners are not usable writing space.
   These ratios describe their central ribbon, NOT the full PNG bounding box. */
const BANNER_NAME_SAFE_WIDTH=Object.freeze({
 none:.94,midnight_banner:.38,aurora_banner:.37,gilded_banner:.34
});
function fitBannerName(prefix){
 const node=el(prefix+"BannerText"),well=el(prefix+"BannerWell");
 if(!node?.style)return;
 // Never use overflow clipping: it used to silently erase the end of names.
 node.style.fontSize="";
 node.style.overflow="";
 node.style.transform="";
 const banner=well?.dataset?.banner||"none";
 const ratio=BANNER_NAME_SAFE_WIDTH[banner]||BANNER_NAME_SAFE_WIDTH.none;
 const containerWidth=well?.clientWidth||0;
 const available=containerWidth>0?containerWidth*ratio:node.clientWidth||0;
 if(typeof window==="undefined"||typeof window.getComputedStyle!=="function"||
     !Number.isFinite(available)||available<=0)return;
 let size=parseFloat(window.getComputedStyle(node).fontSize);
 if(!Number.isFinite(size)||size<=0)return;
 for(let pass=0;pass<8&&node.scrollWidth>available+.5;pass++){
  const smaller=Math.max(8,size*Math.min(.98,available/node.scrollWidth)*.975);
  if(smaller>=size-.01)break;
  size=smaller;
  node.style.fontSize=size.toFixed(2)+"px";
 }
 // Long character names remain whole and centred even at narrow widths.
 if(node.scrollWidth>available+.5){
  node.style.transform="scaleX("+Math.max(.15,available/node.scrollWidth*.98).toFixed(3)+")";
 }
}
function fitVisibleBannerNames(){
 for(const name of ["hq","fit","rival"])fitBannerName(name);
}
function renderProfileLayers(prefix,layers,displayName="Winter player"){
 const framed=!!layers.frame.key,portrait=layers.portrait.key||"recruit";
 const well=el(prefix+"PortraitWell"),bannerWell=el(prefix+"BannerWell");
 if(!well||!bannerWell)return;
 well.classList.toggle("has-frame",framed);well.dataset.portrait=portrait;
 well.dataset.trail=layers.trail.key||"none";
 bannerWell.classList.remove("hidden");
 bannerWell.classList.toggle("has-banner",!!layers.banner.key);
 bannerWell.dataset.banner=layers.banner.key||"none";
 txt(prefix+"BannerText",displayName);
 fitBannerName(prefix);
 // Layout may not have settled yet when switching tabs or the Market preview;
 // follow up in the next animation frame using the actual available width.
 if(typeof requestAnimationFrame==="function"){
  requestAnimationFrame(()=>fitBannerName(prefix));
 }
 for(const slot of Object.keys(layers)){
  const id=slot[0].toUpperCase()+slot.slice(1),node=el(prefix+id),layer=layers[slot];
  if(!node)continue;
  if(layer.src){
   if(node.getAttribute("src")!==layer.src)node.setAttribute("src",layer.src);
   node.classList.remove("hidden");
  }else{node.classList.add("hidden");node.removeAttribute("src")}
  node.dataset.cosmetic=layer.key||"";
  if(slot==="gear"||slot==="trail")alignProfileLayer(node,cosmeticPlacement(portrait,layer.key,framed));
  const name=layer.key?cosmeticName(layer.key):slot==="portrait"?"Recruit":"None";
  if(slot==="portrait")node.alt=displayName+" · "+name+" profile";
  txt(prefix+id+"Name",name);
 }
}
function showWardrobe(){
 const wardrobe=S.session&&S.me?.registered?S.shop:null;
 renderProfileLayers("hq",profileLayers(wardrobe),wardrobe?S.me?.mr_username||"Your character":"Your character");
 txt("hqWardrobeStatus",wardrobe?
     fmt(wardrobe.unlocked?.length||0)+" cosmetics owned · shared with Discord":
     "Wardrobe not loaded — refresh to check equipped cosmetics.");
}

/* PvP preview uses the eligible rival's server-supplied equipped items, never
   the viewer's wardrobe or client-side Market try-on selections. */
function rivalWardrobe(appearance){
 const equipped={},unlocked=[];
 if(appearance&&typeof appearance==="object"&&!Array.isArray(appearance)){
  for(const slot of Object.keys(HQ_SLOTS)){
   const key=appearance[slot];
   if(HQ_SLOTS[slot].includes(key)&&Object.hasOwn(COSMETIC_ART,key)){
    equipped[slot]=key;unlocked.push(key);
   }
  }
 }
 return {unlocked,equipped};
}
function showRivalAppearance(selected){
 if(!el("rivalAppearance"))return;
 el("rivalAppearance").classList.toggle("hidden",!selected);
 el("rivalEmpty")?.classList.toggle("hidden",!!selected);
 if(!selected)return;
 const wardrobe=rivalWardrobe(selected.appearance),layers=profileLayers(wardrobe);
 renderProfileLayers("rival",layers,selected.mr_username);
 const equipped=Object.values(layers).filter(layer=>layer.key).map(layer=>cosmeticName(layer.key));
 txt("rivalVisualStatus",equipped.length
  ?"Equipped: "+equipped.join(" · "):"Default recruit outfit · no equipped cosmetics");
}
const THROW_STYLE_NAMES=Object.freeze({quick:"Quick Shot",standard:"Standard Throw",power:"Power Shot",golden:"Golden Snowball"});
function showSnowballLoadout(style){
 const well=el("alleyLoadoutIcon");
 if(!well)return;
 const trail=S.session&&S.me?.registered?ownedEquipped(S.shop,"trail"):null;
 const title=Object.hasOwn(THROW_STYLE_NAMES,style)?THROW_STYLE_NAMES[style]:THROW_STYLE_NAMES.standard;
 well.dataset.trail=trail||"none";
 well.dataset.style=style||"standard";
 const trailArt=el("alleyLoadoutTrail");
 if(trailArt){
  trailArt.classList.toggle("hidden",!trail);
  if(trail)trailArt.setAttribute("src",COSMETIC_ART[trail]);
  else trailArt.removeAttribute("src");
 }
 txt("alleyLoadoutName","Your snowball · "+title);
 const addon=trail?cosmeticName(trail)+" equipped from Winter Market":
    S.shop?"Default snowball · equip a Snowstorm or Candy Cane Trail in Winter Market":
    "Equip a Snowstorm or Candy Cane Trail in Winter Market";
 const golden=style==="golden"&&Number(S.progress?.inventory?.golden||0)<1;
 txt("alleyLoadoutDetail",addon+(golden?" · Golden Snowball required in inventory":""));
}
const MEDALS=Object.freeze(["first_flurry","deadeye","rival_hunter","critical_ace","knockout_artist","don_destroyer","boss_regular","fort_breaker","quest_master","gift_collector","golden_legend","seven_days","cocoa_club","first_style","collector","full_outfit"]);
const RARITIES=["Common","Rare","Epic","Legendary"];
function hqPercent(value,cap){
 if(value==null||!(Number(cap)>0)||!Number.isFinite(Number(value)))return 0;
 return Math.min(100,Math.max(0,Number(value)*100/Number(cap)));
}
function hqTimer(value,phase,now){
 if(phase==="paused")return "Paused";
 if(phase!=="live"||!value)return "—";
 const until=Date.parse(value);
 if(!Number.isFinite(until))return "—";
 const seconds=Math.ceil((until-now)/1000);
 if(seconds<=0)return "Refresh due";
 const d=Math.floor(seconds/86400),h=Math.floor(seconds/3600)%24,m=Math.floor(seconds/60)%60,s=seconds%60;
 return (d?d+"d ":"")+(d||h?h+"h ":"")+String(m).padStart(2,"0")+"m "+String(s).padStart(2,"0")+"s";
}
function updateHqTimers(){
 if(!S.session||!S.hq?.registered)return;
 const now=Date.now()+S.hqClock;
 for(const key of ["snowball","warmth","throw","reset","knockout","shield"])
  txt("hqTimer"+key[0].toUpperCase()+key.slice(1),hqTimer(S.hq.timers?.[key],S.hq.phase,now));
 if(S.hq.timers?.arena&&S.hq.phase==="live")
  txt("hqArenaState",Date.parse(S.hq.timers.arena)>now?"Arena active · "+hqTimer(S.hq.timers.arena,S.hq.phase,now):"Arena status expired · refresh");
}
function hqMedal(t,featured=false){
 if(!MEDALS.includes(t.key))return "";
 const rarity=RARITIES.includes(t.rarity)?t.rarity:"Common",earned=t.unlocked===true;
 return "<article class='hq-medal "+(earned?"earned":"locked")+"' data-rarity='"+rarity+"'>"+
 "<img loading='lazy' src='/art/v290/trophies/medals/"+t.key+".png' alt=''>"+
 "<div><strong>"+esc(t.badge)+"</strong><small>"+esc(rarity)+" · "+(earned?"Earned":"Locked")+"</small>"+
 (featured?"":"<p>"+esc(t.description)+"</p><div class='hq-meter'><span style='width:"+hqPercent(t.progress,t.target)+"%'></span></div><small>"+fmt(t.progress)+" / "+fmt(t.target)+"</small>")+"</div></article>";
}
function showHq(){
 const h=S.session&&S.me?.registered&&S.hq?.registered?S.hq:null;
 const quests=h&&Array.isArray(h.quests)?h.quests:[],trophies=h&&Array.isArray(h.trophies)?h.trophies.filter(t=>MEDALS.includes(t.key)):[];
 const earned=trophies.filter(t=>t.unlocked===true);
 const rarity=h&&RARITIES.includes(h.rarity)?h.rarity:"Common";
 el("hqCollector").dataset.rarity=rarity;
 txt("hqPlayerTitle",h?.title||"Title unavailable");
 txt("hqRarity",h?rarity+" style":"Style unavailable");
 txt("hqRank",h?.rank!=null?"#"+fmt(h.rank):"—");
 txt("hqDailyPoints",h?.daily_points==null?"—":fmt(h.daily_points));
 txt("hqPhase",S.me?.phase?String(S.me.phase).toUpperCase()+" · "+(S.me.day?"Day "+S.me.day+" of 7":"Awaiting event"):"Awaiting event");
 const cap=h?.caps||{};
 el("hqAmmoMeter").style.width=hqPercent(S.me?.resources?.snowballs,cap.snowballs)+"%";
 el("hqWarmthMeter").style.width=hqPercent(S.me?.resources?.warmth,cap.warmth)+"%";
 el("hqPvpMeter").style.width=hqPercent(h?.today_pvp,cap.pvp)+"%";
 txt("hqPvpValue",h?.today_pvp!=null?fmt(h.today_pvp)+" / "+fmt(cap.pvp)+" pts":"—");
 txt("hqArenaState",!h?"Arena status unavailable":h.phase==="paused"?"Event paused":h.phase!=="live"?"Arena not open":h.timers?.arena?"Checking arena timer…":"Arena inactive — enter Snowball Alley");
 for(const key of ["snowball","warmth","throw","reset","knockout","shield"])
  txt("hqTimer"+key[0].toUpperCase()+key.slice(1),"—");
 if(h)updateHqTimers();
 const recommendation=el("hqRecommended");
 const routes={world:["boss","Open raid"],fight:["combat","Find rivals"],player:["combat","Enter arena"],rankings:["cities","View standings"],quests:["missions","View assignments"],arcade:["arcade","Open Winter Arcade"]};
 const next=h?routes[h.next_action_route]:null;
 recommendation.classList.toggle("hidden",!next);
 recommendation.dataset.destination=next?.[0]||"";
 recommendation.textContent=next?.[1]||"Open";
 if(h)txt("hqNextMove",h.next_action+(["guide"].includes(h.next_action_route)?" See Discord for this feature.":""));
 txt("hqQuestCount",h?quests.filter(q=>q.claimed).length+" / "+quests.length+" claimed":"Unavailable");
 el("hqQuestList").innerHTML=quests.length?quests.map(q=>"<article class='hq-quest'><strong>"+esc(q.name)+"</strong><span>"+(q.claimed?"Claimed":Number(q.progress)>=Number(q.target)?"Ready to claim":"In progress")+"</span><div class='hq-meter'><span style='width:"+hqPercent(q.progress,q.target)+"%'></span></div><small>"+fmt(q.progress)+" / "+fmt(q.target)+"</small></article>").join(""):"<p class='subtle'>"+(h?"No daily assignments are available.":"Refresh to load your assignments.")+"</p>";
 txt("hqGiftStatus",h?"Daily gift: "+h.daily_gift+" · Bonus: "+h.bonus_gift+" · Open gifts in Winter Activities.":"Gift status unavailable.");
 txt("hqTrophyCount",h?earned.length+" / "+trophies.length+" collected":"Achievements unavailable — refresh to retry.");
 el("hqTrophyGrid").innerHTML=trophies.map(t=>hqMedal(t)).join("");
 el("hqFeatured").innerHTML=earned.slice().sort((a,b)=>(Number(b.title===h.title)-Number(a.title===h.title))||RARITIES.indexOf(b.rarity)-RARITIES.indexOf(a.rarity)||String(a.badge).localeCompare(String(b.badge))).slice(0,3).map(t=>hqMedal(t,true)).join("");
 const records=[["PvP throws","pvp_throws"],["PvP accuracy","accuracy"],["Critical hits","critical_hits"],["Knockouts","knockouts"],["Best hit","best_hit"],["Boss damage","boss_damage"],["Siege damage","siege_damage"],["Active days","active_days"]];
 el("hqRecordGrid").innerHTML=records.map(([label,key])=>"<div><small>"+label+"</small><strong>"+(h?.records?.[key]==null?"—":fmt(h.records[key])+(key==="accuracy"?"%":""))+"</strong></div>").join("");
}
function configureBranding(branding){
 const banner=el("siteBanner"),icon=el("brandIcon");
 const header=banner.closest(".topbar");
 header?.classList.toggle("has-city-header",Boolean(branding?.city_header));
 header?.classList.toggle("has-city-title",Boolean(branding?.title));
 document.body.classList.toggle("has-city-wallpaper",Boolean(branding?.wallpaper));
 el("wirePaper")?.classList.toggle("has-wire-template",Boolean(branding?.wire_template));
 if(branding?.title||branding?.banner){
  banner.onerror=()=>{banner.classList.add("hidden");el("bannerFallback").classList.remove("hidden")};
  banner.src=branding?.title?"/static/snowfall-title.png?v=297a":"/static/snowfall-site-banner.webp";
  banner.classList.remove("hidden");el("bannerFallback").classList.add("hidden");
 }
 if(branding?.icon){
  icon.onerror=()=>{icon.classList.add("hidden");el("brandFallback").classList.remove("hidden")};
  icon.src="/static/snowfall-site-icon.webp";
  icon.classList.remove("hidden");el("brandFallback").classList.add("hidden");
 }
}
function bossArtTier(hp,max){
 if(!(Number(max)>0))return 100;
 if(Number(hp)<=0)return 0;
 const maximum=Math.trunc(Number(max)),remaining=Math.max(0,Math.min(Math.trunc(Number(hp)),maximum));
 return Math.max(10,Math.floor((remaining*10+maximum-1)/maximum)*10);
}
function safeStreetsUrl(value){
 if(typeof value!=="string")return "";
 try{
  const url=new URL(value);
  if(url.protocol==="https:" && url.host==="discord.com" && !url.search && !url.hash &&
      /^\/channels\/\d{15,25}\/\d{15,25}$/.test(url.pathname))return url.href;
 }catch{}
 return "";
}
function configureStreets(value){
 const url=safeStreetsUrl(value);
 for(const id of ["communityStreetsLink"]){
  const link=el(id);if(!link)continue;
  link.classList.toggle("hidden",!url);
  if(url)link.href=url;else link.removeAttribute("href");
 }
 el("communityStreetsUnavailable")?.classList.toggle("hidden",!!url);
 S.streetsEmbedUrl=streetsEmbedUrl(url);
 updateStreetsChat();
}

function streetsEmbedUrl(channelUrl){
 const valid=safeStreetsUrl(channelUrl);
 if(!valid)return "";
 const p=new URL(valid).pathname;
 return "https://e.widgetbot.io"+p;
}
function updateStreetsChat(){
 const frame=el("streetsChatFrame"),embed=el("streetsChatEmbed"),button=el("streetsChatEnable");
 if(!frame||!embed||!button)return;
 const eligible=!!(S.session&&S.me?.registered&&hasPlayIdentity(S.session,S.config));
 const configured=!!S.streetsEmbedUrl;
 if(!eligible||!configured){
   S.streetsChatOpen=false;
   frame.removeAttribute("src");
   embed.classList.add("hidden");
 }
 button.disabled=!configured;
 button.textContent=!S.session?"Sign in to enter chat":!hasPlayIdentity(S.session,S.config)?"Connect Underworld":!S.me?.registered?"Go to Headquarters":"Enter The Streets chat";
 button.classList.toggle("hidden",S.streetsChatOpen&&eligible);
 el("streetsChatDisconnect")?.classList.toggle("hidden",!S.streetsChatOpen);
 txt("streetsChatStatus",!configured?"The Discord channel isn't configured yet.":!S.session?"Sign in through Underworld to enter chat.":!eligible?"Register your character in Headquarters before joining.":S.streetsChatOpen?"Chat is open below. Discord members and website visitors can message in the same room.":"Enter chat to connect to WidgetBot. Messages stay here in the Snowfall page.");
}
function openStreetsChat(){
 updateStreetsChat();
 if(!S.streetsEmbedUrl)return;
 if(!S.session){closeStreetsDock(false);authModal();return}
 if(!hasPlayIdentity(S.session,S.config)){
  closeStreetsDock(false);section("home");el("accountTools").open=true;
  notice("Return through Underworld to use your character.","error");return;
 }
 if(!S.me?.registered){
  closeStreetsDock(false);section("home");notice("Register your character at Headquarters to join chat.","error");return;
 }
 const frame=el("streetsChatFrame");
 if(!S.streetsChatOpen){
   frame.src=S.streetsEmbedUrl;
   S.streetsChatOpen=true;
 }
 el("streetsChatEmbed").classList.remove("hidden");
 updateStreetsChat();
}
function closeStreetsDock(restoreFocus=true){
 if(!S.streetsDrawerOpen)return;
 S.streetsDrawerOpen=false;
 el("streetsChatDock")?.classList.remove("drawer-open");
 el("streetsChatBackdrop")?.classList.add("hidden");
 document.body.classList.remove("streets-drawer-open");
 el("streetsChatLauncher")?.setAttribute("aria-expanded","false");
 if(restoreFocus&&S.streetsReturnFocus?.isConnected)S.streetsReturnFocus.focus({preventScroll:true});
 S.streetsReturnFocus=null;
 // Keep the iframe mounted: closing the mobile drawer is NOT a logout.
}
function openStreetsDock(){
 const dock=el("streetsChatDock");
 if(!dock)return;
 if(window.matchMedia("(max-width:980px)").matches){
  S.streetsReturnFocus=document.activeElement;
  S.streetsDrawerOpen=true;
  dock.classList.add("drawer-open");
  el("streetsChatBackdrop").classList.remove("hidden");
  document.body.classList.add("streets-drawer-open");
  el("streetsChatLauncher").setAttribute("aria-expanded","true");
  el("streetsChatClose").focus({preventScroll:true});
 }else{
  dock.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
 }
 // The player's explicit click authorizes the opt-in chat connection.
 if(S.streetsEmbedUrl&&S.session&&S.me?.registered&&hasPlayIdentity(S.session,S.config))openStreetsChat();
 else updateStreetsChat();
}
function disconnectStreetsChat(){
 const frame=el("streetsChatFrame");
 if(frame)frame.removeAttribute("src");
 S.streetsChatOpen=false;
 el("streetsChatEmbed")?.classList.add("hidden");
 updateStreetsChat();
}
let timer;
function notice(message,kind){
 const node=el("toast");node.textContent=String(message);node.className="toast "+(kind||"");
 clearTimeout(timer);timer=setTimeout(()=>node.classList.add("hidden"),5500);
}
function requestKey(path,body){
 // Stable within the current authenticated character for identical inputs.
 return String(S.session?.player_id||"guest")+"|"+path+"|"+JSON.stringify(body??{});
}
function nextActionId(){
 return "web-ui-"+(crypto.randomUUID?crypto.randomUUID():
        String(Date.now())+"-"+Math.random()).replace(/[^A-Za-z0-9_-]/g,"");
}
// Store only pending operation keys and their opaque IDs in this browser tab.
 // No passwords, session cookies, CSRF values or names are persisted.
const RECOVERABLE_ACTIONS=new Set(["/v1/game/throw","/v1/game/boss","/v1/game/siege","/v1/game/craft","/v1/game/wardrobe/purchase","/v1/game/activities/action","/v1/game/arcade/move","/v1/game/arcade/gallery/shot","/v1/game/arcade/safecracker/move","/v1/game/arcade/snowman/place","/v1/game/arcade/catch/update","/v1/game/arcade/trivia/answer"]);
function pendingStoreKey(){
 const id=String(S.session?.player_id||"");
 return /^[1-9][0-9]{0,18}$/.test(id)?"snowfall-pending-v1:"+String(S.config?.season||"qa")+":"+id:null;
}
function savePending(){
 const storage=pendingStoreKey();if(!storage)return;
 const prefix=String(S.session.player_id)+"|";
 const entries=Array.from(S.pendingActions).filter(([k])=>k.startsWith(prefix)).slice(0,32);
 try{if(entries.length)sessionStorage.setItem(storage,JSON.stringify(entries));else sessionStorage.removeItem(storage)}catch{}
}
function restorePending(){
 const storage=pendingStoreKey();if(!storage)return;
 const prefix=String(S.session.player_id)+"|";
 try{
  const entries=JSON.parse(sessionStorage.getItem(storage)||"[]");
  if(!Array.isArray(entries))return;
  for(const entry of entries.slice(0,32)){
   if(!Array.isArray(entry)||entry.length!==2)continue;
   const [key,id]=entry;
   if(typeof key!=="string"||!key.startsWith(prefix)||key.length>350||typeof id!=="string"||!/^[A-Za-z0-9_-]{12,100}$/.test(id))continue;
   const split=key.indexOf("|",prefix.length),path=key.slice(prefix.length,split);
   if(!RECOVERABLE_ACTIONS.has(path))continue;
   const body=JSON.parse(key.slice(split+1));
   if(!body||Array.isArray(body)||typeof body!=="object")continue;
   S.pendingActions.set(key,id);
   if(path==="/v1/game/throw"&&/^[1-9][0-9]{0,18}$/.test(body.target_player_id)&&["quick","standard","power","golden"].includes(body.style))S.lastThrow={body:{target_player_id:body.target_player_id,style:body.style}};
  }
 }catch{}
}
function clearPending(key){S.pendingActions.delete(key);savePending()}
function uncertainResponse(action=true){const err=Error(action?"Connection interrupted. Your action may have succeeded. Check shared progress, then retry the same action safely.":"Connection interrupted. Refresh to load the latest game data.");err.status=0;return err}
async function request(path,method,body,mutation,unique){
 const headers={"Accept":"application/json"};
 if(body!==undefined)headers["Content-Type"]="application/json";
 if(mutation)headers["X-Snowfall-CSRF"]=S.session?.csrf||"";
 if(S.session?.player_id&&path!=="/v1/auth/session"&&(mutation||path.startsWith("/v1/game/")||path.startsWith("/v1/verification/")))headers["X-Snowfall-Player"]=String(S.session.player_id);
 const key=unique?requestKey(path,body):null;
 if(key){
  if(!S.pendingActions.has(key)){
   if(S.pendingActions.size>=32)throw Error("Resolve earlier unconfirmed actions before starting another.");
   S.pendingActions.set(key,nextActionId());savePending();
  }
  headers["Idempotency-Key"]=S.pendingActions.get(key);
 }
 const abort=new AbortController();
 const clock=setTimeout(()=>abort.abort(),15000);
 let response,data,decoded=false;
 try{
  response=await fetch(path,{
   method:method||"GET",headers,credentials:"same-origin",cache:"no-store",
   body:body===undefined?undefined:JSON.stringify(body),signal:abort.signal
  });
  try{data=await response.json();decoded=data!==null&&typeof data==="object"&&!Array.isArray(data)}catch{}
 }catch{throw uncertainResponse(!!mutation||!!unique)}
 finally{clearTimeout(clock)}
 if(response.ok&&!decoded)throw uncertainResponse(!!mutation||!!unique);
 if(!response.ok){
  // A proxy/timeout/auth failure does not establish whether a prior
  // attempt committed. Only explicit game validation rejections end it.
  if(key&&decoded&&[400,409,422].includes(response.status)&&data.detail!=="Account changed in another tab; sign in again")clearPending(key);
  data=decoded?data:{};
  let err=Error(typeof data.detail==="string"?data.detail:
      "Request failed ("+response.status+")");
  err.status=response.status;
  if(response.status>=500||response.status===408||response.status===429)err.message+=". Status uncertain — check progress before retrying.";
  throw err;
 }
 if(key)clearPending(key);
 return data;
}
const get=path=>request(path);
const post=(path,body,mutate,unique)=>request(path,"POST",body,mutate,unique);
/* One menu controller for desktop dropdowns, mobile accordions and keyboard access. */
function closeNavigationMenus({mobile=true,restoreFocus=false}={}){
 const opened=document.querySelector(".nav-group.open .nav-group-trigger");
 const mobileWasOpen=mobile&&el("primaryNav")?.classList.contains("open");
 for(const group of document.querySelectorAll(".nav-group")){
  group.classList.remove("open");
  group.querySelector(".nav-group-trigger")?.setAttribute("aria-expanded","false");
 }
 if(mobile){
  el("primaryNav")?.classList.remove("open");
  el("menuToggle")?.setAttribute("aria-expanded","false");
 }
 if(restoreFocus){
  if(mobileWasOpen)el("menuToggle")?.focus();
  else if(opened)opened.focus();
  else if(mobile)el("menuToggle")?.focus();
 }
}
function reflectNavigationGroup(name){
 for(const group of document.querySelectorAll(".nav-group")){
  const active=(group.dataset.navGroup||"").split(" ").includes(name);
  const trigger=group.querySelector(".nav-group-trigger");
  group.classList.toggle("active",active);
  if(trigger){
   trigger.classList.toggle("active",active);
   if(active)trigger.setAttribute("aria-current","true");
   else trigger.removeAttribute("aria-current");
  }
 }
}
function section(name,{record=true,focus=true}={}){
 if(!["home","combat","boss","shop","cities","wire","activities","arcade","community","staff"].includes(name))name="home";
 if(name==="staff"&&S.staffAllowed!==true)name="home";
 document.querySelectorAll(".panel").forEach(n=>n.classList.toggle("active",n.id==="page-"+name));
 document.querySelectorAll(".nav-item").forEach(n=>{
  const active=n.dataset.nav===name;
  n.classList.toggle("active",active);
  n.setAttribute("aria-pressed",String(active));
 });
 closeNavigationMenus();
 reflectNavigationGroup(name);
 if(name==="staff"){void refreshStaffDashboard();void refreshStaffLab();void refreshStaffDirectory(1)}
 if(name!=="arcade"&&S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(name!=="arcade"&&S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(name!=="arcade"&&S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(name!=="arcade"&&S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(name!=="arcade"&&S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 if(name!=="arcade"&&S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 if(name==="shop")showShop();
 if(name==="community"){updateStreetsChat();showCommunity();void refreshCommunity()}
 if(name==="arcade"){showArcade();if(S.session){if(S.busy||S.privatePending)S.privateQueued=true;else void loadPrivate().catch(e=>notice(e.message,"error"))}}
 if(name==="activities"){showActivities();if(S.session){if(S.busy||S.privatePending)S.privateQueued=true;else void loadPrivate().catch(e=>notice(e.message,"error"))}}
 if(name==="cities"){showCities();showBoard();if(!S.territoryPending&&!S.busy)void refreshTerritory();if(S.session&&!S.privatePending&&!S.busy)void loadPrivate().catch(e=>notice(e.message,"error"))}
 if(name==="boss"){showBoss();if(!S.bossPending&&!S.busy)void refreshBossVisual()}
 if(name==="wire"){showWire();if(!S.wirePending&&!S.busy)void refreshWire()}
 if(record&&location.hash!=="#play-"+name)history.pushState(null,"",location.pathname+location.search+"#play-"+name);
 const heading=document.querySelector("#page-"+name+" h2");
 if(focus&&heading){heading.tabIndex=-1;heading.focus({preventScroll:true})}
 document.querySelector(".page-grid").scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
 updatePlayControls();
 if(typeof requestAnimationFrame==="function")requestAnimationFrame(fitVisibleBannerNames);
}
let authReturnFocus=null;
function authModal(){
 if(S.session)return notice("Already signed in.","success");
 authReturnFocus=document.activeElement;el("authDialog").classList.remove("hidden");el("closeAuth").focus();
}
function closeAuth(){
 if(el("authDialog").classList.contains("hidden"))return;
 el("authDialog").classList.add("hidden");authReturnFocus?.focus({preventScroll:true});authReturnFocus=null;
}
function safeUnderworldUrl(raw){
 if(typeof raw!=="string"||!raw)return "";
 try{const u=new URL(raw);return u.protocol==="https:"&&!u.username&&!u.password&&!u.search&&!u.hash&&u.pathname==="/"?u.origin+"/":""}catch{return ""}
}
function configureUnderworld(raw){
 const url=safeUnderworldUrl(raw);
 for(const id of ["underworldLogin","underworldResume"]){
  const n=el(id);n.classList.toggle("hidden",!url);if(url)n.href=url;else n.removeAttribute("href");
 }
}
function hasPlayIdentity(session,config){return !!session&&(!config?.staging||session.links?.some(l=>l.provider==="underworld"))}
/* v2.9.9h — reject async arcade responses from old accounts or login epochs.
   An account may log out and return to the SAME ID before a request resolves. */
function arcadeOwner(){
 return {player:String(S.session?.player_id||""),epoch:S.arcadeEpoch};
}
function isArcadeOwner(owner){
 return !!owner&&!!S.session&&
  String(S.session.player_id)===owner.player&&S.arcadeEpoch===owner.epoch;
}
function ensureArcadeOwner(owner){
 if(!isArcadeOwner(owner)){
  const err=Error("Account changed during arcade action; refresh your current character.");
  err.status=409;throw err;
 }
}
function syncPlayIdentity(){
 const id=S.session?String(S.session.player_id):null;
 if(id===S.playIdentity)return;
 S.playIdentity=id;S.arcadeEpoch++;if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.dispose();S.arcadePracticeRuntime=null;S.arcadePractice=null;el("arcadePractice")?.classList.add("hidden");if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.dispose();S.arcadeGalleryRuntime=null;S.arcadeGallery=null;el("arcadeGallery")?.classList.add("hidden");if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.dispose();S.arcadeSafeRuntime=null;S.arcadeSafe=null;el("arcadeSafe")?.classList.add("hidden");if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.dispose();S.arcadeSnowmanRuntime=null;S.arcadeSnowman=null;el("arcadeSnowman")?.classList.add("hidden");if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.dispose();S.arcadeCatchRuntime=null;S.arcadeCatch=null;el("arcadeCatch")?.classList.add("hidden");if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.dispose();S.arcadeTriviaRuntime=null;S.arcadeTrivia=null;el("arcadeTrivia")?.classList.add("hidden");if(S.arcadeHubRuntime)S.arcadeHubRuntime.dispose();S.arcadeHubRuntime=null;S.arcadeHub=null;S.arcadeHubSeq++;S.arcadeHubPending=false;S.arcadeHubError=null;S.arcadeHubClassicInitialised=false;el("arcadeHub")?.classList.add("hidden");el("arcadeClassic").open=true;S.staffLab=null;S.staffRole=null;S.staffDirectory=null;S.staffDossier=null;S.staffSelected=null;S.staffDirectorySeq++;S.staffDossierSeq++;S.staffDirectoryBusy=false;S.staffDossierBusy=false;S.staffReviewBusy=false;S.staffAllowed=false;S.staffCheckedIdentity=null;S.staffAccessCheckedAt=0;S.staffData=null;updateStaffNavigation();closeStreetsDock(false);disconnectStreetsChat();S.arcade=null;S.arcadeRun=null;S.arcadeBoard=null;S.arcadeBoardSeq++;showArcade();S.activities=null;el("activitiesResult")?.classList.add("hidden");showActivities();S.chosenTarget=false;S.lastThrow=null;S.targetsReady=false;
 // Never show the prior account's selected rival or equipped Market style
 // while the next login's authoritative records are still loading.
 S.targets=[];S.shop=null;showRivalAppearance(null);
 S.pendingActions.clear();restorePending();
 el("targetSelect").value="";el("combatOutcome").classList.add("hidden");el("siegeOutcome").classList.add("hidden");el("bossRecap").classList.add("hidden");el("playFeedback").classList.add("hidden");
}
function timeLeft(value,now){const t=Date.parse(value);return Number.isFinite(t)?Math.max(0,Math.ceil((t-now)/1000)):0}
function shortTime(seconds){const n=Math.max(0,Math.ceil(seconds||0));if(n<60)return n+"s";const m=Math.ceil(n/60);return m<60?m+" min":Math.floor(m/60)+"h "+(m%60)+"m"}
function playBlock({session,me,hq,world,raid,progress,config,kind,style="standard",item,now,fresh=true,pending=false,busy=false}){
 if(busy)return "Updating your game…";
 if(!session)return "Sign in to play.";
 if(!hasPlayIdentity(session,config))return "Continue through Underworld first.";
 if(!me?.registered)return "Create your character at HQ.";
 if(me.review_state==="disqualified")return "Your character is disqualified from the event.";
 if(pending)return ""; // an exact idempotent replay may already have succeeded
 if(!fresh)return "Refresh your character before playing.";
 if(me.phase!=="live")return me.phase==="paused"?"Event paused.":["closed","finalized"].includes(me.phase)?"Event finished.":"Gameplay opens at kickoff.";
 const rules=config?.play_rules||{},r=me.resources||{},timers=hq?.timers||{},ko=timeLeft(timers.knockout,now);
 if(["throw","boss","siege","ready"].includes(kind)&&ko)return "Recovering from knockout · "+shortTime(ko)+".";
 if(kind==="ready")return "";
 if(kind==="craft"){
  const base=rules.craft_costs?.[item],price=typeof base==="number"?base-(item==="fort"&&me.day===2?2:0):null;
  const count=progress?.inventory?.[item],cap=rules.item_caps?.[item];
  if(typeof count==="number"&&typeof cap==="number"&&count>=cap)return "You already hold the maximum of this item.";
  if(price!=null&&typeof r.snowflakes==="number"&&r.snowflakes<price)return "Need "+price+" Snowflakes to craft.";
  return "";
 }
 if(kind==="boss"&&(raid?.state==="disabled"||world?.boss_enabled===false))return "The Snow Don is disabled.";
 if(kind==="siege"&&(!Number.isInteger(world?.day)||world.day!==me.day||world.city!==me.city||!(world.siege_max_hp>0)))return "Refresh to load your current city fortress.";
 if(kind==="boss"||kind==="siege"){
  const limit=rules[kind+"_limit"],attempts=world?.[kind+"_attempts"],cap=rules[kind+"_cap"],points=world?.[kind+"_points"];
  if(typeof limit==="number"&&typeof attempts==="number"&&attempts>=limit)return "Daily attack limit reached.";
  if(typeof cap==="number"&&typeof points==="number"&&points>=cap)return "Daily score limit reached.";
 }
 if(kind==="throw"){
  if(typeof rules.pvp_cap==="number"&&typeof r.today_pvp==="number"&&r.today_pvp>=rules.pvp_cap)return "Daily PvP score limit reached.";
  if(style==="golden"&&progress?.inventory&&Number(progress.inventory.golden||0)<1)return "You need a Golden Snowball.";
 }
 if((kind!=="throw"||style!=="golden")&&typeof r.snowballs==="number"&&r.snowballs<1){
  const regen=timeLeft(timers.snowball,now);return "Out of snowballs"+(regen?" · next in "+shortTime(regen):" · refresh for regeneration")+".";
 }
 const cooldown=timeLeft(timers.throw,now);
 return cooldown?"Throw cooldown · "+shortTime(cooldown)+".":"";
}
function currentPlayBlock(kind,body={}){
 return playBlock({session:S.session,me:S.me,hq:S.hq,world:S.world,raid:S.raid,progress:S.progress,config:S.config,kind,style:body.style,item:body.item,now:Date.now()+S.hqClock,fresh:S.privateFresh,busy:S.busy||S.privatePending,pending:S.pendingActions.has(requestKey("/v1/game/"+kind,body))});
}
function chooseQuickPlay({phase,bossBlocked,throwBlocked,siegeBlocked,targets,ammo}){
 if(["closed","finalized"].includes(phase))return {route:"wire",label:"Event results",hint:"Review the final editions and standings."};
 if(phase!=="live")return {route:"cities",label:"Explore City Wars",hint:phase==="paused"?"Event paused. Explore the standings while you wait.":"Explore the cities while waiting for kickoff."};
 if(!throwBlocked&&targets)return {route:"combat",label:"Fight rivals",hint:"Choose an available rival and throw a snowball."};
 if(!bossBlocked)return {route:"boss",label:"Join the boss raid",hint:"Attack the shared Snow Don. No rival selection needed."};
 if(siegeBlocked==="")return {route:"cities",label:"Fight the city siege",hint:"Join your city’s shared fortress battle."};
 return {route:"shop",label:"Browse the market",hint:ammo===0?"Snowballs are regenerating. Browse the market while you wait.":"Check your resources and browse the market."};
}
function updatePlayControls(){
 if(!el("playStatus"))return;
 const r=S.me?.resources,registered=!!S.session&&!!S.me?.registered,linked=hasPlayIdentity(S.session,S.config);
 el("playStatus").classList.toggle("hidden",!registered);
 if(registered){
  txt("playPlayer",S.me.mr_username);txt("playGreeting","Ready, "+S.me.mr_username+"?");
  for(const [id,key] of [["playAmmo","snowballs"],["playWarmth","warmth"],["playFlakes","snowflakes"]])txt(id,r?.[key]);
  txt("playPoints",S.me.score);
  showResourceArtwork(r,S.me.score);
 }
 const body={target_player_id:el("targetSelect").value,style:el("throwStyle").value};
 const pendingThrow=!!S.lastThrow&&S.pendingActions.has(requestKey("/v1/game/throw",S.lastThrow.body));
 const throwBlock=pendingThrow&&JSON.stringify(body)!==JSON.stringify(S.lastThrow.body)?"Refresh to restore your previous unconfirmed throw.":currentPlayBlock("throw",body),bossBlock=currentPlayBlock("boss"),siegeBlock=currentPlayBlock("siege"),readyBlock=currentPlayBlock("ready"),craftBlock=currentPlayBlock("craft",{item:el("craftChoice").value});
 const restrict=registered&&linked;
 const disabled=(id,reason)=>{const n=el(id);n.disabled=!!(S.busy||S.privatePending||restrict&&reason);n.title=restrict&&reason?reason:""};
 disabled("throwButton",(!S.targetsReady&&!pendingThrow&&restrict?"Refresh the rival list first.":"")||throwBlock||(!body.target_player_id?"Choose an eligible rival.":""));
 el("targetSelect").disabled=!!(S.busy||pendingThrow);el("throwStyle").disabled=!!(S.busy||pendingThrow);
 txt("throwButton",pendingThrow?"Retry previous throw":"❄ Throw snowball");
 disabled("bossButton",bossBlock);disabled("siegeButton",siegeBlock);disabled("readyButton",readyBlock);disabled("craftButton",craftBlock);
 el("findTargets").disabled=!!(S.busy||S.privatePending);el("playRefresh").disabled=!!(S.busy||S.privatePending);
 txt("combatStatus",throwBlock||(pendingThrow?"Previous throw unconfirmed — retry safely with the same action ID.":!S.targetsReady?"Rival list unavailable — refresh.":S.targets.length?"Choose your rival and take a shot.":"No eligible rivals right now."));
 const bossPending=S.pendingActions.has(requestKey("/v1/game/boss",{}));
 txt("raidPlayStatus",bossBlock||(bossPending?"Previous raid attempt unconfirmed — retry safely.":"Ready to attack · 1 snowball per attempt."));
 if(bossPending)txt("bossButton","Retry previous raid");else txt("bossButton",S.raid?.state==="defeated"?"Attack frozen echo":"Attack the Snow Don");
 const rules=S.config?.play_rules||{},w=S.world;
 txt("raidQuota",registered&&w&&typeof w.boss_attempts==="number"&&typeof rules.boss_limit==="number"?Math.max(0,rules.boss_limit-w.boss_attempts)+" boss attempts left today":"Daily boss attack limits apply.");
 const siegePending=S.pendingActions.has(requestKey("/v1/game/siege",{}));
 txt("siegePlayStatus",siegeBlock||(siegePending?"Previous siege attempt unconfirmed — retry safely.":w?.siege_hp===0?"Fortress cleared. Frozen echo attempts follow the usual limits.":"Ready to attack · 1 snowball"));
 txt("siegeButton",siegePending?"Retry previous siege":w?.siege_hp===0&&w?.siege_max_hp>0?"Attack fortress echo":"Attack city fortress");
 el("refreshSiege").disabled=!!(S.busy||S.privatePending);
 const arena=timeLeft(S.hq?.timers?.arena,Date.now()+S.hqClock);
 txt("readyButton",arena?"Extend arena readiness":"Enter arena");
 const price=rules.craft_costs?.[el("craftChoice").value],actual=typeof price==="number"?price-(el("craftChoice").value==="fort"&&S.me?.day===2?2:0):null;
 txt("craftHint",(actual!=null?"Cost: "+actual+" Snowflakes. ":"")+(craftBlock||"Crafted items go into your shared inventory."));
 const selected=S.targets.find(t=>String(t.player_id)===body.target_player_id);
 showRivalAppearance(selected);
 showSnowballLoadout(body.style);
 txt("targetDetail",selected?selected.city+" · "+fmt(selected.warmth)+" warmth · "+fmt(selected.hits_remaining)+" scoring hits left today.":"");
 const style=rules.styles?.[body.style];
 txt("throwStyleHint",Array.isArray(style)?"Base accuracy "+Math.round(style[0]*100)+"% · "+style[1]+" damage · "+style[2]+" base points. Modifiers may apply.":"Choose a throwing style.");
 el("noRivals").classList.toggle("hidden",!(registered&&linked&&S.me.phase==="live"&&S.targetsReady&&!S.targets.length));
 const q=chooseQuickPlay({phase:S.me?.phase,bossBlocked:bossBlock,throwBlocked:throwBlock,siegeBlocked:siegeBlock,targets:S.targets.length,ammo:r?.snowballs});
 txt("playCoach",q.hint);txt("playPrimary",q.label);el("playPrimary").dataset.destination=q.route;
 if(registered&&!linked){txt("playCoach","Continue through Underworld to play your linked character.");txt("playPrimary","Account settings");el("playPrimary").dataset.destination="account"}
}
function playFeedback(message,kind){
 el("playFeedback").dataset.kind=kind;txt("playFeedbackText",message);el("playFeedback").classList.remove("hidden");
}
function showCombatOutcome(result,target){
 el("combatOutcome").classList.remove("hidden");
 txt("combatOutcomeTitle",result.repeated?"Previously recorded throw":result.knocked_out?"Rival knocked out!":result.critical?"Critical hit!":result.hit?"Direct hit!":"Snowball missed");
 txt("combatOutcomeText",(target?.mr_username?target.mr_username+" · ":"")+(result.hit?fmt(Number(result.warmth_damage||0)+Number(result.armour_damage||0))+" damage · +"+fmt(result.points_awarded)+" points.":"No points from this throw.")+" Your next action uses the normal game cooldown.");
}
function showMe(){
 const signed=!!S.session,allowed=hasPlayIdentity(S.session,S.config);
 syncPlayIdentity();
 el("authToggle").textContent=signed?"Sign out":"Sign in";
 txt("identityStatus",signed?"Signed in":"Guest");
 el("loggedOutNotice").classList.toggle("hidden",signed);
 el("registration").classList.toggle("hidden",!signed||!allowed||!!S.me?.registered||!S.me);
 el("underworldRequired").classList.toggle("hidden",!signed||allowed||S.staffAllowed);
 el("playerDashboard").classList.toggle("hidden",!signed||!S.me?.registered);
 el("linkedIdentity").classList.toggle("hidden",!signed);
 el("accountTools").classList.toggle("hidden",!signed);
 if(signed&&!allowed)el("accountTools").open=true;
 showWardrobe();
 if(!signed){el("bossRecap").classList.add("hidden");showHq();}
 if(!signed||S.session?.links?.some(x=>x.provider==="discord")){
   el("discordDiscardPanel").classList.add("hidden");S.discard=null;
 }
 const links=S.session?.links||[];
 const hasDiscord=links.some(x=>x.provider==="discord");
 const hasUnderworld=links.some(x=>x.provider==="underworld");
 txt("canonicalPlayerId",S.session?.player_id);
 txt("providerStatus",(hasUnderworld?"Underworld connected":"Underworld not linked")+
     " · "+(hasDiscord?"Discord connected":"Discord not linked"));
 el("linkDiscord").disabled=hasDiscord||!S.config?.discord_oauth;
 el("linkDiscord").textContent=hasDiscord?"✓ Discord linked":S.config?.discord_oauth?
      "Link Discord account":"Discord linking not configured";
 if(!S.me?.registered){
   txt("progressSummary","Register this character to compare your official game progress.");
   showVerification();updatePlayControls();
   return;
 }
 renderProgress();
 showVerification();
 txt("welcomeName",S.me.mr_username);txt("welcomeCity",S.me.city+" · Day "+(S.me.day||"—"));
  txt("hqCityName",S.me.city+" winter headquarters");
  const citySlug=Object.hasOwn(CITY_SLUG,S.me.city)?CITY_SLUG[S.me.city]:null;
  const cityImage=el("hqCityArt");
  if(citySlug){cityImage.src="/art/cities/"+citySlug+".webp";el("hqCityCrest").src="/art/v290/cities/crests/"+citySlug+"_crest.png";}
  else {cityImage.removeAttribute("src");el("hqCityCrest").removeAttribute("src");}
  cityImage.alt="";
  const ammo=Number(S.me.resources?.snowballs||0);
  txt("hqNextMove",ammo>0?
      "You've got "+fmt(ammo)+" snowballs ready. Pick a rival or confront the Snow Don.":
      "Ammunition is low. Explore the Winter Market or check back for regeneration.");
 txt("ammoValue",S.me.resources?.snowballs);txt("warmthValue",S.me.resources?.warmth);
 txt("flakeValue",S.me.resources?.snowflakes);txt("scoreValue",fmt(S.me.score));
 txt("shopBalance",fmt(S.me.resources?.snowflakes));
 showResourceArtwork(S.me.resources,S.me.score);
 txt("ammoSub",S.me.resources?.next_snowball_at?"Regenerating snowballs":"Ready for action");
 txt("phaseValue",S.me.phase.toUpperCase());txt("sideStatus",S.me.phase.toUpperCase());
 txt("sideStatusDetail","Day "+(S.me.day||"—")+" of 7 · "+S.me.city);
 showHq();updatePlayControls();
}
function showVerification(){
 const links=S.session?.links||[];
 const linked=!!S.session&&!!S.me?.registered&&
    links.some(x=>x.provider==="discord")&&links.some(x=>x.provider==="underworld");
 el("crossPlatformPanel").classList.toggle("hidden",!linked);
 if(!linked)return;
 const v=S.verification;
 txt("verificationIdentity","✓ Underworld and Discord linked to player "+S.session.player_id+".");
 if(!v||v.state==="not_started"){
   txt("verificationState","Not started. Save a baseline before your Discord move.");
   txt("verificationDiscord","Discord confirmation: waiting for verification.");
   txt("verificationGameplay","Discord gameplay: waiting for an actual game action.");
   txt("verificationReverse","Website → Discord reverse check: optional.");
   txt("verificationCounts","No activity in the current check.");
   txt("verificationDelta","Official progress will be compared after verification starts.");
   return;
 }
 if(v.state==="expired"){
   txt("verificationState","Verification expired after 15 minutes. Start a fresh test.");
   txt("verificationDiscord","No current Discord proof.");
   txt("verificationGameplay","No current gameplay proof.");
   txt("verificationReverse","Reverse check: not completed.");
   txt("verificationCounts","The previous test has expired.");
   txt("verificationDelta","Start a new check to record a fresh baseline.");
   return;
 }
 txt("verificationState",v.discord_gameplay_verified?
     "✓ Discord action recorded in the same official game database.":
     v.discord_confirmed?"✓ Same player verified on Discord. Now perform a game action.":
     "Awaiting the /snowbridge verify Discord command.");
 txt("verificationDiscord",v.discord_confirmed?
     "✓ Discord interaction authenticated as this canonical player.":
     "○ Discord confirmation pending. Run /snowbridge verify.");
 txt("verificationGameplay",v.discord_gameplay_verified?
     "✓ A real Discord crafting, PvP or boss action was recorded after this test started.":
     "○ No verified Discord gameplay yet. Use /snowbridge craft or /snowbridge boss.");
 txt("verificationReverse",v.web_gameplay_seen_by_discord?
     "✓ Discord re-read progress after a website action.":
     "○ Optional: act on this website, then run /snowbridge verify again.");
 txt("verificationCounts","Official events since baseline: Discord "+fmt(v.discord_action_count)+
     " · Website "+fmt(v.web_action_count));
 const d=v.delta||{},pieces=[];
 for(const [key,name] of [["score","points"],["snowballs","snowballs"],["snowflakes","Snowflakes"],
                           ["warmth","warmth"],["boss_hp","Snow Don HP"]]){
   const value=Number(d[key]||0);
   if(value)pieces.push((value>0?"+":"")+fmt(value)+" "+name);
 }
 for(const [item,count] of Object.entries(d.inventory||{})){
   if(count)pieces.push((count>0?"+":"")+fmt(count)+" "+item);
 }
 txt("verificationDelta","Changes from website baseline: "+(
     pieces.length?pieces.join(" · "):"No stable game values changed yet."));
}
function renderProgress(){
 const p=S.progress;
 if(!p?.registered){txt("progressSummary","Loading official shared progress…");return}
 txt("progressSummary","Official score: "+fmt(p.score)+" · "+fmt(p.snowballs)+
     " snowballs · "+fmt(p.snowflakes)+" snowflakes · Snow Don "+
     fmt(p.boss_hp)+"/"+fmt(p.boss_max_hp)+" HP.");
}
function showBoss(){
 const raid=S.raid,known=raid?.hp!=null&&Number(raid.max_hp)>0;
 const hp=known?Number(raid.hp):0,max=known?Number(raid.max_hp):0;
 const state=raid?.state||"waiting",defeated=state==="defeated",disabled=state==="disabled";
 const visibleHealth=known&&!disabled,percent=visibleHealth?Math.max(0,Math.min(100,100*hp/max)):0;
 const tier=visibleHealth?raid.tier:null;
 for(const id of ["snowDonHero","bossScene"])el(id).dataset.bossState=state;
 const art=el("heroBossArt"),portrait=el("bossPortrait");
 const splash=raid?.splash||"/art/v290/boss/phase_ice.webp";
 const portraitPath=raid?.portrait||"/art/boss/snow_don_100.png";
 if(art.getAttribute("src")!==splash)art.src=splash;
 if(portrait.getAttribute("src")!==portraitPath)portrait.src=portraitPath;
 art.dataset.tier=tier==null?"":String(tier);portrait.dataset.tier=art.dataset.tier;
 art.alt=defeated?"Original Discord Snow Don final defeat scene":"Original Discord Snow Don cinematic: "+(raid?.title||"awaiting the raid");
 portrait.alt=defeated?"Original Discord defeated Snow Don portrait":tier==null?"Original Snow Don portrait":"Discord Snow Don damage portrait — "+tier+"% health tier";
 txt("bossTierLabel",tier==null?"Awaiting status":tier===0?"Defeated":tier+"% artwork tier");
 el("heroLiveTitle").classList.toggle("hidden",defeated);el("heroDefeatTitle").classList.toggle("hidden",!defeated);
 txt("heroLede",defeated?"The shared Snow Don has fallen. The city celebrates. Visit the raid aftermath or continue your permitted daily activities.":"Six cities. Seven days. One very angry Snow Don. Grab your ammunition, pick your city and make a name for yourself.");
 const status=visibleHealth?fmt(hp)+" / "+fmt(max)+" HP · "+(raid?.title||""):(raid?.title||"Awaiting the Snow Don");
 txt("heroBossStatus",status+(S.bossStale?" · Refresh pending":""));
 txt("heroArtCaption",defeated?"THE FINAL SNOWFALL":(raid?.title||"ART FROM THE ORIGINAL DISCORD EVENT"));
 txt("heroBossLink",defeated?"View the aftermath":"Meet the Snow Don");
 txt("hqBossLink",defeated?"View boss aftermath":"🎯 Attack Snow Don");
 txt("bossHeadline",defeated?"The Snow Don has fallen!":disabled?"The boss is disabled":visibleHealth?"The Snow Don lives.":"The boss awaits.");
 txt("bossPhase",raid?.title||"The city is waiting");
 txt("raidDay",raid?.day?"SNOW DON / DAY "+raid.day+" OF 7":"SNOW DON / CURRENT STATUS");
 txt("bossHpText",visibleHealth?fmt(hp)+" / "+fmt(max)+" HP":"— / — HP");
 txt("bossDamage",visibleHealth?Math.round(100-percent)+"% damage taken":"—");
 const bar=el("bossHpBar");bar.style.width=percent+"%";
 if(visibleHealth)bar.parentElement.setAttribute("aria-valuenow",String(Math.round(percent)));
 else bar.parentElement.removeAttribute("aria-valuenow");
 for(const [id,key] of [["raidHits","hit_count"],["raidContributors","contributors"],["raidMisses","misses"]])
  txt(id,raid?.[key]==null?"—":fmt(raid[key]));
 txt("raidSummary",raid?.echo_attacks==null?"Raid statistics will appear once the boss spawns.":fmt(raid.echo_attacks)+" frozen-echo attempts · shared raid totals exclude echo damage.");
 txt("bossFreshness",S.bossStale?(raid?"Last known raid status — refresh pending.":"Raid unavailable — refresh pending."):raid?"Synced with the shared raid · refreshes every 30 seconds while this page is visible.":"Waiting for the shared raid.");
 txt("bossActionTitle",defeated?"The Don is down.": "Put the heat on him.");
 txt("bossActionText",defeated?"The real Don is defeated. The existing frozen-echo action remains available under the normal game rules; it cannot defeat him again.":"Attack the shared Snow Don with your snowballs. Daily limits apply.");
 txt("bossButton",defeated?"Attack frozen echo":"Attack the Snow Don");
 if(!S.busy)el("bossButton").disabled=disabled||raid?.season_phase==="closed"||raid?.season_phase==="finalized";
}
async function refreshBossVisual(){
 const sequence=++S.bossRequest;S.bossPending=true;
 try{
  const raid=await get("/v1/web/boss");
  if(sequence!==S.bossRequest)return;
  if(!["waiting","disabled","healthy","cracked","wounded","critical","defeated"].includes(raid.state))throw Error("Missing raid status");
  S.raid=raid;S.bossStale=false;
 }catch{
  if(sequence!==S.bossRequest)return;
  S.bossStale=true;
 }finally{
  if(sequence===S.bossRequest){S.bossPending=false;showBoss();showEvent()}
 }
}
function showBossRecap(r){
 const echo=!!r.echo,final=!!r.final_blow&&!echo;
 txt("bossRecapTitle",final?"The final blow!":echo?"Frozen echo encounter":r.hit?"Direct hit!":"The Don dodged the shot.");
 txt("bossRecapText",(r.hit?(echo?"Echo damage: ":"Damage: ")+fmt(r.damage)+" · "+fmt(r.points)+" points.":"No hit this attempt.")+
    (r.repeated?" Previously recorded action.":""));
 const image=el("bossRecapArt"),tier=bossArtTier(r.hp_after,r.max_hp);
 image.src=final?"/art/v290/boss/victory_screen.webp":tier===0?"/art/v290/boss/snow_don_0.webp":"/art/boss/snow_don_"+tier+".png";
 image.alt=final?"Original Discord final-blow victory artwork":"Snow Don artwork at the recorded encounter's remaining health";
 el("bossRecap").classList.remove("hidden");
}
function showTargets(){
 let node=el("targetSelect"),current=node.value;
 node.innerHTML="<option value=''>"+(!S.session?"Sign in to find rivals":!S.targetsReady?"Refresh to find rivals":S.targets.length?"Choose a rival":"No eligible rivals")+"</option>"+S.targets.map(t=>"<option value='"+esc(t.player_id)+"'>"+esc(t.mr_username)+" — "+esc(t.city)+" · "+fmt(t.hits_remaining)+" hits left</option>").join("");
 if(S.targets.some(t=>String(t.player_id)===current))node.value=current;
 else if(!S.chosenTarget&&S.targets.length){node.value=String(S.targets[0].player_id);S.chosenTarget=true}
 if(S.lastThrow&&S.pendingActions.has(requestKey("/v1/game/throw",S.lastThrow.body))){
  const key=S.lastThrow.body.target_player_id;
  if(!S.targets.some(t=>String(t.player_id)===key))node.insertAdjacentHTML("beforeend","<option value='"+esc(key)+"'>"+esc(S.lastThrow.target?.mr_username||"Previous rival")+" · retry unconfirmed throw</option>");
  node.value=key;el("throwStyle").value=S.lastThrow.body.style;
 }
 updatePlayControls();
}
function showBoard(){
 el("leaderboard").innerHTML=S.board.length?S.board.map((r,i)=>"<div class='score-row'><span class='rank'>"+(i+1)+"</span><div><strong>"+esc(r.mr_username)+"</strong><small>"+esc(r.city)+"</small></div><span class='score-total'><img src='"+resourceArtUrl("points",r.score)+"' alt='' loading='lazy'><strong>"+fmt(r.score)+" pts</strong></span></div>").join(""):"<div class='empty'>The scoreboard is waiting for its first winner.</div>";
}
// Original Discord v290 artwork landmarks and city palette.
const CITY_META=Object.freeze({
 "Chicago":{x:648,y:255,color:"#f07a74"},
 "New York":{x:820,y:244,color:"#85bafb"},
 "Detroit":{x:703,y:240,color:"#c09bea"},
 "Philadelphia":{x:808,y:259,color:"#edc479"},
 "Las Vegas":{x:289,y:332,color:"#e9a0d2"},
 "Los Angeles":{x:240,y:358,color:"#84dcbb"}
});
const knownCity=city=>Object.hasOwn(CITY_META,city);
const cityAsset=(city,type)=>{
 if(!knownCity(city))return "";
 const slug=CITY_SLUG[city];
 return type==="skyline"?"/art/cities/"+slug+".webp":"/art/v290/cities/"+(type==="crest"?"crests/"+slug+"_crest.png":"banners/"+slug+"_district_banner.png");
};
function territoryView(board,city){
 const banner=board?.banners?.find(b=>b.city===city)||null;
 const match=board?.matches?.find(m=>[m.city_a,m.city_b].includes(city))||null;
 const held=board?.districts?.filter(d=>d.owner===city)||[];
 const home=board?.districts?.find(d=>d.kind==="home"&&d.contenders?.includes(city))||null;
 const results=match?[match.rally_owner,match.duel_owner]:[];
 const wins=results.filter(owner=>owner===city).length,losses=results.filter(owner=>knownCity(owner)&&owner!==city).length;
 const archived=board?.day!=null&&(board.day<board.current_day||["closed","finalized"].includes(board.phase));
 return {banner,match,held,home,wins,losses,archived,
  outcome:wins>0&&losses===0?"victory":losses>0&&wins===0?"defeat":wins&&losses?"mixed":"neutral"};
}
// Active siege is pinned to the actual shared world snapshot, never a browsed historical day.
function siegeAssignment(world,me,config){
 if(!me?.registered||!knownCity(me.city)||world?.city!==me.city||!Number.isInteger(world.day)||world.day<1||world.day>7||world.day!==me.day)return null;
 const pair=config?.rival_schedule?.[String(world.day)]?.find(p=>Array.isArray(p)&&p.length===2&&p.includes(me.city)&&p.every(knownCity));
 const rival=pair?.find(city=>city!==me.city)||null;
 const known=typeof world.siege_hp==="number"&&world.siege_hp>=0&&typeof world.siege_max_hp==="number"&&world.siege_max_hp>0;
 return {home:me.city,rival,day:world.day,known,cleared:known&&world.siege_hp===0,percent:known?hqPercent(world.siege_hp,world.siege_max_hp):0};
}
function siegeImage(id,src,alt=""){
 const n=el(id);if(src){if(n.getAttribute("src")!==src)n.src=src;n.alt=alt;n.classList.remove("hidden")}
 else{n.removeAttribute("src");n.alt="";n.classList.add("hidden")}
}
function showSiege(){
 if(!el("citySiege"))return;
 const world=S.session?S.world:null,a=siegeAssignment(world,S.session?S.me:null,S.config),rules=S.config?.play_rules||{};
 el("citySiege").dataset.siegeState=!a?.known?"waiting":a.cleared?"cleared":"active";
 el("siegeMatchup").classList.toggle("hidden",!a?.rival);
 siegeImage("siegeRivalSkyline",a?.rival?cityAsset(a.rival,"skyline"):null,a?.rival?a.rival+" daily rival skyline":"");
 siegeImage("siegeHomeCrest",a?cityAsset(a.home,"crest"):null);
 siegeImage("siegeRivalCrest",a?.rival?cityAsset(a.rival,"crest"):null);
 txt("siegeHomeName",a?.home||"");txt("siegeRivalName",a?.rival||"");
 txt("siegeDay",a?"CITY SIEGE · DAY "+a.day+" OF 7":"CITY SIEGE · DAILY ASSIGNMENT");
 txt("siegeTitle",a?.rival?a.home+" vs "+a.rival:a?a.home+" city siege":"Your city's siege");
 txt("siegeRivalNote",a?.rival?"Today's City Wars matchup · separate from the NPC fortress below.":a?"Your daily rival is unavailable.":"Sign in and wait for kickoff to see your city's assignment.");
 txt("siegeFortTitle",a?.known?a.cleared?"Fortress breached · echo available":a.home+" shared fortress":"Awaiting siege status");
 txt("siegeHpText",a?.known?fmt(world.siege_hp)+" / "+fmt(world.siege_max_hp)+" HP":"— / — HP");
 txt("siegeDamage",a?.known?Math.round(100-a.percent)+"% damage taken":"—");
 el("siegeHpBar").style.width=(a?.percent||0)+"%";
 if(a?.known)el("siegeHealthTrack").setAttribute("aria-valuenow",String(Math.round(a.percent)));else el("siegeHealthTrack").removeAttribute("aria-valuenow");
 txt("siegeAttempts",a&&typeof rules.siege_limit==="number"&&typeof world.siege_attempts==="number"?Math.max(0,rules.siege_limit-world.siege_attempts):"—");
 txt("siegePoints",a&&typeof world.siege_points==="number"?fmt(world.siege_points):"—");
}
function showSiegeOutcome(r){
 el("siegeOutcome").classList.remove("hidden");
 txt("siegeOutcomeTitle",r.repeated?"Previously recorded siege":r.final_blow&&!r.echo?"Fortress breached!":r.echo?"Fortress echo encounter":r.hit?"Direct hit!":"Snowball missed");
 txt("siegeOutcomeText","Day "+fmt(r.day)+" · "+(r.city||"Your city")+" · "+(r.hit?fmt(r.damage)+" damage · +"+fmt(r.points)+" points.":"No points from this attempt.")+(r.repeated?" Previously recorded, not a second charge.":""));
}
function cityScore(n){return n==null?"—":(Number(n)/100).toLocaleString("en-GB",{maximumFractionDigits:2})}
function mapMarkup(board,selected){
 const lines=(board?.matches||[]).filter(m=>knownCity(m.city_a)&&knownCity(m.city_b)).map(m=>{
  const a=CITY_META[m.city_a],b=CITY_META[m.city_b],color=knownCity(m.rally_owner)?CITY_META[m.rally_owner].color:"#a9b5bd";
  return '<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'" stroke="'+color+'" stroke-width="3" stroke-dasharray="8 5" opacity=".85"/>';
 }).join("");
 const pins=Object.entries(CITY_META).map(([city,m])=>{
  const owned=territoryView(board,city).home?.owner===city;
  return '<circle data-map-city="'+city+'" class="map-city-pin" cx="'+m.x+'" cy="'+m.y+'" r="9" fill="#0b2031" stroke="'+(owned?m.color:"#a9b5bd")+'" stroke-width="4"><title>'+city+(owned?" · Home district held":" · Neutral home district")+'</title></circle>'+
   (selected===city?'<circle cx="'+m.x+'" cy="'+m.y+'" r="15" fill="none" stroke="#fff1c5" stroke-width="2.5"/>':"");
 }).join("");
 return lines+pins;
}
function districtMarkup(d){
 const owner=knownCity(d.owner)?d.owner:null,kind=["home","rally","duel"].includes(d.kind)?d.kind:"";
 return "<article class='district-card' data-district-kind='"+kind+"'><span class='eyebrow'>"+esc(kind==="home"?"Home stronghold":kind==="rally"?"Rally frontier":"Duel frontier")+"</span><strong>"+esc(d.name)+"</strong><small>"+(d.contenders||[]).map(esc).join(" vs ")+"</small><div class='district-owner'>"+(owner?"<img src='"+cityAsset(owner,"crest")+"' alt='' loading='lazy'><span>"+esc(owner)+"</span>":"<span class='neutral-mark'>○</span><span>Neutral</span>")+"</div></article>";
}
function comparisonBar(label,a,b,owner,left,right){
 const sum=Number(a)+Number(b);
 return "<div class='match-metric'><strong>"+esc(label)+"</strong><div class='match-pair-values'><span>"+fmt(a)+"</span><span>"+fmt(b)+"</span></div><div class='match-balance' aria-hidden='true'><span style='width:"+(sum?Math.max(0,Math.min(100,Number(a)/sum*100)):50)+"%;background:"+CITY_META[left].color+"'></span><span style='background:"+CITY_META[right].color+"'></span></div><small>"+(knownCity(owner)?"Held by "+esc(owner):"Neutral · tied or no lead")+"</small></div>";
}
function matchMarkup(m,selected){
 if(!knownCity(m.city_a)||!knownCity(m.city_b))return "";
 const a=m.city_a,b=m.city_b;
 return "<article class='city-match-card "+([a,b].includes(selected)?"selected-match":"")+"' data-match-slot='"+esc(m.slot)+"'><div class='match-header'><div><img src='"+cityAsset(a,"crest")+"' alt=''><strong>"+esc(a)+"</strong></div><span>VS</span><div><img src='"+cityAsset(b,"crest")+"' alt=''><strong>"+esc(b)+"</strong></div></div>"+
 comparisonBar(m.rally_district+" · rally marks",m.rally_a,m.rally_b,m.rally_owner,a,b)+comparisonBar(m.duel_district+" · scored hits",m.hits_a,m.hits_b,m.duel_owner,a,b)+
 "<div class='match-extra'><span>Throws: "+fmt(m.throws_a)+" / "+fmt(m.throws_b)+"</span><span>Damage: "+fmt(m.damage_a)+" / "+fmt(m.damage_b)+"</span><span>Knockouts: "+fmt(m.kos_a)+" / "+fmt(m.kos_b)+"</span></div></article>";
}
function showCities(){
 showSiege();
 const board=S.territory,home=S.session&&S.me?.registered&&knownCity(S.me.city)?S.me.city:null;
 const city=knownCity(S.citySelected)?S.citySelected:home||"Chicago",v=territoryView(board,city),b=v.banner;
 const focused=document.activeElement?.dataset?.city;
 const focusGroup=document.activeElement?.closest?.("#citySelectors,#cityStandings")?.id;
 txt("territoryDayLabel",!board?"Awaiting territory status":board.day==null?"Awaiting kickoff":"Day "+board.day+" of 7 · "+(v.archived?"Historical result":board.phase==="paused"?"Paused":"Current territory"));
 txt("territoryFreshness",S.territoryStale?"Unable to refresh — "+(board?"last known snapshot shown.":"territory unavailable."):S.territoryPending?"Refreshing territory…":board?"Shared Discord territory board · "+(v.archived?"historical view":"updates while this page is open"):"Waiting for territory data");
 const day=el("territoryDay");
 day.innerHTML='<option value="current">Current / latest day</option>'+Array.from({length:Math.max(0,Math.min(7,Number(board?.current_day)||0))},(_,i)=>'<option value="'+(i+1)+'">Day '+(i+1)+'</option>').join("");
 day.value=S.territoryDay;day.disabled=S.territoryPending;
 el("cityMapOverlay").innerHTML=mapMarkup(board,city);
 el("citySelectors").innerHTML=Object.keys(CITY_META).map(name=>{
  const x=territoryView(board,name);
  return "<button class='city-select' data-city='"+esc(name)+"' aria-pressed='"+String(name===city)+"' style='--city-accent:"+CITY_META[name].color+"'><img src='"+cityAsset(name,"crest")+"' alt=''><strong>"+esc(name)+"</strong><small>"+(board?x.held.length+" held":"Awaiting data")+(home===name?" · Your city":"")+"</small></button>";
 }).join("");
 el("citySkyline").src=cityAsset(city,"skyline");el("cityWarCrest").src=cityAsset(city,"crest");el("cityWarBanner").src=cityAsset(city,"banner");
 el("cityWarBanner").alt=city+" original district banner";
 txt("cityWarTitle",city+" War Room");txt("cityMotto",b?.motto||"");txt("cityHomeLabel",b?.home_district?b.home_district+(home===city?" · Your home city":""):(home===city?"Your home city":""));
 txt("cityHeld",board?v.held.length+" / "+board.districts.length:"—");txt("cityRally",b?fmt(b.rally_marks):"—");
 txt("cityActivity",b?fmt(b.active)+" / "+fmt(b.registered):"—");txt("cityPve",b?fmt(b.pve_hits):"—");
 txt("cityMissionName",b?.mission_name||"Awaiting city data");
 el("cityMissionMeter").style.width=hqPercent(b?.mission_progress,b?.mission_target)+"%";
 txt("cityMissionProgress",b&&b.mission_target?fmt(b.mission_progress)+" / "+fmt(b.mission_target)+(b.mission_complete?" · Complete":" · In progress"):"No active mission");
 txt("cityQuorum",b&&board.day!=null?"Home stronghold requires the city mission and "+b.stronghold_quorum+" active member"+(b.stronghold_quorum===1?"":"s")+".":"");
 const result=el("cityOutcomeArt"),art=v.archived&&["victory","defeat"].includes(v.outcome);
 result.classList.toggle("hidden",!art);
 if(art){result.src="/art/v290/cities/outcomes/city_"+v.outcome+"_background.png";result.alt=city+" "+v.outcome+" background"}else result.removeAttribute("src");
 txt("cityOutcomeText",!board?"Awaiting territory status":!v.match?"Awaiting daily rivalry":(v.archived?"Recorded result: ":"Current control: ")+v.wins+" frontier"+(v.wins===1?"":"s")+" held · "+v.losses+" held by rival · "+(2-v.wins-v.losses)+" neutral");
 txt("cityWarNote",b?"Claimed city quests: "+fmt(b.quests)+" · "+(v.home?.owner===city?"Home stronghold held.":"Home stronghold neutral."):"Territorial honours never add official points or prizes.");
 el("cityMatches").innerHTML=board?.matches?.length?board.matches.map(m=>matchMarkup(m,city)).join(""):"<p class='empty'>Daily rivalries appear after kickoff.</p>";
 txt("districtCount",board?board.districts.filter(d=>knownCity(d.owner)).length+" / "+board.districts.length+" held":"—");
 el("cityDistricts").innerHTML=board?.districts?.length?board.districts.map(d=>districtMarkup(d)).join(""):"<p class='empty'>District data is unavailable.</p>";
 const standings=S.cities.filter(r=>knownCity(r.city)),max=Math.max(0,...standings.map(r=>Number(r.score_x100)||0));
 el("cityStandings").innerHTML=standings.length?standings.map((r,index)=>{
  const leader=max>0&&r.score_x100===max;
  return "<button class='city-standing "+(leader?"score-leader":"")+"' data-city='"+esc(r.city)+"' aria-label='View "+esc(r.city)+" war room'><span class='rank'>"+(index+1)+"</span><img class='city-crest' src='"+cityAsset(r.city,"crest")+"' alt=''><div><strong>"+esc(r.city)+(leader?" · Score leader":"")+"</strong><small>"+fmt(r.active_players)+" active · "+fmt(r.daily_wins)+" daily wins · "+fmt(r.siege_clears)+" siege clears</small><div class='hq-meter'><span style='width:"+hqPercent(r.score_x100,max)+"%;background:"+CITY_META[r.city].color+"'></span></div><small>Current-day score: "+cityScore(r.todays_score_x100)+" · "+(r.provisional?"Provisional":r.qualifying_today?"Qualified":"Not qualified today")+"</small></div><strong>"+cityScore(r.score_x100)+" pts</strong></button>";
 }).join(""):"<div class='empty'>City standings are unavailable.</div>";
 txt("cityStandingsStatus",S.citiesReady?"Official season scoreboard · ordered by the shared game.":"Unable to refresh standings"+(standings.length?" · last known scores shown.":"."));
 if(focusGroup&&knownCity(focused))Array.from(el(focusGroup).querySelectorAll("[data-city]")).find(n=>n.dataset.city===focused)?.focus({preventScroll:true});
}
async function refreshCityStandings(){
 try{
  const data=await get("/v1/game/cities");
  if(!Array.isArray(data.cities))throw Error("Missing city standings");
  S.cities=data.cities;S.citiesReady=true;
 }catch{S.citiesReady=false}
 showCities();
}
async function refreshTerritory(){
 const seq=++S.territoryRequest,requested=S.territoryDay;
 S.territoryPending=true;txt("territoryFreshness","Refreshing territory…");el("territoryDay").disabled=true;
 try{
  const q=requested==="current"?"":"?day="+encodeURIComponent(requested);
  const board=await get("/v1/web/territory"+q);
  if(seq!==S.territoryRequest)return;
  if(!board?.honorary_only||!Array.isArray(board.banners)||!Array.isArray(board.matches)||!Array.isArray(board.districts))throw Error("Invalid territory response");
  S.territory=board;S.territoryStale=false;
 }catch{
  if(seq!==S.territoryRequest)return;
  S.territoryStale=true;
  if(S.territory&&requested!=="current"&&String(S.territory.day)!==requested)S.territoryDay=S.territory.day==null?"current":String(S.territory.day);
 }finally{if(seq===S.territoryRequest){S.territoryPending=false;showCities()}}
}
const MARKET_SLOTS=Object.freeze(["portrait","frame","banner","gear","trail"]);
const MARKET_FIELDS={marketCategory:"category",marketOwnership:"ownership",marketRarity:"rarity",marketSort:"sort",marketSearch:"search"};
function marketItem(key,items=S.items){return items.find(i=>i.key===key&&MARKET_SLOTS.includes(i.category))}
function marketWardrobe(){
 return S.session&&S.me?.registered&&String(S.session.player_id)===String(S.me.player_id)&&Array.isArray(S.shop?.unlocked)?S.shop:null;
}
function marketState(item,wardrobe){
 if(!wardrobe)return "unknown";
 if(ownedEquipped(wardrobe,item.category)===item.key)return "equipped";
 return wardrobe.unlocked.includes(item.key)?"owned":"unowned";
}
function marketEligible(item,kind){
 const w=marketWardrobe();
 if(S.busy||S.privatePending||!w||!S.catalogReady||!item||["flagged","disqualified"].includes(S.me?.review_state))return false;
 if(S.config?.staging&&!S.session?.links?.some(x=>x.provider==="underworld"))return false;
 const state=marketState(item,w);
 return kind==="equip"?state==="owned":
   kind==="buy"&&state==="unowned"&&S.me.phase==="live"&&Number.isFinite(item.cost)&&item.cost>=0&&Number(w.balance)>=item.cost;
}
function filterMarket(items,filters,wardrobe){
 const search=String(filters.search||"").trim().toLowerCase();
 const list=items.filter(i=>{
  if(!MARKET_SLOTS.includes(i.category))return false;
  if(filters.category!=="all"&&i.category!==filters.category)return false;
  if(filters.rarity!=="all"&&i.rarity!==filters.rarity)return false;
  const state=marketState(i,wardrobe);
  if(filters.ownership==="owned"&&!["owned","equipped"].includes(state))return false;
  if(["equipped","unowned"].includes(filters.ownership)&&state!==filters.ownership)return false;
  if(filters.ownership==="affordable"&&!(state==="unowned"&&Number(wardrobe?.balance)>=i.cost))return false;
  return !search||[i.name,i.detail,i.category,i.rarity].some(v=>String(v||"").toLowerCase().includes(search));
 });
 const cmp={low:(a,b)=>a.cost-b.cost,high:(a,b)=>b.cost-a.cost,rarity:(a,b)=>RARITIES.indexOf(b.rarity)-RARITIES.indexOf(a.rarity),name:(a,b)=>a.name.localeCompare(b.name)};
 if(Object.hasOwn(cmp,filters.sort))list.sort(cmp[filters.sort]);
 return list;
}
function fittingLayers(wardrobe,overrides,items){
 const layers=profileLayers(wardrobe);
 for(const slot of MARKET_SLOTS){
  const key=overrides[slot],item=marketItem(key,items);
  if(item?.category===slot&&HQ_SLOTS[slot].includes(key)&&Object.hasOwn(COSMETIC_ART,key))layers[slot]={key,src:wornCosmeticArt(key)};
 }
 return layers;
}
function syncMarketIdentity(){
 const id=S.session?String(S.session.player_id):null;
 if(S.market.identity!==id){
  S.market.identity=id;S.market.preview={};S.market.ownership="all";
  el("marketOwnership").value="all";
 }
}
function showFitting(){
 const w=marketWardrobe(),layers=fittingLayers(w,S.market.preview,S.items),actual=profileLayers(w);
 renderProfileLayers("fit",layers,w?S.me?.mr_username||"Winter player":"Guest fitting model");
 const changed=MARKET_SLOTS.filter(slot=>layers[slot].key!==actual[slot].key);
 // A preview becomes normal equipped state after an explicit successful equip.
 for(const slot of MARKET_SLOTS)if(!changed.includes(slot))delete S.market.preview[slot];
 const worn=Object.values(layers).map(layer=>marketItem(layer.key)).filter(Boolean);
 const rarity=worn.reduce((r,i)=>RARITIES.indexOf(i.rarity)>RARITIES.indexOf(r)?i.rarity:r,"Common");
 el("fitCollector").dataset.rarity=rarity;
 txt("fitRarity",rarity+" style preview");
 txt("fitPlayerName",w?S.me.mr_username:"Guest fitting model");
 txt("fitStatus",changed.length?changed.length+" previewed slot"+(changed.length===1?"":"s")+" · Previewing never purchases or equips an item.":"Showing "+(w?"your currently equipped outfit":"the default recruit")+". Try any item for free.");
 el("fitReset").disabled=!changed.length;
 el("fitChanges").innerHTML=changed.map(slot=>{
  const i=marketItem(layers[slot].key),state=marketState(i,w),owned=["owned","equipped"].includes(state);
  const kind=owned?"equip":"buy",ready=marketEligible(i,kind);
  const label=owned?"Equip":i.cost===0?"Unlock free":"Unlock · ✦ "+fmt(i.cost);
  return "<div class='fit-change'><div><strong>"+esc(i.name)+"</strong><small>"+(owned?"Owned":state==="unknown"?"Preview only":"✦ "+fmt(i.cost)+" to unlock")+"</small></div><div class='fit-change-actions'><button data-fit-action='"+kind+"' data-item='"+esc(i.key)+"' class='button button-gold button-small' "+(!ready?"disabled":"")+">"+label+"</button><button data-fit-remove='"+slot+"' class='button button-outline button-small' aria-label='Remove "+esc(slot)+" preview'>✕</button></div></div>";
 }).join("");
 const cost=changed.reduce((total,slot)=>{const i=marketItem(layers[slot].key);return total+(w&&marketState(i,w)==="unowned"?i.cost:0)},0);
 txt("fitCost",w?"Estimated cost for unowned preview items: "+fmt(cost)+" Snowflakes. No checkout or automatic spend.":"Sign in to see your owned items and actual purchase eligibility.");
 txt("fitHint",w?"Unlock or equip individual preview items here or in the catalogue.":"Browsing and previewing are free.");
}
function tryMarketItem(key){
 const i=marketItem(key);
 if(!i||!HQ_SLOTS[i.category]?.includes(key)||!Object.hasOwn(COSMETIC_ART,key))return false;
 S.market.preview[i.category]=key;
 showShop();return true;
}
function focusFitting(){
 el("marketFitting").scrollIntoView({block:"start"});
 el("fittingTitle").focus({preventScroll:true});
}
function showFeatured(){
 const items=S.items.filter(i=>MARKET_SLOTS.includes(i.category)&&Object.hasOwn(COSMETIC_ART,i.key))
  .sort((a,b)=>RARITIES.indexOf(b.rarity)-RARITIES.indexOf(a.rarity)||a.name.localeCompare(b.name));
 const chosen=items.length?items[((S.market.featured%items.length)+items.length)%items.length]:null;
 const art=el("featuredArt"),button=el("featuredTry");
 if(!chosen){art.classList.add("hidden");art.removeAttribute("src");button.disabled=true;el("featuredPrev").disabled=true;el("featuredNext").disabled=true;txt("featuredIndex","");txt("featuredTitle","Winter collection");txt("featuredDetail","Catalogue unavailable.");txt("featuredCost","");txt("featuredRarity","Featured selection");button.dataset.item="";return}
 art.setAttribute("src",COSMETIC_ART[chosen.key]);art.classList.remove("hidden");art.alt=chosen.name;
 txt("featuredTitle",chosen.name);txt("featuredDetail",chosen.detail);
 txt("featuredRarity",chosen.rarity+" · "+chosen.category);el("featuredRarity").dataset.rarity=RARITIES.includes(chosen.rarity)?chosen.rarity:"Common";
 txt("featuredCost",chosen.cost===0?"Free to unlock":"✦ "+fmt(chosen.cost)+" Snowflakes");
 txt("featuredIndex",(((S.market.featured%items.length)+items.length)%items.length+1)+" / "+items.length+" · Curated display");
 button.dataset.item=chosen.key;button.disabled=false;el("featuredPrev").disabled=items.length<2;el("featuredNext").disabled=items.length<2;
}
function marketCard(i,w){
 const state=marketState(i,w),owned=["owned","equipped"].includes(state),art=Object.hasOwn(COSMETIC_ART,i.key)?COSMETIC_ART[i.key]:null;
 const rarity=RARITIES.includes(i.rarity)?i.rarity:"Common";
 const preview=S.market.preview[i.category]===i.key;
 const label=state==="equipped"?"Equipped":state==="owned"?"Owned":state==="unowned"?"Not owned":"Browse";
 const pending=owned?"equip":"buy",eligible=marketEligible(i,pending);
 const action=state==="equipped"?"Equipped":state==="owned"?"Equip":i.cost===0?"Unlock free":"Purchase · ✦ "+fmt(i.cost);
 const reason=eligible||state==="equipped"?"":!w?"Sign in or refresh your wardrobe":S.busy?"Action in progress":!S.catalogReady?"Refresh catalogue":pending==="buy"&&S.me.phase!=="live"?"Purchases open during the live event":pending==="buy"&&Number(w.balance)<i.cost?"Not enough Snowflakes":"Currently unavailable";
 return "<article class='catalog-card market-item' data-rarity='"+rarity+"' data-market-key='"+esc(i.key)+"' data-item-state='"+state+"'>"+
 "<div class='market-item-art'>"+(art?"<img class='catalog-thumb' src='"+art+"' loading='lazy' alt='"+esc(i.name)+" artwork'>":"<span>Artwork unavailable</span>")+"<span class='market-state'>"+label+"</span></div>"+
 "<span class='market-rarity' data-rarity='"+rarity+"'>"+esc(rarity)+" · "+esc(i.category)+"</span><h3>"+esc(i.name)+"</h3><p>"+esc(i.detail)+"</p>"+
 "<div class='catalog-row'><strong>"+(i.cost===0?"Free":"✦ "+fmt(i.cost))+"</strong></div><div class='market-card-actions'>"+
 "<button class='button button-outline' data-try='"+esc(i.key)+"' aria-pressed='"+String(preview)+"' "+(!art?"disabled":"")+">"+(preview?"✓ Previewing":"Try on")+"</button>"+
 "<button class='button button-gold' data-"+pending+"='"+esc(i.key)+"' "+(!eligible?"disabled":"")+">"+action+"</button></div>"+
 (reason?"<small class='subtle'>"+esc(reason)+"</small>":"")+"</article>";
}
function showShop(){
 syncMarketIdentity();
 const w=marketWardrobe();
 txt("shopBalance",w?fmt(w.balance):"—");
 const total=S.items.filter(i=>MARKET_SLOTS.includes(i.category)).length;
 const owned=w?S.items.filter(i=>["owned","equipped"].includes(marketState(i,w))).length:0;
 txt("marketOwned",w?owned+" / "+total+" cosmetics owned · "+MARKET_SLOTS.filter(slot=>ownedEquipped(w,slot)).length+" / 5 equipped":"Sign in or refresh to load your wardrobe");
 const filters=S.market,items=filterMarket(S.items,filters,w);
 txt("marketCount",!S.catalogReady?"Catalogue unavailable — refresh to try again.":items.length+" of "+total+" items");
 el("catalog").innerHTML=items.length?items.map(i=>marketCard(i,w)).join(""):"<p class='empty'>"+(!S.catalogReady?"Market unavailable.":filters.ownership!=="all"&&!w?"Sign in to view your personal collection.":"No items match these filters.")+"</p>";
 showFeatured();showFitting();
}
function marketAction(key,kind){
 const item=marketItem(key);
 if(!marketEligible(item,kind))return;
 if(kind==="buy"&&!window.confirm("Unlock "+item.name+" for "+item.cost+" Snowflakes? This does not equip the item."))return;
 act(async()=>{
  const path=kind==="buy"?"purchase":"equip";
  const r=await post("/v1/game/wardrobe/"+path,{item:key},true,kind==="buy");
  notice(r.message,"success");
 });
}
function updateCraftArtwork(){
 const key=el("craftChoice").value;
 const names={cocoa:"Hot Chocolate",fort:"Fort Kit",mittens:"Mittens",bomb:"Blizzard Bomb"};
 if(Object.hasOwn(names,key)){el("craftArtwork").src="/art/items/"+key+".png";el("craftArtwork").alt=names[key]+" artwork"}
}
async function loadPublic(){
 const results=await Promise.allSettled([get("/v1/game/leaderboard?limit=20"),get("/v1/game/cities"),get("/v1/game/catalog")]);
 if(results[0].status==="fulfilled")S.board=results[0].value.players||[];
 S.citiesReady=results[1].status==="fulfilled"&&Array.isArray(results[1].value.cities);
 if(S.citiesReady)S.cities=results[1].value.cities;
 S.catalogReady=results[2].status==="fulfilled"&&Array.isArray(results[2].value.items);
 S.items=S.catalogReady?results[2].value.items:[];
 showBoard();showCities();showBoss();showShop();
}
async function loadPrivate(){
 if(S.privatePending){S.privateQueued=true;return;}
 S.privatePending=true;updatePlayControls();
 try{await readPrivate();S.privateFresh=!!S.session&&!!S.me}catch(e){S.privateFresh=false;throw e}finally{S.privatePending=false;updateStreetsChat();showActivities();showArcade();updatePlayControls();if(S.privateQueued&&!S.busy){S.privateQueued=false;if(S.session)void loadPrivate().catch(e=>notice(e.message,"error"))}}
}
async function readPrivate(){
 syncPlayIdentity();
 if(!S.session){S.activities=null;showActivities();S.me=null;S.world=null;S.hq=null;S.shop=null;S.targetsReady=false;S.targets=[];S.progress=null;S.verification=null;S.pendingActions.clear();showMe();showShop();showTargets();showSiege();return}
 try{
  S.me=await get("/v1/game/me");
  if(String(S.me?.player_id)!==String(S.session?.player_id)){const err=Error("Account changed in another tab; sign in again");err.status=409;throw err}
 }
 catch(e){if(e.status===401||e.message==="Account changed in another tab; sign in again"){S.session=null;S.me=null;S.world=null;S.hq=null;S.shop=null;S.progress=null;S.targetsReady=false;S.targets=[];S.verification=null;showMe();showShop();showTargets();showSiege();return}throw e}
 if(S.me.registered){
  const results=await Promise.allSettled([get("/v1/game/world"),get("/v1/game/wardrobe"),get("/v1/game/targets"),get("/v1/game/progress"),get("/v1/game/headquarters"),el("page-activities")?.classList.contains("active")?get("/v1/game/activities"):Promise.resolve(null),el("page-arcade")?.classList.contains("active")?get("/v1/game/arcade"):Promise.resolve(null)]);
  if(results.some(r=>r.status==="rejected"&&(r.reason?.status===401||r.reason?.message==="Account changed in another tab; sign in again"))){
   S.session=null;return readPrivate();
  }
  S.world=results[0].status==="fulfilled"?results[0].value:null;
  S.shop=results[1].status==="fulfilled"?results[1].value:null;
  S.targetsReady=results[2].status==="fulfilled"&&Array.isArray(results[2].value.targets);
  S.targets=S.targetsReady?results[2].value.targets:[];
  S.progress=results[3].status==="fulfilled"?results[3].value:null;
  S.hq=results[4].status==="fulfilled"?results[4].value:null;
  S.activities=results[5]?.status==="fulfilled"?results[5].value:null;
  S.arcade=results[6]?.status==="fulfilled"?results[6].value:null;
  if(S.arcadeRun&&S.arcade&&String(S.arcade.player_id)===String(S.session.player_id)){
   if(S.arcadeRun.day!==S.arcade.day)S.arcadeRun=null;
   else try{S.arcadeRun=await get("/v1/game/arcade/session/"+encodeURIComponent(S.arcadeRun.session_id));reconcileArcadeMoves(S.arcadeRun)}
   catch{S.arcadeRun=null}
  }
  S.hqClock=Number.isFinite(Date.parse(S.hq?.server_time))?Date.parse(S.hq.server_time)-Date.now():0;
  const linked=(S.session.links||[]).some(x=>x.provider==="discord")&&
               (S.session.links||[]).some(x=>x.provider==="underworld");
  if(linked){
    try{S.verification=await get("/v1/verification/status")}
    catch{S.verification=null}
  }else S.verification=null;
 }else{S.shop=null;S.world=null;S.hq=null;S.progress=null;S.targetsReady=false;S.targets=[];S.verification=null;}
 showMe();showTargets();showBoss();showShop();showCities();showActivities();showArcade();
 if(el("page-arcade")?.classList.contains("active")&&hubAllowed())void loadArcadeHub();
 void refreshStaffAccess();
}
function updateDiscardSubmit(){
 el("discardConfirm").disabled=!S.discard||!el("discardAcknowledge").checked||
     el("discardPhrase").value!=="DISCARD DISCORD CHARACTER"||S.busy;
}
function hideDiscardOffer(){
 el("discordDiscardPanel").classList.add("hidden");S.discard=null;
 el("discardPhrase").value="";el("discardAcknowledge").checked=false;
 updateDiscardSubmit();
}
async function loadDiscardOffer(){
 const offer=await get("/v1/auth/discord/discard/preview");
 if(!S.session?.links?.some(x=>x.provider==="underworld"))throw Error("Sign in with Underworld to keep the correct character.");
 S.discard=offer;
 txt("discardKeepName",offer.keep.name);
 txt("discardKeepDetails",(offer.keep.city?offer.keep.city+" · ":"")+
    "Your Underworld player and all its progress are retained. Player ID: "+offer.keep.player_id);
 txt("discardOldName",offer.discard.name);
 txt("discardOldDetails",offer.discard.city+" · "+fmt(offer.discard.score)+" points · "+
    fmt(offer.discard.snowflakes)+" Snowflakes · "+
    fmt(offer.discard.snowballs)+" snowballs · "+fmt(offer.discard.warmth)+" warmth · "+
    fmt(offer.discard.cosmetic_unlocks)+" cosmetics unlocked · "+
    fmt(offer.discard.pvp_attacks)+" PvP attacks · "+fmt(offer.discard.boss_attacks)+" NPC attacks.");
 const owned=Object.entries(offer.discard.inventory||{}).filter(([,qty])=>qty>0)
     .map(([name,qty])=>name+" ×"+qty);
 txt("discardInventory","Inventory that will not transfer: "+(owned.length?owned.join(", "):"no stored items"));
 txt("discardWarning",offer.warning);
 el("discardPhrase").value="";el("discardAcknowledge").checked=false;
 el("discordDiscardPanel").classList.remove("hidden");
 updateDiscardSubmit();
 notice("Choose carefully: your separate Discord character will be retired only if you confirm.","error");
}
async function refresh(){await Promise.all([loadPublic(),loadPrivate()]);await Promise.all([refreshBossVisual(),refreshTerritory(),refreshWire()]);showEvent()}
async function resume(){try{S.session=await get("/v1/auth/session")}catch(e){if(e.status!==401)throw e;S.session=null}await refresh()}
async function act(fn){
 if(S.busy||S.privatePending)return;
 if(!S.session)return authModal();
 S.busy=true;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=true);updatePlayControls();
 try{
  el("playFeedback").classList.add("hidden");
  await fn();
  try{await refresh()}catch(e){S.privateFresh=false;playFeedback("Action recorded. Refresh to see updated resources.", "warning");notice("Action recorded; refresh failed.","error")}
 }catch(e){playFeedback(e.message,"error");notice(e.message,"error");if(S.lastThrow&&S.pendingActions.has(requestKey("/v1/game/throw",S.lastThrow.body)))showTargets()}

 finally{S.busy=false;document.querySelectorAll(".actions-inline button,.craft-card button").forEach(b=>b.disabled=false);showBoss();showShop();showActivities();showArcade();updatePlayControls();if(S.privateQueued&&!S.privatePending){S.privateQueued=false;if(S.session)void loadPrivate().catch(e=>notice(e.message,"error"))}}
}
function registered(){
 if(!S.session){authModal();return false}
 if(!hasPlayIdentity(S.session,S.config)){section("home");notice("Continue through Underworld first.","error");return false}
 if(S.me?.registered)return true;
 section("home");notice("Create your character at Headquarters first.","error");return false;
}
// Local presentation preference only.
function motionEnabled(){
 return document.documentElement?.dataset.atmosphere!=="off"&&!window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}
function setupAtmosphere(){
 let off=false;
 try{off=localStorage.getItem("snowfall-atmosphere")==="off"}catch{}
 const media=window.matchMedia("(prefers-reduced-motion: reduce)");
 const update=()=>{
  document.documentElement.dataset.atmosphere=off?"off":"on";
  const enabled=!off&&!media.matches;
  el("atmosphereToggle").setAttribute("aria-pressed",String(enabled));
  txt("atmosphereToggle",media.matches?"Motion reduced by system":enabled?"Atmosphere on":"Atmosphere off");
  el("atmosphereToggle").disabled=media.matches;
 };
 el("atmosphereToggle").onclick=()=>{off=!off;try{localStorage.setItem("snowfall-atmosphere",off?"off":"on")}catch{}update()};
 media.addEventListener?.("change",update);update();
}
function eventPresentation(wire,raid,stale=false){
 const phase=wire?.phase||(!stale?raid?.season_phase:null)||"unknown";
 const ended=["closed","finalized"].includes(phase);
 const defeated=raid?.state==="defeated"&&!stale&&(!wire?.current_day||wire.current_day===raid.day);
 return {phase,ended,defeated,kind:ended?phase:phase==="paused"?"paused":defeated?"raid":"normal"};
}
function showEvent(){
 const e=eventPresentation(S.wireStale?null:S.wire,S.raid,S.bossStale);
 const phaseLabels={not_open:"NOT OPEN",registration:"REGISTRATION",ready:"AWAITING START",live:"LIVE",paused:"PAUSED",closed:"CLOSED",finalized:"FINALIZED",unknown:"—"};
 txt("phaseValue",phaseLabels[e.phase]||"—");
 if(!el("eventFinale"))return;
 if(S.connection==="ready"){
  const stale=S.wireStale||S.bossStale||S.territoryStale;
  txt("eventConnectionText",stale?"Some live data could not refresh. Last known status may be shown.":"Connected to shared staging game · "+(phaseLabels[e.phase]||"checking status"));
  el("eventRetry").classList.toggle("hidden",!stale);
 }
 const finale=el("eventFinale"),art=el("finaleArt");
 finale.classList.toggle("hidden",e.kind==="normal");
 finale.dataset.kind=e.kind;
 if(e.kind==="normal"){art.removeAttribute("src")}
 else{
  const src=e.ended?"/art/v290/wire/backgrounds/final_day_edition.png":e.kind==="raid"?"/art/v290/boss/raid_celebration.webp":"/art/v290/wire/backgrounds/newsroom_editorial.png";
  if(art.getAttribute("src")!==src)art.src=src;
  art.alt=e.ended?"Original final-day newspaper artwork":e.kind==="raid"?"Original raid celebration":"Original newsroom artwork";
  txt("finaleKicker",e.ended?"SEVEN-DAY SEASON / ARCHIVE":e.kind==="raid"?"DAILY RAID VICTORY":"EVENT PAUSED");
  txt("eventFinaleTitle",e.kind==="finalized"?"The final edition":e.kind==="closed"?"The streets fall quiet":e.kind==="raid"?"The Snow Don has fallen":"The streets are on hold");
  txt("finaleText",e.kind==="finalized"?"The season is finalized. Explore verified editions and standings. This QA event awards no prizes.":e.kind==="closed"?"The seven-day playing window has closed. Review the standings and newspaper while official finalization is pending.":e.kind==="raid"?"Today's shared boss is defeated. This is a daily raid victory, not the end of the season. The usual event rules still apply.":"The event clock is paused. Resume timing is controlled by the host; browse existing records.");
 }
 el("raidCelebration").classList.toggle("hidden",!e.defeated);
 if(e.defeated)txt("raidCelebrationText","Day "+(S.raid.day||"—")+" · "+fmt(S.raid.contributors)+" contributors · "+fmt(S.raid.hit_count)+" shared hits. "+(e.ended?"Season archive.":"The frozen echo follows the existing game rules."));
 if(e.ended){txt("bossActionText","The event is closed. Raid results are available for review; no further attacks are allowed.");txt("heroPlay","View event records")}
 else txt("heroPlay",S.me?.registered?"Play now ↗":"Enter the event ↗");
 updatePlayControls();
}
function wireHeadlineMarkup(h){
 return "<article class='wire-story'><p class='wire-byline'>"+esc(h.category)+"</p><h4>"+esc(h.title)+"</h4><p>"+esc(h.detail)+"</p></article>";
}
const WIRE_SLOTS=Object.freeze([["streets","Combat"],["boss","Boss"],["cities","Cities"],["community","Community"]]);
function wireSlots(heads){
 return WIRE_SLOTS.map(([key,category])=>heads.find(h=>h?.key===key)||{key,category,title:"Awaiting dispatch",detail:"No verified report for this edition yet."});
}
function showWire(){
 const w=S.wire,heads=Array.isArray(w?.headlines)?w.headlines:[],lead=heads.find(h=>h?.key==="lead");
 const kind=!w?.day?"waiting":w.complete&&w.day===7?"final":w.complete?"archive":"live";
 el("wirePaper").dataset.edition=kind;
 const select=el("wireDay");
 select.innerHTML='<option value="current">Latest edition</option>'+ (w?.available_days||[]).filter(d=>Number.isInteger(d)&&d>=1&&d<=7).map(d=>'<option value="'+d+'">Day '+d+'</option>').join("");
 select.value=S.wireDay;select.disabled=S.wirePending;
 txt("wireEdition",w?.day?"DAY "+w.day+" / 7 · "+(w.complete?"ARCHIVE": "LIVE DISPATCH"):"AWAITING KICKOFF");
 txt("wireTheme",w?.theme||"THE WINTER UNDERWORLD");
 txt("wireLead",lead?.title||"The streets are waiting");txt("wireLeadDetail",lead?.detail||"Verified dispatches appear once the event opens.");
 el("wireHeadlines").innerHTML=wireSlots(heads).map(wireHeadlineMarkup).join("");
 txt("wireNotice",S.wireStale?"Refresh unavailable — "+(w?"last known edition shown.":"no edition loaded."):w?.day?w.complete?"Historical ledger dispatch · review-cleared records as of this refresh. Not a prize announcement.":"Live figures may change until the day closes.":"No edition has opened yet.");
 txt("wireSideTitle",lead?.title||"Special bulletin");
 txt("wireSideDetail",(w?.day?"Day "+w.day+" · ":"")+(lead?.detail||"Verified dispatches from the shared game."));
}
async function refreshWire(){
 const seq=++S.wireRequest,chosen=S.wireDay;S.wirePending=true;el("wireDay").disabled=true;
 try{
  const w=await get("/v1/web/wire"+(chosen==="current"?"":"?day="+encodeURIComponent(chosen)));
  if(seq!==S.wireRequest)return;
  if(w?.verified_only!==true||!Array.isArray(w.headlines)||!Array.isArray(w.available_days))throw Error("Invalid edition");
  S.wire=w;S.wireStale=false;
 }catch{
  if(seq!==S.wireRequest)return;
  S.wireStale=true;
  if(chosen!=="current"&&String(S.wire?.day)!==chosen)S.wireDay=S.wire?.day?String(S.wire.day):"current";
 }finally{if(seq===S.wireRequest){S.wirePending=false;showWire();showEvent()}}
}
function bind(){
 bindActivities();bindArcade();
 if(el("communityRefresh"))el("communityRefresh").onclick=()=>void refreshCommunity();
 if(el("staffRefresh"))el("staffRefresh").onclick=()=>void refreshStaffDashboard();
 if(el("staffPlayerSearchForm"))el("staffPlayerSearchForm").onsubmit=e=>{e.preventDefault();void refreshStaffDirectory(1)};
 if(el("staffPlayerPrev"))el("staffPlayerPrev").onclick=()=>void refreshStaffDirectory(Math.max(1,(S.staffDirectory?.page||1)-1));
 if(el("staffPlayerNext"))el("staffPlayerNext").onclick=()=>void refreshStaffDirectory((S.staffDirectory?.page||1)+1);
 if(el("staffPlayerResults"))el("staffPlayerResults").onclick=e=>{const b=e.target.closest("button[data-player-id]");if(b)void inspectStaffPlayer(b.dataset.playerId)};
 if(el("staffReviewForm"))el("staffReviewForm").onsubmit=e=>{e.preventDefault();void submitStaffReview()};
 if(el("staffReviewAction"))el("staffReviewAction").onchange=()=>showStaffPlayerDesk();
 if(el("staffPlayerExport"))el("staffPlayerExport").onclick=downloadStaffPlayerDossier;
 if(el("staffLabRefresh"))el("staffLabRefresh").onclick=()=>void refreshStaffLab();
 if(el("staffLabExport"))el("staffLabExport").onclick=downloadLabResults;
 for(const btn of document.querySelectorAll("[data-lab-action]"))btn.onclick=()=>void staffLabAction(btn.dataset.labAction);
 for(const btn of document.querySelectorAll("[data-staff-copy]"))btn.onclick=()=>navigator.clipboard.writeText(btn.dataset.staffCopy).then(()=>notice("Discord command copied.","success")).catch(()=>notice("Clipboard permission required.","error"));
 if(el("staffExportDiagnostics"))el("staffExportDiagnostics").onclick=downloadStaffDiagnostics;
 if(el("streetsChatEnable"))el("streetsChatEnable").onclick=openStreetsChat;
 if(el("streetsChatDisconnect"))el("streetsChatDisconnect").onclick=disconnectStreetsChat;
 for(const btn of document.querySelectorAll("[data-chat-open],#streetsChatLauncher"))btn.addEventListener("click",()=>{closeNavigationMenus();openStreetsDock()});
 if(el("streetsChatClose"))el("streetsChatClose").onclick=()=>closeStreetsDock();
 if(el("streetsChatBackdrop"))el("streetsChatBackdrop").onclick=()=>closeStreetsDock();
 document.addEventListener("keydown",e=>{if(e.key==="Escape"&&S.streetsDrawerOpen)closeStreetsDock()});
 window.addEventListener("resize",()=>{if(S.streetsDrawerOpen&&!window.matchMedia("(max-width:980px)").matches)closeStreetsDock(false)});
 document.querySelectorAll("[data-nav]").forEach(b=>b.addEventListener("click",()=>section(b.dataset.nav)));
 for(const group of document.querySelectorAll(".nav-group")){
  const trigger=group.querySelector(".nav-group-trigger");
  if(!trigger)continue;
  trigger.addEventListener("click",()=>{
   const expand=trigger.getAttribute("aria-expanded")!=="true";
   closeNavigationMenus({mobile:false});
   group.classList.toggle("open",expand);
   trigger.setAttribute("aria-expanded",String(expand));
  });
  trigger.addEventListener("keydown",event=>{
   if(event.key==="ArrowDown"){
    event.preventDefault();
    if(trigger.getAttribute("aria-expanded")!=="true")trigger.click();
    group.querySelector(".nav-popover .nav-item:not(.hidden)")?.focus();
   }
  });
 }
 document.addEventListener("click",event=>{
  if(event.target?.closest?.(".nav-group")||event.target?.closest?.("#menuToggle"))return;
  // Clicking anywhere outside the header dismisses a mobile menu as well.
  const outsideHeader=!event.target?.closest?.(".topbar");
  closeNavigationMenus({mobile:outsideHeader});
 });
 document.addEventListener("keydown",event=>{
  if(event.key==="Escape"&&(el("primaryNav")?.classList.contains("open")||document.querySelector(".nav-group.open"))){
   event.preventDefault();closeNavigationMenus({restoreFocus:true});
  }
 });
 window.addEventListener("resize",()=>{
  if(!window.matchMedia("(max-width:1200px)").matches){
   closeNavigationMenus();
  }
  fitVisibleBannerNames();
 });
 document.querySelectorAll("[data-jump]").forEach(b=>b.addEventListener("click",()=>el(b.dataset.jump)?.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"})));
 window.addEventListener("popstate",()=>section(location.hash.startsWith("#play-")?location.hash.slice(6):"home",{record:false}));
 el("playPrimary").onclick=()=>{const dest=el("playPrimary").dataset.destination||"boss";if(dest==="account"){el("accountTools").open=true;el("accountTools").scrollIntoView({block:"start"})}else section(dest)};
 el("playRefresh").onclick=()=>{if(!S.busy&&!S.privatePending)void loadPrivate().catch(e=>{playFeedback(e.message,"error");notice(e.message,"error")})};
 el("playFeedbackClose").onclick=()=>el("playFeedback").classList.add("hidden");
 el("targetSelect").onchange=()=>{S.chosenTarget=true;updatePlayControls()};
 el("throwStyle").onchange=updatePlayControls;
 el("menuToggle").onclick=()=>{
  const open=!el("primaryNav").classList.contains("open");
  closeNavigationMenus();
  if(open)el("primaryNav").classList.add("open");
  el("menuToggle").setAttribute("aria-expanded",String(open));
 };
 document.querySelectorAll(".nav-item").forEach(b=>b.setAttribute("aria-pressed",String(b.classList.contains("active"))));
 reflectNavigationGroup("home");
 el("heroPlay").onclick=()=>eventPresentation(S.wireStale?null:S.wire,S.raid,S.bossStale).ended?section("wire"):S.session?section("home"):authModal();
 el("wireDay").onchange=()=>{S.wireDay=el("wireDay").value;void refreshWire()};
 el("refreshWire").onclick=()=>{if(!S.wirePending)void refreshWire()};
 el("eventRetry").onclick=()=>{if(S.connection==="offline")location.reload();else void refresh().catch(e=>notice(e.message,"error"))};
 el("hqRecommended").onclick=()=>{const dest=el("hqRecommended").dataset.destination;if(dest==="missions")el("hqMissions").scrollIntoView({block:"start"});else if(dest)section(dest)};
 el("loginCTA").onclick=authModal;el("closeAuth").onclick=closeAuth;
 el("authDialog").onclick=e=>{if(e.target===el("authDialog"))closeAuth()};
 document.addEventListener("keydown",e=>{
  if(el("authDialog").classList.contains("hidden"))return;
  if(e.key==="Escape"){closeAuth();return}
  if(e.key==="Tab"){
   const items=Array.from(el("authDialog").querySelectorAll("button,a[href],input,select,textarea,summary")).filter(n=>!n.disabled&&n.getClientRects().length);
   if(!items.length)return;
   if(e.shiftKey&&document.activeElement===items[0]){e.preventDefault();items.at(-1).focus()}
   else if(!e.shiftKey&&document.activeElement===items.at(-1)){e.preventDefault();items[0].focus()}
  }
 });
 el("authToggle").onclick=()=>{if(!S.session)return authModal();act(async()=>{await post("/v1/auth/logout",{},true);S.session=null;S.me=null;S.pendingActions.clear();notice("Signed out.","success")})};
 el("demoForm").onsubmit=async e=>{
  e.preventDefault();let b=e.target.querySelector("button");b.disabled=true;
  try{
   await post("/v1/auth/demo",{code:el("demoCode").value,slot:Number(el("demoSlot").value)},false);
   S.session=await get("/v1/auth/session");
   el("demoCode").value="";closeAuth();await refresh();notice("Signed in to isolated staging.","success");
  }catch(x){notice(x.message,"error")}finally{b.disabled=false}
 };
 el("underworldForm").onsubmit=async e=>{
  e.preventDefault();
  try{await post("/v1/auth/underworld",{assertion:el("underworldAssertion").value},false);S.session=await get("/v1/auth/session");el("underworldAssertion").value="";closeAuth();await refresh();notice("Underworld assertion verified.","success")}
  catch(x){notice(x.message,"error")}
 };
 el("refreshShared").onclick=async()=>{
  if(!S.session)return authModal();
  try{
   if(S.busy||S.privatePending)return;
   S.session=await get("/v1/auth/session");
   await loadPrivate();
   if(!S.progress?.registered)throw Error("Shared progress could not be verified. Refresh and try again.");
   notice("Progress verified against the authoritative PostgreSQL game.","success");
  }catch(e){notice(e.message,"error")}
 };
 el("verificationStart").onclick=()=>{
   if(!registered())return;
   act(async()=>{
     S.verification=await post("/v1/verification/start",{},true);
     showVerification();
     notice("Baseline saved. Now run /snowbridge verify in Discord.","success");
   });
 };
 el("verificationCheck").onclick=async()=>{
   try{await refresh();notice("Checked canonical progress and Discord receipts.","success")}
   catch(e){notice(e.message,"error")}
 };
 el("discardAcknowledge").onchange=updateDiscardSubmit;
 el("discardPhrase").oninput=updateDiscardSubmit;
 el("discardForm").onsubmit=e=>{
  e.preventDefault();
  if(el("discardConfirm").disabled||!S.discard)return;
  act(async()=>{
   const result=await post("/v1/auth/discord/discard/confirm",{
     acknowledged_loss:el("discardAcknowledge").checked,
     confirmation:el("discardPhrase").value
   },true);
   hideDiscardOffer();
   S.session=await get("/v1/auth/session");
   notice("Discord login now opens your Underworld character. "+
     "The separate Discord character was retired without transferring its progress.","success");
   if(!result.linked)throw Error("Replacement was not verified");
  });
 };
 el("discardCancel").onclick=()=>{
  if(!S.session)return hideDiscardOffer();
  act(async()=>{
   await post("/v1/auth/discord/discard/cancel",{},true);
   hideDiscardOffer();
   notice("Cancelled. Both characters are unchanged.");
  });
 };
 el("linkDiscord").onclick=async()=>{
  if(!S.session)return authModal();
  try{
   const r=await post("/v1/auth/discord/start",{mode:"link"},true);
   if(!r.authorize_url?.startsWith("https://discord.com/"))throw Error("Unexpected OAuth destination");
   location.assign(r.authorize_url);
  }catch(e){notice(e.message,"error")}
 };
 el("discordLogin").onclick=async()=>{
  try{const r=await post("/v1/auth/discord/start",{mode:"login"},false);if(!r.authorize_url?.startsWith("https://discord.com/"))throw Error("Unexpected OAuth destination");location.assign(r.authorize_url)}
  catch(x){notice(x.message,"error")}
 };
 el("registerForm").onsubmit=e=>{
  e.preventDefault();if(!hasPlayIdentity(S.session,S.config))return notice("Continue through Underworld first.","error");act(async()=>{
   const r=await post("/v1/game/register",{mr_username:el("characterName").value.trim(),city:el("cityChoice").value},true);
   notice("Welcome to "+r.city+", "+r.mr_username+"!","success");
  });
 };
 el("readyButton").onclick=()=>{if(registered())act(async()=>{await post("/v1/game/ready",{},true);notice("You are ready to be targeted.","success")})};
 el("findTargets").onclick=()=>{if(registered()&&!S.busy&&!S.privatePending)void loadPrivate().then(()=>notice(S.targetsReady?"Rival list refreshed.":"Rivals are unavailable right now.")).catch(e=>notice(e.message,"error"))};
 el("throwButton").onclick=()=>{
  if(!registered())return;
  let target=el("targetSelect").value;
  if(!target)return notice("Select a rival first.","error");
  const body={target_player_id:target,style:el("throwStyle").value};
  if(S.lastThrow&&S.pendingActions.has(requestKey("/v1/game/throw",S.lastThrow.body))&&JSON.stringify(body)!==JSON.stringify(S.lastThrow.body))return notice("Retry the previous throw first.","error");
  const chosen=S.targets.find(t=>String(t.player_id)===target)||S.lastThrow?.target;
  S.lastThrow={body,target:chosen};
  act(async()=>{const r=await post("/v1/game/throw",body,true,true);showCombatOutcome(r,chosen);notice(r.hit?"Direct hit! +"+r.points_awarded+" points.":"Snowball missed.",r.hit?"success":"")});
 };
 for(const kind of ["boss","siege"]){
  el(kind==="boss"?"bossButton":"siegeButton").onclick=()=>{
   if(!registered())return;
   act(async()=>{let r=await post("/v1/game/"+kind,{},true,true);if(kind==="boss")showBossRecap(r);else showSiegeOutcome(r);notice(r.hit?"Hit! "+r.damage+" damage and "+r.points+" points.":"Shot missed.",r.hit?"success":"")});
  };
 }
 el("craftButton").onclick=()=>{if(registered())act(async()=>{let r=await post("/v1/game/craft",{item:el("craftChoice").value},true,true);notice(r.text||"Crafted.","success")})};
 for(const [id,key] of Object.entries(MARKET_FIELDS)){
  const control=el(id);
  control.addEventListener(id==="marketSearch"?"input":"change",()=>{S.market[key]=control.value;showShop()});
 }
 el("marketClear").onclick=()=>{
  for(const [id,key] of Object.entries(MARKET_FIELDS)){const value=key==="search"?"":key==="sort"?"catalogue":"all";S.market[key]=value;el(id).value=value}
  showShop();
 };
 el("featuredPrev").onclick=()=>{S.market.featured--;showFeatured()};
 el("featuredNext").onclick=()=>{S.market.featured++;showFeatured()};
 el("featuredTry").onclick=()=>{if(tryMarketItem(el("featuredTry").dataset.item))focusFitting()};
 el("fitReset").onclick=()=>{S.market.preview={};showShop()};
 el("fitBrowse").onclick=()=>el("marketCatalogue").scrollIntoView({block:"start"});
 el("fitChanges").onclick=e=>{
  const b=e.target.closest("button");if(!b||b.disabled)return;
  if(MARKET_SLOTS.includes(b.dataset.fitRemove)){delete S.market.preview[b.dataset.fitRemove];showShop();el("fittingTitle").focus()}
  else if(["buy","equip"].includes(b.dataset.fitAction))marketAction(b.dataset.item,b.dataset.fitAction);
 };
 el("craftChoice").onchange=()=>{updateCraftArtwork();updatePlayControls()};
 el("catalog").onclick=e=>{
  const b=e.target.closest("button");if(!b||b.disabled)return;
  if(b.dataset.try){if(tryMarketItem(b.dataset.try))focusFitting();return}
  if(b.dataset.buy)marketAction(b.dataset.buy,"buy");
  else if(b.dataset.equip)marketAction(b.dataset.equip,"equip");
 };
 el("cityMapOverlay").onclick=e=>{
  const pin=e.target.closest("[data-map-city]");
  if(pin&&knownCity(pin.dataset.mapCity)){S.citySelected=pin.dataset.mapCity;showCities()}
 };
 el("territoryDay").onchange=()=>{S.territoryDay=el("territoryDay").value;void refreshTerritory()};
 el("refreshTerritory").onclick=()=>{if(!S.territoryPending&&!S.busy)void Promise.all([refreshTerritory(),refreshCityStandings()])};
 for(const id of ["citySelectors","cityStandings"])el(id).onclick=e=>{const b=e.target.closest("button[data-city]");if(b&&knownCity(b.dataset.city)){S.citySelected=b.dataset.city;showCities();if(id==="cityStandings")el("cityWarRoom").scrollIntoView({block:"start"});else el("citySelectors").querySelector("[aria-pressed=true]")?.focus({preventScroll:true})}};
 for(const id of ["refreshHome","refreshBoss","refreshShop","refreshSiege"]){el(id).onclick=()=>refresh().then(()=>notice("Game state refreshed.")).catch(e=>notice(e.message,"error"))}
}
async function init(){
 bind();setupAtmosphere();
 try{
  let [cfg,health]=await Promise.all([get("/v1/web/config"),get("/v1/health")]);
  S.config=cfg;configureUnderworld(cfg.underworld_url);configureBranding(cfg.branding);configureStreets(cfg.streets_url);el("discordLogin").disabled=!cfg.discord_oauth;
  if(!cfg.discord_oauth)el("discordLogin").textContent="Discord login (not configured)";
  if(!cfg.underworld_assertions)el("underworldForm").querySelector("button").disabled=true;
  txt("sideStatus",(health.status||"unknown").toUpperCase());txt("sideStatusDetail","Isolated staging · "+cfg.season);
  await resume();await refreshStaffAccess({force:true});S.connection="ready";showEvent();
  if(!location.search.includes("discord=")){
    if(location.hash.startsWith("#play-"))section(location.hash.slice(6),{record:false,focus:false});
    else if(location.search.includes("login=ok")&&S.staffAllowed)section("staff",{record:false,focus:false});
    else if(S.me?.registered)section("home",{record:false,focus:false});
  }
  const poll=()=>{
   if(document.hidden||S.busy||S.privatePending)return;
   if(!S.bossPending)void refreshBossVisual();
   if(el("page-cities").classList.contains("active")&&!S.territoryPending&&S.territoryDay==="current")void Promise.all([refreshTerritory(),refreshCityStandings()]);
   if(!S.wirePending)void refreshWire();
   if(el("page-community").classList.contains("active"))void refreshCommunity();
   if(S.session)void refreshStaffAccess();
   if(S.staffAllowed&&el("page-staff").classList.contains("active")){void refreshStaffDashboard();void refreshStaffLab()}
   if(S.session&&["home","combat","boss","cities","activities","arcade"].some(name=>el("page-"+name).classList.contains("active"))&&!document.activeElement?.matches("input,select,textarea")&&el("authDialog").classList.contains("hidden"))
    void loadPrivate().catch(()=>{});
  };
  setInterval(poll,30000);document.addEventListener("visibilitychange",poll);
  setInterval(()=>{if(!document.hidden){updateHqTimers();updatePlayControls()}},1000);
  if(location.search.includes("login=ok"))notice("Discord login successful.","success");
  if(location.search.includes("linked=discord"))notice("Discord account linked to this character.","success");
  if(location.search.includes("discord=discard-offer")){
    el("accountTools").open=true;
    try{await loadDiscardOffer()}
    catch(e){notice("Cannot load Discord character confirmation: "+e.message,"error")}
  }
  if(location.search.includes("discord=conflict")){
    el("accountTools").open=true;
    const reason=new URLSearchParams(location.search).get("reason")||"manual-review";
    const explanations={
      "gameplay":"That Discord login already has its own registered Snowfall player. For safety, its game progress cannot be automatically merged with your Underworld character.",
      "activity":"That Discord login already has recorded Snowfall activity, such as rewards or event history. A manual review is required before linking.",
      "linked-elsewhere":"That Discord account is already connected to a different Underworld character. Snowfall will not transfer it automatically.",
      "character-occupied":"This Underworld character already has a different Discord account connected.",
      "reserved":"That Discord account has a previously reserved identity requiring manual review.",
      "underworld-required":"Sign into Snowfall through Underworld first, then use Link Discord account.",
      "manual-review":"The link could not be completed safely. No accounts or progress were changed."
    };
    const explanation=explanations[reason]||explanations["manual-review"];
    const details=el("linkConflictDetail");
    if(details){details.textContent=explanation;details.classList.remove("hidden")}
    notice(explanation,"error");
  }
  if(location.search.includes("linked=discord")||location.search.includes("discord=conflict")||location.search.includes("discord=discard-offer"))
    history.replaceState(null,"",location.pathname+location.hash);
 }catch(e){S.connection="offline";txt("eventConnectionText","Connection unavailable. Retry to reconnect.");el("eventRetry").classList.remove("hidden");txt("sideStatus","OFFLINE");txt("sideStatusDetail",e.message);notice("Staging service unavailable: "+e.message,"error")}
}
document.addEventListener("DOMContentLoaded",init);

/* v2.9.8 — server-authoritative player activities. */
function activityButton(action,item,label,disabled=false){
 return "<button type='button' class='button button-outline' data-activity='"+esc(action)+"' data-item='"+esc(item)+"'"+(disabled?" disabled":"")+">"+esc(label)+"</button>";
}
function activityCard(title,body,art=""){
 return "<article class='activity-card'>"+(art?"<img class='activity-art' src='"+esc(art)+"' alt='' loading='lazy'>":"")+"<h3>"+esc(title)+"</h3>"+body+"</article>";
}
function showActivities(){
 const root=el("activitiesContent");if(!root)return;
 const a=S.session&&S.me?.registered&&String(S.activities?.player_id)===String(S.session.player_id)?S.activities:null;
 const locked=!!(S.busy||S.privatePending||!S.privateFresh||a?.phase!=="live"||!hasPlayIdentity(S.session,S.config));
 txt("activitiesStatus",!S.session?"Sign in to open your dossier.":!S.me?.registered?"Register at Headquarters first.":!a?"Refresh to load today's activities.":("Day "+(a.day??"—")+" / 7 · "+String(a.phase).toUpperCase()+" · Shared with Discord"));
 if(!a){root.innerHTML="";return}
 const list=Array.isArray(a.quests)?a.quests:[];
 const quests=list.map(q=>"<div class='activity-line'><div><strong>"+esc(q.name)+"</strong><p>"+fmt(q.progress)+" / "+fmt(q.target)+(q.claimed?" · Claimed":"")+"</p></div>"+activityButton("quest",q.key,q.claimed?"Claimed":"Claim reward",locked||q.claimed||Number(q.progress)<Number(q.target))+"</div>").join("");
 const gifts="<p>Daily present: "+esc(a.daily_gift)+" · Bonus: "+esc(a.bonus_gift)+"</p><div class='activity-actions'>"+activityButton("gift","daily","Open daily present",locked||a.daily_gift!=="Ready")+activityButton("gift","bonus","Open bonus present",locked||a.bonus_gift!=="Ready")+"</div>";
 const inv=a.inventory||{};
 const items=["cocoa","fort","mittens","bomb","golden"].map(k=>{
  const n=Number(inv.quantities?.[k]||0),used=Number(inv.uses_today?.[k]||0),cap=Number(a.use_caps?.[k]||0);
  return "<div class='activity-line'><div><strong>"+esc(a.item_names?.[k]||k)+" × "+fmt(n)+"</strong><p>"+(k==="golden"?"Use through Snowball Alley":used+" / "+cap+" used today")+"</p></div>"+(k==="golden"?"":activityButton("use",k,"Use",locked||n<1||used>=cap))+"</div>";
 }).join("");
 const guard="<p>Guard: "+(inv.guard_active?"Active":"Inactive")+" · Armour: "+fmt(inv.armour_hp)+" · Mittens: "+(inv.mittens_armed?"Armed":"Not armed")+" · Bomb: "+(inv.bomb_armed?"Armed":"Not armed")+"</p>"+activityButton("guard",inv.guard_active?"off":"on",inv.guard_active?"Lower guard":"Activate guard",locked);
 const titles="<p>Equipped: "+esc(a.equipped_title)+"</p><div class='activity-actions'>"+activityButton("title","none","Default title",S.busy||S.privatePending||!S.privateFresh||!hasPlayIdentity(S.session,S.config))+(a.titles||[]).map(t=>activityButton("title",t.key,t.label,S.busy||S.privatePending||!S.privateFresh||!hasPlayIdentity(S.session,S.config)||t.label===a.equipped_title)).join("")+"</div>";
 const c=a.case,e=a.encounter;
 let caseBody="<p>Today's case is not open.</p>";
 if(c){
  const clues=(c.clues||[]).map(x=>"<div class='activity-line'><div><strong>"+esc(x.label)+"</strong><p>"+esc(x.found?x.text:"Evidence not yet examined")+"</p></div>"+activityButton("clue",x.key,x.found?"Found":"Investigate",locked||x.found)+"</div>").join("");
  const count=(c.clues||[]).filter(x=>x.found).length;
  caseBody="<p>"+esc(c.scene)+"</p>"+clues+"<p>"+(c.solved?"Case closed":c.locked?"No accusations remain":fmt(c.guesses)+" / "+fmt(c.max_guesses)+" accusations used · Find two clues first")+"</p>"+(c.conclusion?"<p>"+esc(c.conclusion)+"</p>":"")+"<div class='activity-actions'>"+(c.suspects||[]).map(x=>activityButton("accuse",x.key,x.label,locked||count<2||c.solved||c.locked)).join("")+"</div>";
 }
 const dayArt=Number.isInteger(a.day)&&a.day>=1&&a.day<=7?"/art/v290/mysteries/day_"+a.day+".webp":"/art/v290/mysteries/classified_dossier.webp";
 const encounter=e?"<p>"+esc(e.scene)+"</p>"+(e.completed?"<p>Collected: "+esc(e.completed.souvenir)+"</p>":"<div class='activity-actions'>"+(e.choices||[]).map(x=>activityButton("encounter",x.key,x.label,locked)).join("")+"</div>"):"<p>Available once the event opens.</p>";
 const secret=c?.secret?"<p>"+esc(c.secret.scene)+"</p><p>Collected: "+esc(c.secret.souvenir)+"</p>":c?.secret_ready?"<p>"+esc(c.secret_title)+" · "+esc(c.secret_scene)+"</p><div class='activity-actions'>"+(c.secret_choices||[]).map(x=>activityButton("secret",x.key,x.label,locked)).join("")+"</div>":"<p>Find two clues and earn daily points or complete today's surprise encounter.</p>";
 const history=(a.history||[]).map(x=>"<div class='activity-line'><div><strong>Day "+fmt(x.day)+" · "+esc(x.title)+"</strong><p>"+fmt(x.clues)+" / 3 clues · "+(x.solved?"Solved":"Unsolved")+(x.secret?" · "+esc(x.secret):"")+"</p></div></div>").join("")||"<p>No case history yet.</p>";
 root.innerHTML=activityCard("Daily assignments & presents",quests+gifts)+activityCard("Inventory & protection",items+guard)+activityCard(c?.title||"Christmas mysteries",caseBody,dayArt)+activityCard(e?.title||"Surprise encounter",encounter)+activityCard("Secret encounter",secret,"/art/v290/mysteries/secret_encounter.webp")+activityCard("Casebook",history,"/art/v290/mysteries/classified_dossier.webp")+activityCard("Earned titles",titles);
}
function bindActivities(){
 const root=el("activitiesContent"),refreshButton=el("activitiesRefresh");
 if(!root||!refreshButton)return;
 refreshButton.onclick=()=>{if(registered()&&!S.busy&&!S.privatePending)void loadPrivate().catch(e=>notice(e.message,"error"))};
 root.addEventListener("click",event=>{
  const b=event.target.closest("button[data-activity]");
  if(!b||!root.contains(b)||b.disabled||!registered()||S.busy||S.privatePending)return;
  const body={action:b.dataset.activity,item:b.dataset.item,day:S.activities?.day??null};
  if(!S.activities||String(S.activities.player_id)!==String(S.session.player_id))return;
  if(body.action==="accuse"&&!window.confirm("Accuse "+b.textContent+"? This uses one of today's limited guesses."))return;
  act(async()=>{
   const result=await post("/v1/game/activities/action",body,true,true);
   const n=el("activitiesResult");n.textContent=result.message||"Activity recorded.";n.classList.remove("hidden");
   notice(result.message||"Activity recorded.","success");
  });
  showActivities();
 });
}

/* v2.9.8a — five shared arcade games, with server-owned puzzle sessions. */
const ARCADE_ART=Object.freeze(Object.fromEntries(["gallery","safe","snowman","catch","trivia"].map(k=>[k,"/art/v290/arcade/"+k+".webp"])));
function returnToArcadeHub(){
 if(hubAllowed()){
  void loadArcadeHub();
  el("arcadeHub")?.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
 }
}
function arcadeAllowed(){
 return !!(S.session&&S.me?.registered&&S.arcade&&String(S.arcade.player_id)===String(S.session.player_id));
}
function arcadeButton(action,value,label,disabled=false){
 return "<button type='button' class='button button-outline' data-arcade='"+esc(action)+"' data-value='"+esc(value)+"'"+(disabled?" disabled":"")+">"+esc(label)+"</button>";
}
function showArcade(){
 const lobby=el("arcadeLobby"),runNode=el("arcadeRun"),stamps=el("arcadeStamps"),board=el("arcadeBoard");
 if(!lobby||!runNode||!stamps||!board)return;
 const a=arcadeAllowed()?S.arcade:null;
 if(a)mountArcadeHub();
 const locked=!!(S.busy||S.privatePending||!S.privateFresh||a?.phase!=="live"||!hasPlayIdentity(S.session,S.config));
 txt("arcadeStatus",!S.session?"Sign in to play.":!S.me?.registered?"Register at Headquarters to play.":!a?"Refresh to load your arcade.":((S.config?.hub_v299f_enabled?"Classic (Discord-shared) · ":"")+"Day "+(a.day??"—")+" / 7 · "+String(a.phase).toUpperCase()+" · "+fmt(a.completed)+" completed runs · "+fmt(a.bests_total)+" combined best"));
 el("arcadeRefresh").disabled=!!(S.busy||S.privatePending);
 el("arcadeBoardRefresh").disabled=!a||S.busy||S.privatePending;
 if(!a){if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.dispose();S.arcadePracticeRuntime=null;S.arcadePractice=null;el("arcadePractice")?.classList.add("hidden");if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.dispose();S.arcadeGalleryRuntime=null;S.arcadeGallery=null;el("arcadeGallery")?.classList.add("hidden");if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.dispose();S.arcadeSafeRuntime=null;S.arcadeSafe=null;el("arcadeSafe")?.classList.add("hidden");if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.dispose();S.arcadeSnowmanRuntime=null;S.arcadeSnowman=null;el("arcadeSnowman")?.classList.add("hidden");if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.dispose();S.arcadeCatchRuntime=null;S.arcadeCatch=null;el("arcadeCatch")?.classList.add("hidden");if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.dispose();S.arcadeTriviaRuntime=null;S.arcadeTrivia=null;el("arcadeTrivia")?.classList.add("hidden");if(S.arcadeHubRuntime)S.arcadeHubRuntime.dispose();S.arcadeHubRuntime=null;S.arcadeHub=null;S.arcadeHubSeq++;S.arcadeHubPending=false;el("arcadeHub")?.classList.add("hidden");lobby.innerHTML="";stamps.innerHTML="";board.innerHTML="";runNode.classList.add("hidden");runNode.innerHTML="";return}
 const run=S.arcadeRun&&S.arcadeRun.day===a.day&&ARCADE_ART[S.arcadeRun.mode]?S.arcadeRun:null;
 runNode.classList.toggle("hidden",!run);
 if(run){
  const round=run.current;
  const choices=Array.isArray(round?.choices)?round.choices:[];
  runNode.innerHTML="<img class='arcade-run-art' src='"+ARCADE_ART[run.mode]+"' alt=''><div class='arcade-run-copy'><p class='eyebrow'>"+esc(run.title)+" · Run "+fmt(run.attempt)+"</p><h3>"+(run.finished?"Run complete!":"Round "+fmt(round?.index)+" / "+fmt(run.total_rounds))+"</h3><div class='arcade-meter' aria-label='Score'><span style='width:"+Math.max(0,Math.min(100,Number(run.score)||0))+"%'></span></div><p><strong>"+fmt(run.score)+" / 100</strong> arcade points</p>"+(run.feedback?"<p class='arcade-feedback' role='status'>"+esc(run.feedback)+"</p>":"")+(run.finished?"<p>Personal records and stamps are saved to your shared passport.</p>":"<p class='arcade-prompt'>"+esc(round?.prompt)+"</p><div class='arcade-choices'>"+choices.map(v=>arcadeButton("move",v,v,locked)).join("")+"</div>")+"</div>";
 }
 else runNode.innerHTML="";
 const records=Array.isArray(a.records)?a.records:[];
 const practiceHubLive=!!(S.config?.hub_v299f_enabled&&S.arcadeHub&&!S.arcadeHubError);
 lobby.innerHTML=(a.games||[]).filter(g=>ARCADE_ART[g.key]).map(g=>{
  const r=records.find(x=>x.mode===g.key)||{},used=Number(r.attempts_today||0),cap=Number(a.daily_cap||3);
  const canResume=!!r.active_id;
  return "<article class='arcade-card'><img src='"+ARCADE_ART[g.key]+"' alt='' loading='lazy'><div><p class='eyebrow'>"+fmt(g.rounds)+" rounds · "+esc(g.award_name)+"</p><h3>"+esc(g.title)+"</h3><p>"+esc(g.description)+"</p><p>Personal best: <strong>"+fmt(r.personal_best)+" / 100</strong> · "+fmt(r.games_played)+" finished</p><p>"+fmt(used)+" / "+fmt(cap)+" starts used today</p>"+arcadeButton("start",g.key,canResume?"Resume game":used>=cap?"Daily limit reached":"Play game",locked||(!canResume&&used>=cap))+
  (practiceHubLive?"":arcadeButton("practice",g.key,S.config?.interactive_arcade_enabled?"Interactive practice · free":"Interactive practice · coming soon",!S.config?.interactive_arcade_enabled||S.busy||S.privatePending||!S.privateFresh||!hasPlayIdentity(S.session,S.config)))+(practiceHubLive?"":(g.key==="gallery"?arcadeButton("gallery-full",g.key,S.config?.gallery_v299a_enabled?"Play full Target Gallery · QA":"Full Target Gallery · coming soon",!S.config?.gallery_v299a_enabled||locked):"")+(g.key==="safe"?arcadeButton("safe-full",g.key,S.config?.safe_v299b_enabled?"Crack the Frozen Safe · QA":"Frozen Safecracker · coming soon",!S.config?.safe_v299b_enabled||locked):"")+(g.key==="snowman"?arcadeButton("snowman-full",g.key,S.config?.snowman_v299c_enabled?"Build a Snowman · QA":"Snowman Builder · coming soon",!S.config?.snowman_v299c_enabled||locked):"")+(g.key==="catch"?arcadeButton("catch-full",g.key,S.config?.catch_v299d_enabled?"Play Snowflake Catch · QA":"Full Snowflake Catch · coming soon",!S.config?.catch_v299d_enabled||locked):"")+(g.key==="trivia"?arcadeButton("trivia-full",g.key,S.config?.trivia_v299e_enabled?"Play Christmas Trivia · QA":"Full Christmas Trivia · coming soon",!S.config?.trivia_v299e_enabled||locked):""))+"</div></article>";
 }).join("");
 const collected=new Set(a.stamps||[]);
 stamps.innerHTML=Object.entries(a.stamp_labels||{}).map(([key,name])=>"<div class='arcade-stamp"+(collected.has(key)?" earned":"")+"'><span>"+(collected.has(key)?"✓":"◇")+"</span> "+esc(name)+"</div>").join("");
 renderArcadeBoard();
}

/* v2.9.9f — one read-only web-practice hub, never Classic gameplay ledger. */
const FULL_ARCADE_HUB=Object.freeze({
 gallery:{path:"gallery",flag:"gallery_v299a_enabled",state:"arcadeGallery",
  mount:mountArcadeGallery,reconcile:reconcileGalleryPending},
 safe:{path:"safecracker",flag:"safe_v299b_enabled",state:"arcadeSafe",
  mount:mountArcadeSafe,reconcile:reconcileSafePending},
 snowman:{path:"snowman",flag:"snowman_v299c_enabled",state:"arcadeSnowman",
  mount:mountArcadeSnowman,reconcile:reconcileSnowmanPending},
 catch:{path:"catch",flag:"catch_v299d_enabled",state:"arcadeCatch",
  mount:mountArcadeCatch,reconcile:reconcileCatchPending},
 trivia:{path:"trivia",flag:"trivia_v299e_enabled",state:"arcadeTrivia",
  mount:mountArcadeTrivia,reconcile:reconcileTriviaPending},
});
function hubAllowed(){
 return !!(S.config?.hub_v299f_enabled&&window.SnowfallArcadeHubV299f&&
  arcadeAllowed()&&hasPlayIdentity(S.session,S.config));
}
function openClassicArcade(){
 const classic=el("arcadeClassic");
 if(!classic)return;
 classic.open=true;
 classic.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
 classic.querySelector("summary")?.focus({preventScroll:true});
}
async function launchArcadeHubGame(key){
 const spec=Object.hasOwn(FULL_ARCADE_HUB,key)?FULL_ARCADE_HUB[key]:null;
 if(!hubAllowed()||!spec||!S.config?.[spec.flag]||S.busy||S.privatePending||
    !S.privateFresh||S.arcade?.phase!=="live")
  throw Error("That game is not ready for this player.");
 const owner=arcadeOwner();
 // An existing, server-owned paused game is automatically reused by start().
 const view=await post("/v1/game/arcade/"+spec.path+"/start",{},true);
 ensureArcadeOwner(owner);
 if(view.mode!==key||typeof view.session_id!=="string")
  throw Error("Unexpected game session. Refresh the arcade.");
 S[spec.state]=view;
 spec.reconcile(view);
 spec.mount();
 // Update saved/playing state without resetting this mini-game.
 void loadArcadeHub();
}
function mountArcadeHub(){
 const root=el("arcadeHub");
 if(!root)return;
 if(!hubAllowed()){
  if(S.arcadeHubRuntime)S.arcadeHubRuntime.dispose();
  S.arcadeHubRuntime=null;root.classList.add("hidden");return;
 }
 if(!S.arcadeHubRuntime){
  S.arcadeHubRuntime=window.SnowfallArcadeHubV299f.mount({
   root,onLaunch:launchArcadeHubGame,onRefresh:loadArcadeHub,
   onClassic:openClassicArcade,
  });
 }
 if(S.arcadeHub&&String(S.arcadeHub.player_id)===String(S.session?.player_id)){
  try{S.arcadeHubRuntime.update(S.arcadeHub)}
  catch(e){S.arcadeHubError=e;S.arcadeHubRuntime.setError(e)}
 }
 if(S.arcadeHubError)S.arcadeHubRuntime.setError(S.arcadeHubError);
}
async function loadArcadeHub(){
 if(!hubAllowed())return;
 if(S.arcadeHubPending)return;
 const id=String(S.session.player_id),sequence=++S.arcadeHubSeq;
 S.arcadeHubPending=true;
 mountArcadeHub();S.arcadeHubRuntime?.setLoading(true);
 try{
  const hub=await get("/v1/game/arcade/hub");
  if(sequence!==S.arcadeHubSeq||id!==String(S.session?.player_id))return;
  if(hub.player_id!==id||hub.version!=="2.9.9f"||
     !Array.isArray(hub.modes)||hub.modes.length!==5)
   throw Error("Practice records did not match your signed-in character.");
  S.arcadeHub=hub;S.arcadeHubError=null;
  S.arcadeHubRuntime?.update(hub);
  if(!S.arcadeHubClassicInitialised){
   S.arcadeHubClassicInitialised=true;
   if(!S.arcadeRun)el("arcadeClassic").open=false;
  }
  showArcade();
 }catch(e){
  if(sequence!==S.arcadeHubSeq||id!==String(S.session?.player_id))return;
  S.arcadeHubError=e;
  S.arcadeHubRuntime?.setError(e);
  // Keep all previous full-game buttons as a fallback if the hub fails.
  showArcade();
 }finally{
  if(sequence===S.arcadeHubSeq){
   S.arcadeHubPending=false;
   if(!S.arcadeHubError)S.arcadeHubRuntime?.setLoading(false);
  }
 }
}
function renderArcadeBoard(){
 const root=el("arcadeBoard");if(!root||!arcadeAllowed())return;
 const b=S.arcadeBoard;
 if(!b){root.textContent="Choose a game and period to view the rankings.";return}
 const row=(label,detail)=>"<div class='activity-line'><strong>"+esc(label)+"</strong><span>"+esc(detail)+"</span></div>";
 root.innerHTML="<div class='arcade-boards'><div><h4>Player high scores</h4>"+((b.players||[]).map((p,i)=>row((i+1)+". "+p.name+" · "+p.city,fmt(p.best)+" / 100 · "+fmt(p.games)+" runs")).join("")||"<p>No finished runs yet.</p>")+"</div><div><h4>City Cup · all games</h4>"+((b.cities||[]).map((c,i)=>row((i+1)+". "+c.city,fmt(c.score)+" · "+fmt(c.players)+" players")).join("")||"<p>No city records yet.</p>")+"</div></div>";
}
async function loadArcadeBoard(){
 if(!arcadeAllowed()||S.busy||S.privatePending)return;
 const seq=++S.arcadeBoardSeq,identity=String(S.session.player_id),mode=el("arcadeBoardMode").value,daily=el("arcadeBoardPeriod").value==="daily";
 S.arcadeBoard=null;txt("arcadeBoard","Loading rankings…");
 try{
  const b=await get("/v1/game/arcade/board?mode="+encodeURIComponent(mode)+"&daily="+daily);
  if(seq!==S.arcadeBoardSeq||identity!==String(S.session?.player_id))return;
  if(b.mode!==mode||b.daily!==daily)throw Error("Unexpected arcade rankings");
  S.arcadeBoard=b;renderArcadeBoard();
 }catch(e){if(seq===S.arcadeBoardSeq)txt("arcadeBoard",e.message)}
}
// v2.9.9 isolated canvas drills: no social-arcade attempts or records are touched.
function mountArcadePractice(){
 const root=el("arcadePractice");
 if(!root||!S.arcadePractice||!window.SnowfallArcadeV299)return;
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.dispose();
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 S.arcadePracticeRuntime=window.SnowfallArcadeV299.mount({
  root,session:S.arcadePractice,
  save:async body=>{
   const result=await post("/v1/game/arcade/practice/save",body,true);
   S.arcadePractice=result;
   return result;
  },
  onExit:()=>{
   S.arcadePracticeRuntime=null;root.classList.add("hidden");root.innerHTML="";
   S.arcadePractice=null;returnToArcadeHub();
  }
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
/* v2.9.9a: independent, server-verified interactive practice gallery.
   Never modifies the classic Discord arcade passport or daily starts. */
function reconcileGalleryPending(view){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/gallery/shot|";
 let changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{
   const body=JSON.parse(key.slice(prefix.length));
   if(body.session_id===view.session_id&&body.shot_index<view.shots_used){
    S.pendingActions.delete(key);changed=true;
   }
  }catch{}
 }
 if(changed)savePending();
}
function mountArcadeGallery(){
 const owner=arcadeOwner();ensureArcadeOwner(owner);
 const root=el("arcadeGallery");
 if(!root||!S.arcadeGallery||!window.SnowfallGalleryV299a)return;
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.dispose();
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 const accepted=view=>{ensureArcadeOwner(owner);S.arcadeGallery=view;reconcileGalleryPending(view);return view};
 S.arcadeGalleryRuntime=window.SnowfallGalleryV299a.mount({
  root,session:S.arcadeGallery,
  start:async()=>accepted(await post("/v1/game/arcade/gallery/start",{},true)),
  control:async(session_id,action)=>accepted(await post("/v1/game/arcade/gallery/control",{session_id,action},true)),
  shot:async body=>accepted(await post("/v1/game/arcade/gallery/shot",body,true,true)),
  refresh:async session_id=>accepted(await get("/v1/game/arcade/gallery/session/"+encodeURIComponent(session_id))),
  fetchRecord:async()=>get("/v1/game/arcade/gallery/record"),
  onExit:()=>{if(!isArcadeOwner(owner))return;S.arcadeGalleryRuntime=null;S.arcadeGallery=null;root.classList.add("hidden");root.innerHTML="";returnToArcadeHub()}
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
/* v2.9.9b isolated Frozen Safecracker — no changes to Discord choice games. */
function reconcileSafePending(view){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/safecracker/move|";
 let recovered=null,changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{
   const body=JSON.parse(key.slice(prefix.length));
   if(body.session_id!==view.session_id||body.action_seq<view.action_seq){
    S.pendingActions.delete(key);changed=true;
   }else if(body.action_seq===view.action_seq&&
    ["turn","set"].includes(body.action)&&Number.isInteger(body.ticks)){
    recovered=body;
   }
  }catch{}
 }
 if(changed)savePending();
 return recovered;
}
function mountArcadeSafe(){
 const owner=arcadeOwner();ensureArcadeOwner(owner);
 const root=el("arcadeSafe");
 if(!root||!S.arcadeSafe||!window.SnowfallSafecrackerV299b)return;
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.dispose();
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 const accepted=view=>{ensureArcadeOwner(owner);S.arcadeSafe=view;reconcileSafePending(view);return view};
 S.arcadeSafeRuntime=window.SnowfallSafecrackerV299b.mount({
  root,session:S.arcadeSafe,
  recoveredAction:reconcileSafePending(S.arcadeSafe),
  start:async()=>accepted(await post("/v1/game/arcade/safecracker/start",{},true)),
  control:async(session_id,action)=>accepted(await post(
   "/v1/game/arcade/safecracker/control",{session_id,action},true)),
  move:async body=>accepted(await post("/v1/game/arcade/safecracker/move",body,true,true)),
  refresh:async session_id=>accepted(await get(
   "/v1/game/arcade/safecracker/session/"+encodeURIComponent(session_id))),
  fetchRecord:async()=>get("/v1/game/arcade/safecracker/record"),
  onExit:()=>{if(!isArcadeOwner(owner))return;S.arcadeSafeRuntime=null;S.arcadeSafe=null;
   root.classList.add("hidden");root.innerHTML="";returnToArcadeHub()}
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
/* v2.9.9c: Snowman Builder is isolated from Discord competition. */
function reconcileSnowmanPending(view){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/snowman/place|";
 let recovered=null,changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{
   const body=JSON.parse(key.slice(prefix.length));
   if(body.session_id!==view.session_id||body.action_seq<view.action_seq){
    S.pendingActions.delete(key);changed=true;
   }else if(body.action_seq===view.action_seq&&
    /^[a-z_]{3,24}$/.test(body.piece_id)&&
    Number.isInteger(body.x)&&Number.isInteger(body.y)){
    recovered=body;
   }
  }catch{}
 }
 if(changed)savePending();
 return recovered;
}
function mountArcadeSnowman(){
 const owner=arcadeOwner();ensureArcadeOwner(owner);
 const root=el("arcadeSnowman");
 if(!root||!S.arcadeSnowman||!window.SnowfallSnowmanV299c)return;
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.dispose();
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 const accepted=view=>{
  ensureArcadeOwner(owner);S.arcadeSnowman=view;reconcileSnowmanPending(view);return view;
 };
 S.arcadeSnowmanRuntime=window.SnowfallSnowmanV299c.mount({
  root,session:S.arcadeSnowman,
  recoveredAction:reconcileSnowmanPending(S.arcadeSnowman),
  start:async()=>accepted(await post("/v1/game/arcade/snowman/start",{},true)),
  control:async(session_id,action)=>accepted(await post(
   "/v1/game/arcade/snowman/control",{session_id,action},true)),
  place:async body=>accepted(await post("/v1/game/arcade/snowman/place",body,true,true)),
  refresh:async session_id=>accepted(await get(
   "/v1/game/arcade/snowman/session/"+encodeURIComponent(session_id))),
  fetchRecord:async()=>get("/v1/game/arcade/snowman/record"),
  onExit:()=>{if(!isArcadeOwner(owner))return;S.arcadeSnowmanRuntime=null;S.arcadeSnowman=null;
   root.classList.add("hidden");root.innerHTML="";returnToArcadeHub()}
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
/* v2.9.9d — separate, speed-limited Snowflake Catch with replay recovery. */
function reconcileCatchPending(view){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/catch/update|";
 let recovered=null,changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{
   const body=JSON.parse(key.slice(prefix.length));
   if(body.session_id!==view.session_id||body.action_seq<view.action_seq){
    S.pendingActions.delete(key);changed=true;
   }else if(body.action_seq===view.action_seq&&
            Number.isInteger(body.x)&&body.x>=66&&body.x<=574){
    recovered=body;
   }
  }catch{}
 }
 if(changed)savePending();
 return recovered;
}
function mountArcadeCatch(){
 const owner=arcadeOwner();ensureArcadeOwner(owner);
 const root=el("arcadeCatch");
 if(!root||!S.arcadeCatch||!window.SnowfallCatchV299d)return;
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.dispose();
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.pause();
 const accepted=view=>{ensureArcadeOwner(owner);S.arcadeCatch=view;reconcileCatchPending(view);return view};
 S.arcadeCatchRuntime=window.SnowfallCatchV299d.mount({
  root,session:S.arcadeCatch,
  recoveredAction:reconcileCatchPending(S.arcadeCatch),
  start:async()=>accepted(await post("/v1/game/arcade/catch/start",{},true)),
  control:async(session_id,action)=>accepted(await post(
   "/v1/game/arcade/catch/control",{session_id,action},true)),
  update:async body=>accepted(await post("/v1/game/arcade/catch/update",body,true,true)),
  refresh:async session_id=>accepted(await get(
   "/v1/game/arcade/catch/session/"+encodeURIComponent(session_id))),
  fetchRecord:async()=>get("/v1/game/arcade/catch/record"),
  onExit:()=>{if(!isArcadeOwner(owner))return;S.arcadeCatchRuntime=null;S.arcadeCatch=null;
   root.classList.add("hidden");root.innerHTML="";returnToArcadeHub()}
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
/* v2.9.9e — Christmas Trivia reuses the Arcade 2.0 scene and official login. */
function reconcileTriviaPending(view){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/trivia/answer|";
 let recovered=null,changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{
   const body=JSON.parse(key.slice(prefix.length));
   if(body.session_id!==view.session_id||body.step<view.step){
    S.pendingActions.delete(key);changed=true;
   }else if(body.step===view.step&&
    typeof body.answer==="string"&&body.answer.length<=64){
    recovered=body;
   }
  }catch{}
 }
 if(changed)savePending();
 return recovered;
}
function mountArcadeTrivia(){
 const owner=arcadeOwner();ensureArcadeOwner(owner);
 const root=el("arcadeTrivia");
 if(!root||!S.arcadeTrivia||!window.SnowfallTriviaV299e)return;
 if(S.arcadeTriviaRuntime)S.arcadeTriviaRuntime.dispose();
 if(S.arcadePracticeRuntime)S.arcadePracticeRuntime.pause();
 if(S.arcadeGalleryRuntime)S.arcadeGalleryRuntime.pause();
 if(S.arcadeSafeRuntime)S.arcadeSafeRuntime.pause();
 if(S.arcadeSnowmanRuntime)S.arcadeSnowmanRuntime.pause();
 if(S.arcadeCatchRuntime)S.arcadeCatchRuntime.pause();
 const accepted=view=>{ensureArcadeOwner(owner);S.arcadeTrivia=view;reconcileTriviaPending(view);return view};
 S.arcadeTriviaRuntime=window.SnowfallTriviaV299e.mount({
  root,session:S.arcadeTrivia,
  recoveredAction:reconcileTriviaPending(S.arcadeTrivia),
  start:async()=>accepted(await post("/v1/game/arcade/trivia/start",{},true)),
  control:async(session_id,action)=>accepted(await post(
   "/v1/game/arcade/trivia/control",{session_id,action},true)),
  answer:async body=>accepted(await post("/v1/game/arcade/trivia/answer",body,true,true)),
  refresh:async session_id=>accepted(await get(
   "/v1/game/arcade/trivia/session/"+encodeURIComponent(session_id))),
  fetchRecord:async()=>get("/v1/game/arcade/trivia/record"),
  onExit:()=>{if(!isArcadeOwner(owner))return;S.arcadeTriviaRuntime=null;S.arcadeTrivia=null;
   root.classList.add("hidden");root.innerHTML="";returnToArcadeHub()}
 });
 root.scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"});
}
function bindArcade(){
 const page=el("page-arcade");if(!page)return;
 el("arcadeRefresh").onclick=()=>{if(registered()&&!S.busy&&!S.privatePending)void loadPrivate().catch(e=>notice(e.message,"error"))};
 el("arcadeBoardRefresh").onclick=()=>void loadArcadeBoard();
 for(const id of ["arcadeBoardMode","arcadeBoardPeriod"])el(id).onchange=()=>{S.arcadeBoardSeq++;S.arcadeBoard=null;renderArcadeBoard()};
 page.addEventListener("click",event=>{
  const b=event.target.closest("button[data-arcade]");
  if(!b||b.disabled||!registered()||!arcadeAllowed()||S.busy||S.privatePending)return;
  const a=S.arcade,action=b.dataset.arcade,value=b.dataset.value;
  if(action==="trivia-full"&&value==="trivia"&&S.config?.trivia_v299e_enabled){
   act(async()=>{
    const view=await post("/v1/game/arcade/trivia/start",{},true);
    S.arcadeTrivia=view;reconcileTriviaPending(view);mountArcadeTrivia();
    notice("Christmas Trivia ready — unwrap 15 festive challenges!","success");
   });
  }else if(action==="catch-full"&&value==="catch"&&S.config?.catch_v299d_enabled){
   act(async()=>{
    const view=await post("/v1/game/arcade/catch/start",{},true);
    S.arcadeCatch=view;reconcileCatchPending(view);mountArcadeCatch();
    notice("Snowflake Catch ready — avoid hazards, catch falling bonuses!","success");
   });
  }else if(action==="snowman-full"&&value==="snowman"&&S.config?.snowman_v299c_enabled){
   act(async()=>{
    const view=await post("/v1/game/arcade/snowman/start",{},true);
    S.arcadeSnowman=view;reconcileSnowmanPending(view);mountArcadeSnowman();
    notice("Snowman Builder ready — drag parts onto the blueprints!","success");
   });
  }else if(action==="safe-full"&&value==="safe"&&S.config?.safe_v299b_enabled){
   act(async()=>{
    const view=await post("/v1/game/arcade/safecracker/start",{},true);
    S.arcadeSafe=view;reconcileSafePending(view);mountArcadeSafe();
    notice("Frozen Safecracker ready: clockwise, anticlockwise, clockwise!","success");
   });
  }else if(action==="gallery-full"&&value==="gallery"&&S.config?.gallery_v299a_enabled){
   act(async()=>{
    const view=await post("/v1/game/arcade/gallery/start",{},true);
    S.arcadeGallery=view;reconcileGalleryPending(view);mountArcadeGallery();
    notice("Target Gallery ready — 3 waves, 45 seconds, practice-only scoring.","success");
   });
  }else if(action==="practice"&&ARCADE_ART[value]){
   act(async()=>{
    const practice=await post("/v1/game/arcade/practice/start",{mode:value},true);
    S.arcadePractice=practice;
    mountArcadePractice();
    notice("Unranked interactive practice ready. No daily start used.","success");
   });
  }else if(action==="start"&&ARCADE_ART[value]){
   const record=a.records.find(r=>r.mode===value);if(!record)return;
   act(async()=>{
    const run=record.active_id?await get("/v1/game/arcade/session/"+encodeURIComponent(record.active_id)):
      await post("/v1/game/arcade/start",{mode:value,day:a.day,attempts_today:record.attempts_today},true);
    S.arcadeRun=run;S.arcadeBoard=null;el("arcadeRun").classList.remove("hidden");
    notice(run.finished?"Run already completed.":"Arcade run ready.","success");
   }).then(()=>{if(S.arcadeRun&&el("page-arcade").classList.contains("active"))el("arcadeRun").scrollIntoView({block:"start",behavior:motionEnabled()?"smooth":"auto"})});
  }else if(action==="move"&&S.arcadeRun&&!S.arcadeRun.finished&&S.arcadeRun.current?.choices?.includes(value)){
   const body={session_id:S.arcadeRun.session_id,step:S.arcadeRun.step,choice:value};
   act(async()=>{
    const result=await post("/v1/game/arcade/move",body,true,true);
    S.arcadeRun=result.session;S.arcadeBoard=null;notice(result.feedback||"Turn recorded.","success");
   });
  }
  showArcade();
 });
}

function reconcileArcadeMoves(run){
 const prefix=String(S.session?.player_id)+"|/v1/game/arcade/move|";
 let changed=false;
 for(const key of S.pendingActions.keys()){
  if(!key.startsWith(prefix))continue;
  try{const b=JSON.parse(key.slice(prefix.length));if(b.session_id===run.session_id&&b.step<run.step){S.pendingActions.delete(key);changed=true}}catch{}
 }
 if(changed)savePending();
}

/* v2.9.8b — read-only community dispatch. No message relay. */
function showCommunity(){
 const c=S.community,root=el("communityCities");if(!root)return;
 el("communityRefresh").disabled=S.communityPending;
 txt("communityStatus",S.communityPending?"Refreshing verified dispatch…":S.communityStale?"Update unavailable — "+(c?"showing last known community totals.":"retry when connected."):!c?"The streets are awaiting a dispatch.":("Day "+(c.day??"—")+" / 7 · "+String(c.phase).toUpperCase()+" · "+c.theme));
 if(!c){for(const id of ["communityTotals","communityFeed","communityCities"])el(id).innerHTML="";txt("communityMilestones","No verified milestones yet.");return}
 const t=c.totals||{};
 el("communityTotals").innerHTML=[["Snowballs thrown","throws"],["Snow Don damage","boss_damage"],["Siege damage","siege_damage"],["Assignments","quests"],["Presents","gifts"],["Arcade runs","arcade"]].map(([label,key])=>"<div class='activity-card'><span class='subtle'>"+esc(label)+"</span><strong>"+fmt(t[key])+"</strong></div>").join("");
 const labels={combat:"Snowball Alley",boss:"Snow Don",siege:"City siege",quests:"Assignments",gifts:"Presents",arcade:"Arcade"};
 el("communityFeed").innerHTML=(c.updates||[]).map(x=>"<div class='activity-line'><div><strong>"+esc(x.city)+" · "+esc(labels[x.kind]||"Activity")+"</strong><p>"+fmt(x.count)+" "+esc(x.unit)+" today</p></div></div>").join("")||"<p>No eligible activity recorded for this edition yet.</p>";
 txt("communityMilestones",fmt(c.objectives_met)+" / 6 cities met today's cooperative objective · "+fmt(t.hits)+" successful hits · "+fmt(t.arcade)+" arcade runs completed.");
 root.innerHTML=(c.cities||[]).map(x=>{
  const o=x.objective,slug=CITY_SLUG[x.city];
  return "<article class='activity-card'><div class='community-city-head'>"+(slug?"<img alt='' src='/art/v290/cities/crests/"+slug+"_crest.png'>":"")+"<div><h3>"+esc(x.city)+"</h3><p>"+fmt(x.members)+" registered members · "+esc(x.rival?"Rival: "+x.rival:"Awaiting daily pairing")+"</p></div></div>"+(o?"<p><strong>"+esc(o.name)+"</strong> · "+esc(o.detail)+"</p><div class='hq-meter'><span style='width:"+hqPercent(o.progress,o.target)+"%'></span></div><p>"+fmt(o.progress)+" / "+fmt(o.target)+" "+esc(o.unit)+(o.completed?" · Objective complete":"")+"</p>":"<p>Daily objectives open with the event.</p>")+"<p class='subtle'>"+fmt(x.activity?.throws)+" throws · "+fmt(x.activity?.quests)+" assignments · "+fmt(x.activity?.arcade)+" arcade runs</p></article>";
 }).join("");
}
async function refreshCommunity(){
 if(S.communityPending)return;
 S.communityPending=true;showCommunity();
 try{const c=await get("/v1/web/community");if(c.verified_only!==true||c.chat_relay!==false||!Array.isArray(c.cities))throw Error("Invalid community dispatch");S.community=c;S.communityStale=false}
 catch{S.communityStale=true}
 finally{S.communityPending=false;showCommunity()}
}

/* Staff-only read-only control centre, v2.9.8c. */
function updateStaffNavigation(){
 const allowed=S.staffAllowed===true;
 for(const id of ["staffNav","staffShortcut"]){
   const item=el(id);if(item)item.classList.toggle("hidden",!allowed);
 }
 if(el("staffOnlyNotice"))el("staffOnlyNotice").classList.toggle("hidden",!allowed||!S.session||hasPlayIdentity(S.session,S.config));
 if(allowed&&el("underworldRequired"))el("underworldRequired").classList.add("hidden");
 if(!allowed&&S.session&&!hasPlayIdentity(S.session,S.config)&&el("underworldRequired"))el("underworldRequired").classList.remove("hidden");
 if(!allowed&&el("page-staff")?.classList.contains("active"))section("home",{record:false,focus:false});
}
async function refreshStaffAccess({force=false}={}){
 const id=S.session?String(S.session.player_id):null;
 if(!id){S.staffCheckedIdentity=null;S.staffAccessCheckedAt=0;S.staffAllowed=false;S.staffRole=null;S.staffData=null;S.staffDirectory=null;S.staffDossier=null;updateStaffNavigation();showStaffPlayerDesk();return}
 if(!force&&id===S.staffCheckedIdentity&&Date.now()-S.staffAccessCheckedAt<90000)return;
 S.staffCheckedIdentity=id;
 S.staffAccessCheckedAt=Date.now();
 try{
   const a=await get("/v1/staff/access");
   if(String(S.session?.player_id)!==id)return;
   S.staffAllowed=a.allowed===true;
   if(!S.staffAllowed){S.staffData=null;S.staffRole=null;S.staffDirectory=null;S.staffDossier=null}
   else {
     const role=await get("/v1/staff/role");
     if(String(S.session?.player_id)!==id)return;
     if(role.scope!=="ISOLATED_QA_ONLY"||!["host","organiser"].includes(role.role))throw Error("Unexpected staff role");
     S.staffRole=role;
   }
 }catch{
   if(String(S.session?.player_id)!==id)return;
   S.staffAllowed=false;S.staffRole=null;S.staffData=null;S.staffDirectory=null;S.staffDossier=null;
 }
 updateStaffNavigation();showStaffPlayerDesk();
}
function staffTime(v){
 const t=Date.parse(v);return Number.isFinite(t)?new Date(t).toLocaleString([],{dateStyle:"medium",timeStyle:"short"}):"—";
}
function staffRow(label,value){
 return "<div class='activity-line'><strong>"+esc(label)+"</strong><span>"+esc(value??"—")+"</span></div>";
}
function showStaffDashboard(){
 const d=S.staffAllowed?S.staffData:null;
 if(!el("staffStatus"))return;
 el("staffRefresh").disabled=!!(S.staffPending||!S.staffAllowed);
 txt("staffStatus",!S.staffAllowed?"Authorised staff only.":S.staffPending?"Refreshing audited game records…":S.staffStale?"Refresh failed — showing last retrieved data.":!d?"Select Refresh control centre to load records.":("Verified "+staffTime(d.server_time)+" · "+String(d.phase).toUpperCase()+" · Day "+(d.game_day??"—")+" / 7 · QA · "+(S.staffRole?.can_review?"Host review enabled":"Organiser view")));
 if(!d){
  for(const id of ["staffMetrics","staffSchedule","staffRisks","staffBoss","staffPlayers","staffDaily","staffAudit","staffPrizes"])el(id).innerHTML="";
  txt("staffPlayersStatus","");txt("staffPrizeNote","");return;
 }
 const t=d.totals||{},risk=d.risks||{},times=d.schedule||{};
 el("staffMetrics").innerHTML=[["Registered",t.players],["Flagged",t.flagged],["Ledger entries",t.score_rows],["Snowball attacks",t.combat],["Boss & siege actions",t.boss_siege],["Recorded awards",t.award_rows]].map(([k,v])=>"<div class='activity-card'><small>"+esc(k)+"</small><strong>"+fmt(v)+"</strong></div>").join("");
 el("staffSchedule").innerHTML=staffRow("Current phase",String(d.phase).toUpperCase())+staffRow("Registration opens",staffTime(times.registration_opens))+staffRow("Scheduled kickoff",staffTime(times.planned_start))+staffRow("Actual kickoff",staffTime(times.started_at))+staffRow("Paused since",staffTime(times.paused_at))+staffRow("Projected completion",staffTime(times.projected_end))+staffRow("Accumulated pause",fmt(times.pause_seconds)+" seconds");
 const risks=[["Flagged players","flagged_players"],["Invalid resource balances","invalid_balances"],["Combat–ledger mismatches","pvp_ledger_mismatches"],["PvP over-cap days","pvp_over_cap"],["Quest over-cap days","quest_over_cap"],["Unbacked quest credits","quest_unbacked"],["Missing quest credits","quest_missing"],["Defense mismatches","defense_mismatches"],["Arcade attempt violations","arcade_over_limit"]];
 el("staffRisks").innerHTML="<p><strong>Reconciliation: "+(d.reconciliation_ok?"PASS":"REVIEW REQUIRED")+"</strong></p>"+risks.map(([name,key])=>staffRow(name,fmt(risk[key]))).join("")+"<p class='subtle'>"+fmt(t.unlinked)+" QA characters without Underworld links (may include intentional fixtures).</p>";
 const boss=d.boss;
 const bs=boss?"<p>"+esc(boss.theme)+" · Day "+fmt(boss.day)+"</p>"+staffRow("Snow Don HP",fmt(boss.boss_hp)+" / "+fmt(boss.boss_initial_hp)):"<p>The Snow Don has not been initialised for this event day.</p>";
 el("staffBoss").innerHTML=bs+(d.sieges||[]).map(s=>staffRow(s.city,fmt(s.hp)+" / "+fmt(s.initial_hp)+" HP")).join("");
 el("staffPlayers").innerHTML=(d.players||[]).map(p=>"<tr><td>"+esc(p.mr_username)+"</td><td>"+esc(p.city)+"</td><td>"+fmt(p.score)+"</td><td>"+esc(p.review_state)+"</td></tr>").join("")||"<tr><td colspan='4'>No registered characters.</td></tr>";
 txt("staffPlayersStatus",fmt((d.players||[]).length)+" shown · "+fmt(t.players)+" registered · "+fmt(t.disqualified)+" disqualified. No automatic sanctions.");
 el("staffDaily").innerHTML=(d.days||[]).map(x=>staffRow("Day "+fmt(x.day)+" · "+x.category,fmt(x.points)+" points · "+fmt(x.entries)+" entries")).join("")||"<p>No ledger entries yet.</p>";
 el("staffAudit").innerHTML=(d.audit||[]).map(x=>"<div class='staff-audit-line'><strong>"+esc(x.action)+"</strong><span>"+staffTime(x.created_at_utc)+"</span><p>"+esc(x.reason)+"</p></div>").join("")||"<p>No staff audit events recorded.</p>";
 el("staffPrizes").innerHTML=(d.prize_preview||[]).map(x=>staffRow("Place "+fmt(x.place)+" · "+x.name+" ("+x.city+")",fmt(x.points)+" points")).join("")||"<p>No eligible positive-score candidates yet.</p>";
 txt("staffPrizeNote",d.prize_policy+" · "+fmt(t.award_rows)+" existing award rows.");
}
async function refreshStaffDashboard(){
 if(!S.staffAllowed||S.staffPending)return;
 const id=String(S.session?.player_id||"");
 S.staffPending=true;showStaffDashboard();
 try{
  const data=await get("/v1/staff/control");
  if(String(S.session?.player_id)!==id||!S.staffAllowed)return;
  if(data.read_only!==true||data.scope!=="ISOLATED_QA_ONLY"||data.official_prizes_enabled!==false)throw Error("Unexpected control centre permissions");
  S.staffData=data;S.staffStale=false;
 }catch(e){
  if(String(S.session?.player_id)===id){
   S.staffStale=true;
   if(e.status===401||e.status===403){S.staffAllowed=false;S.staffData=null;updateStaffNavigation()}
  }
 }finally{S.staffPending=false;showStaffDashboard()}
}


/* v2.9.8d — isolated disposable staff test lab, never a shared-game mutation. */
function showStaffLab(){
 const root=el("staffLabStatus");if(!root)return;
 const d=S.staffAllowed?S.staffLab:null,active=!!d?.active;
 txt("staffLabStatus",S.staffLabPending?"Running or refreshing your private test…":!S.staffAllowed?"Staff sign-in required.":!d?"Press Refresh lab to retrieve your session.":active?"WEB TEST ONLY · Day "+d.day+"/7 · "+d.theme+" · "+d.last_action:"No disposable web test is running.");
 for(const btn of document.querySelectorAll("[data-lab-action]")){
  const action=btn.dataset.labAction;
  const standalone=["simulate_week","reset_all"].includes(action);
  btn.disabled=S.staffLabPending||!S.staffAllowed||(!standalone&&(action==="start"?active:!active));
 }
 el("staffLabRefresh").disabled=S.staffLabPending||!S.staffAllowed;
 el("staffLabDay").disabled=active&&S.staffLabPending;
 el("staffLabExport").disabled=!S.staffAllowed||S.staffLabPending||!d;
 if(!d){for(const id of ["staffLabStats","staffLabPlayers","staffLabHistory","staffLabWeekSummary","staffLabComparisons"])el(id).innerHTML="";return}
 const totals=d.totals||{};
 el("staffLabStats").innerHTML=(active?[
  ["Test Day",d.day+"/7"],["Snow Don HP",d.boss?fmt(d.boss.boss_hp)+" / "+fmt(d.boss.boss_initial_hp):"—"],
  ["PvP throws",fmt(totals.pvp)],["Boss & siege actions",fmt(totals.pve)],
  ["Test ledger rows",fmt(totals.ledger)],["Test awards",fmt(totals.awards)]
 ]:[["Test Lab", "Inactive"],["Shared QA", "Unchanged"]]).map(([label,value])=>"<div class='activity-card'><small>"+esc(label)+"</small><strong>"+esc(value)+"</strong></div>").join("");
 el("staffLabPlayers").innerHTML=(d.players||[]).map(x=>staffRow(x.mr_username+" · "+x.city,fmt(x.score)+" pts")).join("")||"<p>No active fictional test players.</p>";
 el("staffLabHistory").innerHTML=(d.history||[]).slice(0,10).map(x=>"<div class='staff-audit-line'><strong>"+esc(x.action)+"</strong><span>"+staffTime(x.at)+"</span><p>"+esc(x.detail)+" · "+esc(x.reason)+"</p></div>").join("")||"<p>No test actions yet.</p>";
 const rows=d.comparisons||[];
 el("staffLabComparisons").innerHTML=rows.slice(0,35).map(x=>"<tr><td>"+esc(x.kind+(x.mode?" · "+x.mode:"")+(x.quest?" · "+x.quest:""))+"</td><td>"+fmt(x.day)+"</td><td>"+fmt(x.expected_points)+"</td><td>"+fmt(x.actual_points)+"</td><td>"+fmt(x.difference)+"</td><td>"+(x.passed&&x.arcade_passed!==false?"PASS":"REVIEW")+"</td></tr>").join("")||"<tr><td colspan='6'>No scoring checks recorded.</td></tr>";
 const week=d.weekly_report;
 el("staffLabWeekSummary").innerHTML=week?("<p><strong>"+(week.passed?"PASS":"REVIEW")+"</strong> · "+fmt(week.days_tested)+" days · "+fmt(week.total_points)+" temporary ledger points · "+fmt(week.official_awards)+" real awards</p><div class='staff-table-wrap'><table><thead><tr><th>Day</th><th>Theme</th><th>Checks</th><th>Score</th><th>Result</th></tr></thead><tbody>"+week.days.map(x=>"<tr><td>"+fmt(x.day)+"</td><td>"+esc(x.theme)+"</td><td>"+fmt(x.checks.length)+"</td><td>"+fmt(x.ledger_points)+"</td><td>"+(x.checks_passed?"PASS":"REVIEW")+"</td></tr>").join("")+"</tbody></table></div>"):"<p class='subtle'>No seven-day simulation recorded yet.</p>";
}
async function refreshStaffLab(){
 if(!S.staffAllowed||S.staffLabPending)return;
 const id=String(S.session?.player_id||"");
 S.staffLabPending=true;showStaffLab();
 try{
  const data=await get("/v1/staff/lab");
  if(String(S.session?.player_id)!==id||!S.staffAllowed)return;
  if(data.scope!=="DISPOSABLE_WEB_TEST_LAB"||data.shared_game_unchanged!==true||data.official_prizes_enabled!==false)throw Error("Unrecognised QA lab scope");
  S.staffLab=data;
 }catch(e){if(String(S.session?.player_id)===id)notice("Test Lab: "+e.message,"error")}
 finally{S.staffLabPending=false;showStaffLab()}
}
async function staffLabAction(action){
 if(!S.staffAllowed||S.staffLabPending)return;
 const active=!!S.staffLab?.active;
 if(action==="start"&&active)return notice("End the existing test first.","error");
 if(!["start","simulate_week","reset_all"].includes(action)&&!active)return notice("Start a disposable test day first.","error");
 const reason=el("staffLabReason").value.trim();
 if(reason.length<8)return notice("Add a staff reason of at least 8 characters.","error");
 const confirms={start:"START TEST",day:"RESET TEST DAY",resupply:"RESUPPLY TEST",end:"END TEST",simulate_week:"SIMULATE 7 DAYS",reset_all:"RESET ALL TEST DATA"};
 const expected=confirms[action]||"";
 if(expected&&el("staffLabConfirm").value.trim().toUpperCase()!==expected)return notice("Type "+expected+" to confirm this test-only action.","error");
 const day=["start","day"].includes(action)?Number(el("staffLabDay").value):null;
 const sessionId=["start","simulate_week","reset_all"].includes(action)?null:S.staffLab?.session_id;
 const identity=String(S.session?.player_id||"");
 const options={};
 if(action==="configure"){
  options.player_index=Number(el("staffLabPlayer").value);
  for(const [id,key] of [["staffLabSnowballs","snowballs"],["staffLabWarmth","warmth"],["staffLabArmour","armour_hp"],["staffLabCooldown","cooldown_seconds"],["staffLabBossHp","boss_hp"]]){
    const raw=el(id).value.trim();
    if(raw!==""){if(!/^\d+$/.test(raw))return notice("Use nonnegative whole numbers for test resources.","error");options[key]=Number(raw)}
  }
  if(Object.keys(options).length===1)return notice("Enter at least one resource or boss HP value.","error");
 }
 if(["pvp","boss","siege"].includes(action))options.outcome=el("staffLabOutcome").value;
 if(action==="arcade"){options.mode=el("staffLabArcade").value;options.scenario=el("staffLabArcadeOutcome").value}
 if(action==="mission")options.quest=el("staffLabMission").value;
 const body={action,day,reason,confirmation:expected,request_id:nextActionId(),session_id:sessionId,options};
 S.staffLabPending=true;showStaffLab();
 try{
  const result=await post("/v1/staff/lab/action",body,true);
  if(String(S.session?.player_id)!==identity||!S.staffAllowed)return;
  if(result.scope!=="DISPOSABLE_WEB_TEST_LAB"||result.shared_game_unchanged!==true)throw Error("Unexpected staff lab scope");
  S.staffLab=result;
  el("staffLabConfirm").value="";
  if(action==="configure"){for(const name of ["staffLabSnowballs","staffLabWarmth","staffLabArmour","staffLabCooldown","staffLabBossHp"])el(name).value=""}
  notice(result.action_result?.message||"Test action completed.","success");
 }catch(e){
  notice("Test Lab: "+e.message+" Refresh lab before another action.","error");
 }finally{S.staffLabPending=false;showStaffLab()}
}
function downloadStaffDiagnostics(){
 if(!S.staffAllowed||!S.staffData)return notice("Refresh Event Control first.","error");
 const d=S.staffData;
 const report={scope:"PRIVATE_QA_DIAGNOSTICS",exported_at:new Date().toISOString(),
  season:d.season,phase:d.phase,game_day:d.game_day,totals:d.totals,
  risks:d.risks,reconciliation_ok:d.reconciliation_ok,players:d.players,
  audit:d.audit,prize_preview:d.prize_preview,
  notice:"STAFF PRIVATE · QA ONLY · NO OFFICIAL PRIZES · DO NOT POST IN PUBLIC CHAT"};
 const blob=new Blob([JSON.stringify(report,null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob);
 try{const a=document.createElement("a");a.href=url;a.download="snowfall-private-qa-report.json";a.click()}
 finally{setTimeout(()=>URL.revokeObjectURL(url),1000)}
 notice("Private QA report prepared. Do not share publicly.","success");
}

function downloadLabResults(){
 if(!S.staffAllowed||!S.staffLab)return notice("Open an authorised Test Lab first.","error");
 const result={...S.staffLab,exported_at:new Date().toISOString(),
  notice:"DISPOSABLE TEST-ONLY DATA · NOT A REAL GAME OR PRIZE REPORT"};
 const blob=new Blob([JSON.stringify(result,null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob);
 try{const a=document.createElement("a");a.href=url;a.download="snowfall-test-lab-v298e.json";a.click()}
 finally{setTimeout(()=>URL.revokeObjectURL(url),1000)}
 notice("Your private Test Lab report was downloaded.","success");
}

/* v2.9.8f — staff-only player search, investigation and audited host review. */
function showStaffPlayerDesk(){
 const allowed=S.staffAllowed===true,d=allowed?S.staffDirectory:null;
 const p=allowed?S.staffDossier:null,host=S.staffRole?.can_review===true;
 const role=allowed?(host?"Host · may flag or clear QA player reviews":"Organiser · search, audit, inspect and test only"):"Sign in with an authorised Discord staff account.";
 txt("staffRoleStatus",role+" · No direct score edits, event resets or prizes.");
 txt("staffPlayerSearchStatus",S.staffDirectoryBusy?"Searching QA player records…":!d?"Search by name, player ID, city or review state.":fmt(d.total)+" matching · "+fmt(d.players?.length||0)+" on page "+d.page);
 const rows=d?.players||[];
 el("staffPlayerResults").innerHTML=rows.map(x=>"<tr><td>"+esc(x.mr_username)+"</td><td>"+esc(x.city)+"</td><td>"+fmt(x.score)+"</td><td>"+esc(x.review_state)+"</td><td><button class='button button-outline button-small' type='button' data-player-id='"+esc(x.player_id)+"'>Inspect</button></td></tr>").join("")||"<tr><td colspan='5'>"+(d?"No matching QA characters.":"Run a player search to see results.")+"</td></tr>";
 txt("staffPlayerPage",d?"Page "+d.page+" · "+fmt(d.total)+" total":"Page —");
 el("staffPlayerPrev").disabled=!allowed||S.staffDirectoryBusy||!d||d.page<=1;
 el("staffPlayerNext").disabled=!allowed||S.staffDirectoryBusy||!d||!d.has_more;
 el("staffPlayerExport").disabled=!allowed||!p||S.staffDossierBusy;
 const review=el("staffReviewForm");
 review.classList.toggle("hidden",!host||!p||p.profile.review_state==="disqualified");
 el("staffReviewSubmit").disabled=!host||!p||S.staffReviewBusy;
 if(!p){
  el("staffPlayerDossier").innerHTML="<p class='subtle'>"+(S.staffDossierBusy?"Loading verified QA player history…":"Select Inspect beside a character to see their dossier.")+"</p>";
  return;
 }
 const x=p.profile,links=p.links||{},activity=p.score_history||[];
 const linkName=v=>v===true?"Linked":v===false?"Not linked":"Not checked on this database";
 const issues=p.alerts||[];
 const history=(p.review_history||[]).map(h=>"<div class='staff-audit-line'><strong>"+esc(h.action)+"</strong><span>"+staffTime(h.created_at_utc)+"</span><p>"+esc(h.reason)+"</p></div>").join("");
 const combat=(p.combat_history||[]).map(a=>"<div class='staff-audit-line'>Day "+fmt(a.day)+" · "+esc(a.style)+" · "+(a.hit?"Hit":"Miss")+" · "+fmt(a.points_awarded)+" pts · "+staffTime(a.happened_at_utc)+"</div>").join("");
 const pve=(p.pve_history||[]).map(a=>"<div class='staff-audit-line'>Day "+fmt(a.day)+" · "+esc(a.kind)+" · "+(a.hit?"Hit":"Miss")+" · "+fmt(a.damage)+" damage · "+fmt(a.points_awarded)+" pts</div>").join("");
 el("staffPlayerDossier").innerHTML="<div class='staff-dossier-header'><div><p class='eyebrow'>VERIFIED SEASON RECORD</p><h4>"+esc(x.mr_username)+"</h4><p>"+esc(x.city)+" · "+esc(x.review_state)+" · #"+esc(x.player_id)+"</p></div><strong>"+fmt(x.score)+" points</strong></div>"+
 "<div class='staff-dossier-facts'>"+
 staffRow("Registered",staffTime(x.joined_at_utc))+
 staffRow("Underworld character",linkName(links.underworld))+
 staffRow("Discord account",linkName(links.discord))+
 staffRow("Snowballs / warmth",fmt(x.snowballs)+" / "+fmt(x.warmth))+
 staffRow("Snowflakes / armour",fmt(x.snowflakes)+" / "+fmt(x.armour_hp))+
 staffRow("Last throw",staffTime(x.last_throw_at))+"</div>"+
 "<h4>Integrity signals</h4>"+(issues.length?"<ul class='staff-alerts'>"+issues.map(a=>"<li>"+esc(a)+"</li>").join("")+"</ul>":"<p class='subtle'>No account-specific alert detected. This is not proof of clean play.</p>")+
 "<div class='staff-dossier-columns'><section><h4>Recent score ledger</h4>"+(activity.map(v=>staffRow("Day "+fmt(v.day)+" · "+v.category,fmt(v.points)+" pts · "+staffTime(v.created_at_utc))).join("")||"<p class='subtle'>No points yet.</p>")+"</section>"+
 "<section><h4>Combat history</h4>"+(combat||"<p class='subtle'>No PvP actions yet.</p>")+"<h4>Snow Don &amp; siege history</h4>"+(pve||"<p class='subtle'>No boss or siege actions yet.</p>")+"</section></div>"+
 "<details class='staff-review-history'><summary>Administrative history ("+fmt((p.review_history||[]).length)+")</summary>"+(history||"<p class='subtle'>No prior player-review actions.</p>")+"</details>";
 if(host&&x.review_state!=="disqualified"){
  const action=el("staffReviewAction");
  if(x.review_state==="flagged"&&action.value==="flag")action.value="clear";
  if(x.review_state!=="flagged"&&action.value==="clear")action.value="flag";
  txt("staffReviewHelp",action.value==="flag"?"Type FLAG QA PLAYER exactly, then confirm the flag.":"Type CLEAR QA PLAYER exactly, then confirm the clearance.");
 }
}
async function refreshStaffDirectory(page=1){
 if(!S.staffAllowed||S.staffDirectoryBusy)return;
 if(!Number.isInteger(page)||page<1||page>100)return;
 const who=String(S.session?.player_id||""),seq=++S.staffDirectorySeq;
 S.staffDirectoryBusy=true;showStaffPlayerDesk();
 try{
  const params=new URLSearchParams({q:el("staffPlayerQuery").value.trim(),
   city:el("staffPlayerCity").value,state:el("staffPlayerState").value,page:String(page)});
  const result=await get("/v1/staff/players?"+params.toString());
  if(seq!==S.staffDirectorySeq||String(S.session?.player_id)!==who||!S.staffAllowed)return;
  if(result.scope!=="ISOLATED_QA_ONLY"||result.read_only!==true||!Array.isArray(result.players))throw Error("Unexpected player directory scope");
  S.staffDirectory=result;
 }catch(e){notice(e.message||"Player search failed.","error")}
 finally{if(seq===S.staffDirectorySeq){S.staffDirectoryBusy=false;showStaffPlayerDesk()}}
}
async function inspectStaffPlayer(id){
 if(!S.staffAllowed||!/^\d{1,19}$/.test(String(id)))return;
 const who=String(S.session?.player_id||""),seq=++S.staffDossierSeq;
 S.staffSelected=String(id);S.staffDossier=null;S.staffDossierBusy=true;showStaffPlayerDesk();
 try{
  const result=await get("/v1/staff/players/"+encodeURIComponent(id));
  if(seq!==S.staffDossierSeq||String(S.session?.player_id)!==who||!S.staffAllowed)return;
  if(result.scope!=="ISOLATED_QA_ONLY"||result.read_only!==true||result.profile?.player_id!==id)throw Error("Invalid player dossier");
  S.staffDossier=result;
  el("staffReviewReason").value="";el("staffReviewConfirm").value="";
 }catch(e){notice(e.message||"Dossier unavailable.","error")}
 finally{if(seq===S.staffDossierSeq){S.staffDossierBusy=false;showStaffPlayerDesk()}}
}
async function submitStaffReview(){
 if(!S.staffAllowed||!S.staffRole?.can_review||!S.staffDossier||S.staffReviewBusy)return;
 const x=S.staffDossier.profile,action=el("staffReviewAction").value;
 const phrase=action==="flag"?"FLAG QA PLAYER":"CLEAR QA PLAYER";
 const reason=el("staffReviewReason").value.trim(),confirmation=el("staffReviewConfirm").value.trim();
 if(reason.length<12)return notice("Provide a specific reason of at least 12 characters.","error");
 if(confirmation!==phrase)return notice("Type "+phrase+" exactly to confirm this QA review.","error");
 if(!window.confirm((action==="flag"?"Flag":"Clear")+" "+x.mr_username+"? This changes the shared QA eligibility review state and writes to the audit log."))return;
 const who=String(S.session?.player_id||"");
 S.staffReviewBusy=true;showStaffPlayerDesk();
 try{
  const result=await post("/v1/staff/players/review",{
   player_id:x.player_id,action,expected_state:x.review_state,reason,confirmation,
   request_id:nextActionId()
  },true);
  if(String(S.session?.player_id)!==who||!S.staffAllowed)return;
  if(result.scope!=="ISOLATED_QA_ONLY"||result.player_id!==x.player_id)throw Error("Unexpected review response");
  notice(result.replayed?"Previously recorded review confirmed.":"QA player review audited.","success");
  await inspectStaffPlayer(x.player_id);
  await refreshStaffDirectory(S.staffDirectory?.page||1);
  void refreshStaffDashboard();
 }catch(e){notice(e.message||"Review action was not applied.","error")}
 finally{S.staffReviewBusy=false;showStaffPlayerDesk()}
}
function downloadStaffPlayerDossier(){
 if(!S.staffAllowed||!S.staffDossier)return;
 const result={...S.staffDossier,exported_at:new Date().toISOString(),
  notice:"CONFIDENTIAL QA STAFF RECORD · NO OFFICIAL PRIZES · DO NOT SHARE PUBLICLY"};
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
 try{const a=document.createElement("a");a.href=url;
  a.download="snowfall-qa-player-"+S.staffDossier.profile.player_id+".json";a.click()}
 finally{setTimeout(()=>URL.revokeObjectURL(url),1000)}
 notice("Private player dossier exported.","success");
}
