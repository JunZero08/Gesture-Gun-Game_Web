// ===================== Gesture Gun — Web Port =====================
// 원본: Python OpenCV + MediaPipe 데스크톱 앱 (main.py)
// 이 웹 버전은 게임 내용/로직을 그대로 유지하며 HTML5 Canvas + JS로 포팅됨.
// 원본 main.py, requirements.txt, hand_landmarker.task, gesture_gun_save.json은 수정하지 않음.

/* ---------- 상수 ---------- */
const EXT_RATIO = 1.40;
const EXT_RATIO_PINKY = 1.30;
const TRIG_DOWN = 0.40;
const TRIG_UP = 0.55;
const PUNCH_DOWN = 0.45;
const PUNCH_UP = 0.70;
const MELEE_COOLDOWN = 0.5;
const MELEE_RANGE = 120;
const MELEE_DMG = 40;
const MELEE_COMBO_MAX = 5;
const MELEE_COMBO_BONUS = 1.2;
const MELEE_COMBO_TIMEOUT = 1.5;
const AIM_LOCK_BACK = 0.07;
const DWELL_TIME = 0.9;
const PALM_RELOAD = 0.35;
const RENDER_MAX_W = 1280;
const RENDER_MIN_W = 480;
const INF = 1e6;
const EXT_HYST = 0.18;
const ANG_ON = 148.0;
const ANG_OFF = 128.0;
const LOST_GRACE = 0.18;

const FINGER_IDS = [[5,6,7,8],[9,10,11,12],[13,14,15,16],[17,18,19,20]];
const CONN = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
              [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];

const DIFFS = [
  {name:"EASY", zhp:0.75, zdmg:0.6, coin:1.0, spawn:1.25},
  {name:"NORMAL", zhp:1.0, zdmg:1.0, coin:1.0, spawn:1.0},
  {name:"HARD", zhp:1.4, zdmg:1.5, coin:1.3, spawn:0.8},
];

const WEAPONS = {
  // 권총류
  pistol:  {name:"PISTOL",   dmg:34,  rate:0.30, mag:12, reload:1.0, pellets:1, spread:0,  auto:false, pierce:false, price:0,   pack:0,  packcost:0,   pvp:11,  pvp_spread:0.015, col:[220,220,220],  snd:"shot"},
  glock17: {name:"GLOCK 17", dmg:28,  rate:0.22, mag:17, reload:1.2, pellets:1, spread:0,  auto:false, pierce:false, price:450, pack:34, packcost:55,  pvp:9,   pvp_spread:0.012, col:[200,200,200], snd:"shot"},
  m1911:   {name:"M1911", dmg:42,  rate:0.35, mag:7, reload:1.5, pellets:1, spread:0,  auto:false, pierce:false, price:500, pack:14, packcost:65, pvp:13,  pvp_spread:0.008, col:[180,160,120], snd:"shot"},
  deagle:  {name:"DESERT EAGLE", dmg:85, rate:0.55, mag:7, reload:2.0, pellets:1, spread:5, auto:false, pierce:true, price:1200, pack:14, packcost:120, pvp:25, pvp_spread:0.02, col:[220,180,60], snd:"shot"},
  // 기관단총 / PDW
  smg:     {name:"SMG",     dmg:15, rate:0.085, mag:30, reload:1.5, pellets:1, spread:18, auto:true, pierce:false, price:300, pack:60, packcost:60, pvp:4.5, pvp_spread:0.05, col:[80,220,255], snd:"smg"},
  mp5:     {name:"MP5", dmg:22, rate:0.07, mag:30, reload:1.6, pellets:1, spread:14, auto:true, pierce:false, price:650, pack:60, packcost:70, pvp:5, pvp_spread:0.04, col:[100,180,255], snd:"smg"},
  ump45:   {name:"UMP45", dmg:30, rate:0.10, mag:25, reload:1.8, pellets:1, spread:10, auto:true, pierce:false, price:700, pack:50, packcost:75, pvp:6, pvp_spread:0.025, col:[140,120,200], snd:"smg"},
  mac10:   {name:"MAC-10", dmg:18, rate:0.05, mag:30, reload:1.4, pellets:1, spread:22, auto:true, pierce:false, price:550, pack:60, packcost:60, pvp:4, pvp_spread:0.07, col:[150,150,150], snd:"smg"},
  vector:  {name:"VECTOR", dmg:24, rate:0.055, mag:25, reload:1.5, pellets:1, spread:10, auto:true, pierce:false, price:800, pack:50, packcost:70, pvp:5.5, pvp_spread:0.03, col:[255,100,200], snd:"smg"},
  p90:     {name:"P90", dmg:20, rate:0.065, mag:50, reload:2.2, pellets:1, spread:16, auto:true, pierce:false, price:850, pack:100, packcost:80, pvp:4.5, pvp_spread:0.05, col:[255,200,100], snd:"smg"},
  mp7:     {name:"MP7", dmg:18, rate:0.06, mag:40, reload:1.8, pellets:1, spread:12, auto:true, pierce:true, price:950, pack:80, packcost:90, pvp:5, pvp_spread:0.03, col:[200,150,255], snd:"smg"},
  // 돌격소총
  rifle:   {name:"RIFLE",   dmg:26, rate:0.13, mag:30, reload:1.8, pellets:1, spread:7,  auto:true, pierce:false, price:550, pack:60, packcost:75, pvp:6.5, pvp_spread:0.025, col:[255,180,80], snd:"smg"},
  ak47:    {name:"AK-47", dmg:38, rate:0.09, mag:30, reload:2.0, pellets:1, spread:12, auto:true, pierce:false, price:900, pack:60, packcost:90, pvp:7, pvp_spread:0.03, col:[120,100,60], snd:"smg"},
  m4a1:    {name:"M4A1", dmg:32, rate:0.085, mag:30, reload:1.8, pellets:1, spread:8, auto:true, pierce:false, price:1100, pack:60, packcost:85, pvp:6, pvp_spread:0.02, col:[100,140,100], snd:"smg"},
  scar:    {name:"SCAR-L", dmg:35, rate:0.095, mag:30, reload:2.0, pellets:1, spread:10, auto:true, pierce:false, price:1200, pack:60, packcost:95, pvp:6.5, pvp_spread:0.025, col:[80,160,100], snd:"smg"},
  g36:     {name:"G36C", dmg:30, rate:0.10, mag:30, reload:1.9, pellets:1, spread:11, auto:true, pierce:false, price:1000, pack:60, packcost:85, pvp:6, pvp_spread:0.028, col:[120,160,90], snd:"smg"},
  aug:     {name:"AUG", dmg:34, rate:0.09, mag:30, reload:2.0, pellets:1, spread:9, auto:true, pierce:false, price:1100, pack:60, packcost:90, pvp:6.2, pvp_spread:0.022, col:[90,150,110], snd:"smg"},
  m249:    {name:"M249", dmg:28, rate:0.075, mag:100, reload:3.5, pellets:1, spread:20, auto:true, pierce:false, price:1600, pack:200, packcost:150, pvp:5, pvp_spread:0.06, col:[100,100,80], snd:"smg"},
  // 샷건
  shotgun: {name:"SHOTGUN", dmg:14, rate:0.80, mag:6, reload:2.0, pellets:8, spread:100, auto:false, pierce:false, price:500, pack:12, packcost:80, pvp:4, pvp_spread:0.20, col:[80,150,255], snd:"shotgun"},
  rem870:  {name:"REM 870", dmg:16, rate:0.75, mag:6, reload:2.2, pellets:10, spread:110, auto:false, pierce:false, price:750, pack:12, packcost:90, pvp:5, pvp_spread:0.22, col:[80,100,220], snd:"shotgun"},
  m1014:   {name:"M1014", dmg:18, rate:0.45, mag:7, reload:2.5, pellets:9, spread:95, auto:false, pierce:false, price:900, pack:14, packcost:100, pvp:6, pvp_spread:0.18, col:[60,120,255], snd:"shotgun"},
  // 저격소총
  sniper:  {name:"SNIPER",  dmg:140, rate:1.10, mag:5, reload:2.2, pellets:1, spread:0, auto:false, pierce:true, price:800, pack:10, packcost:100, pvp:42, pvp_spread:0.0, col:[120,255,120], snd:"sniper"},
  m24:     {name:"M24", dmg:160, rate:1.2, mag:5, reload:2.5, pellets:1, spread:0, auto:false, pierce:true, price:1400, pack:10, packcost:130, pvp:40, pvp_spread:0.0, col:[100,200,100], snd:"sniper"},
  awp:     {name:"AWP", dmg:200, rate:1.5, mag:5, reload:2.8, pellets:1, spread:0, auto:false, pierce:true, price:1800, pack:10, packcost:150, pvp:50, pvp_spread:0.0, col:[0,255,180], snd:"sniper"},
  // 로켓 / 폭발물
  rpg7:    {name:"RPG-7", dmg:500, rate:1.5, mag:1, reload:3.0, pellets:1, spread:0, auto:false, pierce:true, price:2500, pack:2, packcost:300, pvp:0, pvp_spread:0.15, col:[255,80,60], snd:"boom"},
  grenade: {name:"GRENADE", dmg:170, rate:0.9, mag:1, reload:0, pellets:1, spread:0, auto:false, pierce:false, price:60, pack:1, packcost:60, pvp:0, pvp_spread:0, col:[60,160,255], snd:"shot"},
};
const GUNS = ["pistol","glock17","m1911","deagle","smg","mp5","ump45","mac10","vector","p90","mp7",
        "rifle","ak47","m4a1","scar","g36","aug","m249",
        "shotgun","rem870","m1014",
        "sniper","m24","awp"];
const ORDER = GUNS.concat(["grenade"]);

const ZT = {
  walker: {hp:70, spd:0.070, dmg:8, h:1.00, skin:[80,170,90], cloth:[120,90,60], coin:5, score:10},
  runner: {hp:40, spd:0.160, dmg:6, h:0.88, skin:[110,190,150], cloth:[60,60,170], coin:7, score:15},
  tank:   {hp:280, spd:0.040, dmg:18, h:1.35, skin:[60,120,70], cloth:[55,55,55], coin:25, score:50},
  boss:   {hp:1400, spd:0.028, dmg:30, h:1.70, skin:[70,70,200], cloth:[30,30,90], coin:150, score:300},
};

const DEFAULT_SAVE = {
  coins:150, owned:["pistol"], equipped:"pistol",
  ammo:{smg:0,rifle:0,shotgun:0,sniper:0},
  items:{medkit:1,armor:0,grenade:2},
  best:{pve_wave:0,pve_score:0,range:0,pvp_matches:0},
  settings:{difficulty:1, sound:true, tutorial_done:false, trig:null},
  kills:0,
};

/* ---------- 수학/유틸 ---------- */
function clamp(v,a,b){ return v<a ? a : v>b ? b : v; }
function C(c){ return [clamp(c[0],0,255),clamp(c[1],0,255),clamp(c[2],0,255)]; }
function hypot(a,b){ return Math.sqrt(a*a+b*b); }
function deg(a){ return a*180/Math.PI; }
function rad(d){ return d*Math.PI/180; }
function randomRange(a,b){ return a+Math.random()*(b-a); }

/* ---------- View / 스케일 ---------- */
class View{
  constructor(){ this.W=1280; this.H=720; this.s=1.0; }
  set(W,H){ this.W=W; this.H=H; this.s=clamp(H/720,0.5,2.4); }
}
const V = new View();
function S(v){ return Math.round(v*V.s); }
function T(th){ return Math.max(1,Math.round(th*V.s)); }
function P2(p){ return [Math.round(p[0]),Math.round(p[1])]; }
function inside(r,p){ return r[0]<=p[0]&&p[0]<=r[2]&&r[1]<=p[1]&&p[1]<=r[3]; }

/* ---------- 캔버스 드로잉 ---------- */
const canvas = document.getElementById('output_canvas');
const ctx = canvas.getContext('2d', {alpha:false});
const video = document.getElementById('input_video');

function resizeCanvas(){
  const container = document.querySelector('.game-container');
  let w = container.clientWidth || window.innerWidth;
  let h = container.clientHeight || window.innerHeight;
  // 내부 고해상도 버퍼 유지, CSS로 맞춤
  canvas.width = V.W;
  canvas.height = V.H;
  video.width = V.W; video.height = V.H;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

function text(imgCtx, s, x, y, size=0.6, col=[255,255,255], th=1, anchor="l"){
  const sc = size*V.s;
  const t = T(th);
  imgCtx.save();
  imgCtx.font = (t*sc)+"px sans-serif";
  imgCtx.textBaseline = "middle";
  let tw = imgCtx.measureText(s).width;
  let tx=x, ty=y;
  if(anchor==="c") tx -= tw/2;
  else if(anchor==="r") tx -= tw;
  // 그림자(검정 외곽)
  imgCtx.strokeStyle = "rgba(0,0,0,0.85)";
  imgCtx.lineWidth = t+Math.max(1,Math.round(2*V.s));
  imgCtx.lineJoin = "round";
  imgCtx.strokeText(s, tx, ty);
  imgCtx.fillStyle = "rgb("+C(col).join(",")+")";
  imgCtx.fillText(s, tx, ty);
  imgCtx.restore();
  return tw;
}

function shade(ctx2, x0,y0,x1,y1, col=[0,0,0], a=0.5){
  const H=ctx2.canvas.height, W=ctx2.canvas.width;
  x0=clamp(x0,0,W); x1=clamp(x1,0,W); y0=clamp(y0,0,H); y1=clamp(y1,0,H);
  if(x1<=x0||y1<=y0) return;
  const cc = "rgb("+C(col).join(",")+")";
  ctx2.save();
  ctx2.globalAlpha=a;
  ctx2.fillStyle=cc;
  ctx2.fillRect(x0,y0,x1-x0,y1-y0);
  ctx2.restore();
}

function bar(ctx2, x,y,w,h, frac, col, back=[40,40,40], border=[210,210,210]){
  frac=clamp(frac,0,1);
  ctx2.fillStyle="rgb("+C(back).join(",")+")";
  ctx2.fillRect(x,y,w,h);
  if(frac>0){
    ctx2.fillStyle="rgb("+C(col).join(",")+")";
    ctx2.fillRect(x,y,Math.floor(w*frac),h);
  }
  ctx2.strokeStyle="rgb("+C(border).join(",")+")";
  ctx2.lineWidth=T(1);
  ctx2.strokeRect(x,y,w,h);
}

function crosshair(ctx2, p, r, col=[255,255,255], th=2){
  const x=Math.round(p[0]), y=Math.round(p[1]);
  const g=Math.max(2,Math.floor(r/3));
  th=Math.max(1,th);
  ctx2.strokeStyle="rgb("+C(col).join(",")+")";
  ctx2.lineWidth=th;
  ctx2.beginPath();
  ctx2.arc(x,y,r,0,Math.PI*2);
  ctx2.stroke();
  for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){
    ctx2.beginPath();
    ctx2.moveTo(x+dx*g,y+dy*g);
    ctx2.lineTo(x+dx*(r+g),y+dy*(r+g));
    ctx2.stroke();
  }
  ctx2.fillStyle="rgb("+C(col).join(",")+")";
  ctx2.beginPath();
  ctx2.arc(x,y,Math.max(1,th),0,Math.PI*2);
  ctx2.fill();
}

function btn_draw(ctx2, rect, label, hover=false, sel=false, col=[70,70,70], prog=0.0, size=0.7, enabled=true, sub=null){
  const [x0,y0,x1,y1] = rect.map(v=>Math.round(v));
  const base = enabled ? col : [45,45,45];
  const bcol = hover&&enabled ? base.map(c=>Math.min(255,c+45)) : base;
  shade(ctx2,x0,y0,x1,y1,bcol,0.82);
  const edge = sel ? [0,255,255] : (hover&&enabled ? [255,255,255] : [150,150,150]);
  ctx2.strokeStyle="rgb("+C(edge).join(",")+")";
  ctx2.lineWidth = (hover||sel)?T(2):1;
  ctx2.strokeRect(x0,y0,x1-x0,y1-y0);
  const tc = enabled ? [255,255,255] : [150,150,150];
  const cy=(y0+y1)/2;
  text(ctx2,label,(x0+x1)/2,cy-S(2),size,tc,1,"c");
  if(sub) text(ctx2,sub,(x0+x1)/2,cy+S(16),size*0.62,[200,200,200],1,"c");
  if(prog>0){
    bar(ctx2,x0+2,y1-S(8),(x1-x0)-4,S(6),prog,[0,255,0],[30,30,30],[30,30,30]);
  }
}

/* ---------- 사운드 (Web Audio API) ---------- */
const SR = 22050;
let audioCtx = null;
function ensureAudio(){
  if(!audioCtx){
    const AC = window.AudioContext || window.webkitAudioContext;
    if(AC) audioCtx = new AC();
  }
  return audioCtx;
}
function wavBuffer(samples){
  const ac = ensureAudio();
  if(!ac) return null;
  const buf = ac.createBuffer(1, samples.length, SR);
  const ch = buf.getChannelData(0);
  for(let i=0;i<samples.length;i++) ch[i]=samples[i];
  return buf;
}
function t(d){ const n=Math.floor(SR*d); const arr=[]; for(let i=0;i<n;i++) arr.push(i/SR); return arr; }
function noise(d,decay,lp=0){
  const tt=t(d); let n=[];
  for(let i=0;i<tt.length;i++) n.push((Math.random()*2-1)*Math.exp(-tt[i]*decay));
  if(lp>1){
    const kernel=Array(lp).fill(1/lp);
    n = convolve(n,kernel,"same");
  }
  return n;
}
function convolve(a,k,mode){
  const out=[];
  const half=Math.floor(k.length/2);
  for(let i=0;i<a.length;i++){
    let s=0;
    for(let j=0;j<k.length;j++){
      const idx=i-half+j;
      if(idx>=0&&idx<a.length) s+=a[idx]*k[j];
    }
    out.push(s);
  }
  return out;
}
function tone(f,d,decay){
  const tt=t(d); return tt.map(x=>Math.sin(2*Math.PI*f*x)*Math.exp(-x*decay));
}
function silence(d){ return new Array(Math.floor(SR*d)).fill(0); }
function cat(...a){ return a.flat(); }
function env(d, attack=0.005, decay=0.15){
  const n=Math.floor(SR*d); const out=[]; const a=Math.max(1,Math.floor(SR*attack));
  for(let i=0;i<n;i++) out.push(i<a? i/a : Math.exp(-(i-a)/(SR*decay)));
  return out;
}
function gunshot(dur, noiseDecay, lowFreq, highFreq, noiseAmp=0.9, lowAmp=0.5, highAmp=0.35){
  const n=Math.floor(SR*dur); const e=env(dur); const out=[];
  for(let i=0;i<n;i++){
    const tt=i/SR;
    const nz=(Math.random()*2-1)*Math.exp(-tt*noiseDecay);
    const low=Math.sin(2*Math.PI*lowFreq*tt)*Math.exp(-tt*40);
    const high=Math.sin(2*Math.PI*highFreq*tt)*Math.exp(-tt*80);
    out.push((nz*noiseAmp + low*lowAmp + high*highAmp)*e[i]);
  }
  return out;
}

class Sfx{
  constructor(on=true){ this.on=on; this.bufs={}; this.ac=null; this.inited=false; }
  init(){
    if(!this.on) return;
    ensureAudio();
    const tt=t(0.2);
    this.bufs = {
      "shot": gunshot(0.18, 45, 110, 900),
      "smg": gunshot(0.09, 70, 160, 1100),
      "shotgun": gunshot(0.35, 12, 60, 500, 1.0, 0.8, 0.5),
      "sniper": gunshot(0.45, 8, 50, 300, 0.8, 1.0, 0.4),
      "empty": tone(1500,0.05,100).map(v=>v*0.4),
      "reload": tone(400,0.06,100).concat(silence(0.12), tone(650,0.07,100)),
      "hit": tone(800,0.06,80).map((v,i)=>v*0.7 + noise(0.04,100)[i]*0.4),
      "melee": noise(0.12,60,5).map((v,i)=>v*0.8).concat(tone(120,0.12,40).map((v,i)=>v*0.5)),
      "kill": tt.map(x=>Math.sin(2*Math.PI*(500*x-1200*x*x))*Math.exp(-x*10)*0.8),
      "hurt": tone(100,0.25,25).concat(noise(0.25,30,10).map(v=>v*0.7)).flat(),
      "boom": noise(0.8,5,20).map((v,i)=>v*1.1).concat(tone(40,0.8,8).map(v=>v*0.9)),
      "coin": tone(1100,0.08,50).map((v,i)=>v + tone(1700,0.12,40)[i]),
      "ui": tone(650,0.05,90).map(v=>v*0.5),
      "beep": tone(850,0.09,60).map(v=>v*0.5),
      "go": tone(1300,0.25,10).map(v=>v*0.7),
      "win": tone(550,0.12,15).map((v,i)=>v + tone(800,0.12,15)[i] + tone(1100,0.3,10)[i]),
    };
    // 클리핑 방지 정규화
    for(const k in this.bufs){
      let mx=0; for(const v of this.bufs[k]) mx=Math.max(mx,Math.abs(v));
      if(mx>1) for(let i=0;i<this.bufs[k].length;i++) this.bufs[k][i]/=mx;
    }
    this.inited=true;
  }
  play(name){
    if(!this.on||!this.inited||!this.bufs[name]) return;
    const ac=audioCtx; if(!ac) return;
    const buf=wavBuffer(this.bufs[name]);
    if(!buf) return;
    const src=ac.createBufferSource();
    src.buffer=buf;
    src.connect(ac.destination);
    try{ src.start(0); }catch(e){}
  }
}
const sfx = new Sfx(true);

/* ---------- 이펙트 ---------- */
class FX{
  constructor(){ this.p=[]; this.t=[]; this.rings=[]; this.shake=0; this.hurt=0; this.flash=0; }
  burst(x,y,col,n=10,speed=240,life=0.5,size=3,grav=600){
    if(this.p.length>700) return;
    for(let i=0;i<n;i++){
      const a=Math.random()*Math.PI*2;
      const sp=(0.2+Math.random()*0.8)*speed*V.s;
      this.p.push([x,y,Math.cos(a)*sp,Math.sin(a)*sp,life*(0.6+Math.random()*0.6),life,C(col),Math.max(1,size*V.s),grav*V.s]);
    }
  }
  text(x,y,s,col=[255,255,255],size=0.7){ this.t.push([x,y,0.9,s,C(col),size]); }
  ring(x,y,r,col,life=0.4){ this.rings.push([x,y,r,C(col),life,life]); }
  update(dt){
    for(const p of this.p){ p[3]+=p[8]*dt; p[0]+=p[2]*dt; p[1]+=p[3]*dt; p[4]-=dt; }
    this.p=this.p.filter(p=>p[4]>0);
    for(const t of this.t){ t[1]-=55*V.s*dt; t[2]-=dt; }
    this.t=this.t.filter(t=>t[2]>0);
    for(const r of this.rings) r[4]-=dt;
    this.rings=this.rings.filter(r=>r[4]>0);
    this.shake=Math.max(0,this.shake-40*dt);
    this.hurt=Math.max(0,this.hurt-dt*1.2);
    this.flash=Math.max(0,this.flash-dt*2.5);
  }
  draw(imgCtx){
    for(const r of this.rings){
      const k=1-r[4]/r[5];
      const rad=Math.max(1,Math.round(r[2]*(0.3+0.7*k)));
      imgCtx.strokeStyle="rgb("+r[3].join(",")+")";
      imgCtx.lineWidth=T(3);
      imgCtx.beginPath(); imgCtx.arc(Math.round(r[0]),Math.round(r[1]),rad,0,Math.PI*2); imgCtx.stroke();
    }
    for(const p of this.p){
      const k=clamp(p[4]/p[5],0,1);
      const c = p[6].map(v=>Math.round(v*(0.35+0.65*k)));
      const rad=Math.max(1,Math.round(p[7]*(0.4+0.6*k)));
      imgCtx.fillStyle="rgb("+c.join(",")+")";
      imgCtx.beginPath(); imgCtx.arc(Math.round(p[0]),Math.round(p[1]),rad,0,Math.PI*2); imgCtx.fill();
    }
    for(const t of this.t){
      text(imgCtx,t[3],t[0],t[1],t[5],t[4],2,"c");
    }
  }
}

/* ---------- 입력 컨트롤러 ---------- */
class Ctl{
  constructor(){ this.present=false; this.pos=[0,0]; this.lock=[0,0]; this.tip=[0,0]; this.center=[0,0]; this.size=60; this.dir=[0,-1]; this.pose="NONE"; this.trigger=false; this.fire_edge=false; this.reload_edge=false; this.switch_edge=false; this.guard=false; this.palm_prog=0; this.pts=null; this.dbg=""; this.tr=0; this.ext=[false,false,false,false]; }
  shot_pos(){ return this.fire_edge ? this.lock : this.pos; }
}
class HandCtl extends Ctl{
  constructor(){ super(); this.raw="NONE"; this.raw_n=0; this.trig=false; this.armed=false; this.hist=[]; this.filt=null; this.smooth=null; this.palm_t=null; this.palm_used=false; this.peace_prev=false; this.switch_cd=0; this.fext=[false,false,false,false]; this.lost_t=0; this.punch_z=null; this.punch_fired=false; this.melee_z=null; this.melee_fired=false; this.melee_ready=true; this.melee_cool=0; this.melee_combo=0; this.melee_combo_t=0; }
  _lost(){
    this.present=false; this.pose=this.raw="NONE"; this.raw_n=0;
    this.trigger=this.trig=this.armed=this.guard=false;
    this.hist=[]; this.filt=null; this.smooth=null; this.pts=null;
    this.palm_t=null; this.palm_used=false; this.palm_prog=0;
    this.peace_prev=false; this.fext=[false,false,false,false]; this.ext=[false,false,false,false];
    this.tr=0; this.lost_t=0;
    this.punch_z=null; this.punch_fired=false;
    this.melee_z=null; this.melee_fired=false; this.melee_ready=true; this.melee_cool=0; this.melee_combo=0; this.melee_combo_t=0;
  }
  update(lm,now,dt){
    this.fire_edge=this.reload_edge=this.switch_edge=false;
    if(!lm){ this.lost_t+=dt; if(this.present&&this.lost_t<LOST_GRACE) return; this._lost(); return; }
    this.lost_t=0;
    const W=V.W,H=V.H;
    const P = lm.map(p=>[p.x*W,p.y*H,p.z*W]);
    const d3=(i,j)=>{ const a=P[i],b=P[j]; return Math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2); };
    const ang=(a,b,c)=>{
      const v1=[P[a][0]-P[b][0],P[a][1]-P[b][1],P[a][2]-P[b][2]];
      const v2=[P[c][0]-P[b][0],P[c][1]-P[b][1],P[c][2]-P[b][2]];
      const n1=hypot(v1[0],v1[1]), n2=hypot(v2[0],v2[1]);
      if(n1<1e-6||n2<1e-6) return 180;
      const cs=clamp((v1[0]*v2[0]+v1[1]*v2[1]+v1[2]*v2[2])/(n1*n2),-1,1);
      return deg(Math.acos(cs));
    };
    const palm=Math.max(d3(0,9),1);
    let ext=[],rat=[],angs=[];
    for(let k=0;k<4;k++){
      const [mcp,pip,dip,tip]=FINGER_IDS[k];
      const r=d3(tip,0)/Math.max(d3(mcp,0),1);
      const a=0.5*(ang(mcp,pip,dip)+ang(pip,dip,tip));
      const on=k===3?EXT_RATIO_PINKY:EXT_RATIO;
      const off=on-EXT_HYST;
      let e;
      if(this.fext[k]) e=!(r<off||a<ANG_OFF);
      else e=r>on&&a>ANG_ON;
      this.fext[k]=e; ext.push(e); rat.push(r); angs.push(a);
    }
    this.ext=ext;
    const [i,m,r_,pk]=ext;
    let raw;
    if(i&&m&&r_&&pk) raw="PALM";
    else if(i&&m&&!r_&&!pk) raw="PEACE";
    else if(i&&!m&&!r_&&!pk) raw="GUN";
    else if(!ext.some(Boolean)) raw="FIST";
    else raw="OTHER";
    if(raw===this.raw) this.raw_n+=1; else { this.raw=raw; this.raw_n=1; }
    if(raw!==this.pose&&this.raw_n>=(raw==="PALM"?3:raw==="FIST"?3:raw==="PEACE"?4:2)) this.pose=raw;
    this.present=true;
    this.guard=this.pose==="FIST";
    if(!this.filt) this.filt=new OneEuro();
    this.smooth=this.filt([P[8][0],P[8][1]],dt);
    this.pos=this.tip=this.smooth;
    this.hist.push([now,this.smooth[0],this.smooth[1]]);
    if(this.hist.length>20) this.hist.shift();
    this.center=[P[9][0],P[9][1]];
    this.size=palm;
    const dx=P[8][0]-P[5][0], dy=P[8][1]-P[5][1];
    const ln=hypot(dx,dy);
    if(ln>4){
      const nd=[dx/ln,dy/ln];
      const [ox,oy]=this.dir;
      let vx=ox+(nd[0]-ox)*0.5, vy=oy+(nd[1]-oy)*0.5;
      const vl=hypot(vx,vy)||1;
      this.dir=[vx/vl,vy/vl];
    }
    this.pts=P.map(p=>[Math.round(p[0]),Math.round(p[1])]);
    const tr=d3(4,5)/palm;
    this.tr=tr;
    const t_up=TRIG_UP,t_down=TRIG_DOWN;
    const prev=this.trig;
    let fired=false;
    if(raw==="GUN"){
      if(tr>t_up) this.armed=true;
      if(this.armed){
        if(!this.trig&&tr<t_down){ this.trig=true; fired=true; }
        else if(this.trig&&tr>t_up) this.trig=false;
      } else this.trig=false;
    } else { this.armed=false; this.trig=false; }
    const cz=P[9][2];
    let punch_fired=false;
    if(this.punch_z!==null){
      const dz=this.punch_z-cz;
      if(dz>PUNCH_DOWN){ punch_fired=true; }
    }
    this.punch_z=cz;
    let melee_fired=false;
    if(this.melee_ready){
      if(this.melee_z!==null){
        const dz_m=this.melee_z-cz;
        if(dz_m>PUNCH_DOWN*0.7 && cz>this.melee_z+PUNCH_DOWN*0.3){
          melee_fired=true;
          this.melee_ready=false;
          this.melee_cool=MELEE_COOLDOWN;
          if(now-this.melee_combo_t<=MELEE_COMBO_TIMEOUT){
            this.melee_combo=Math.min(MELEE_COMBO_MAX, this.melee_combo+1);
          } else {
            this.melee_combo=1;
          }
          this.melee_combo_t=now;
        }
      }
      this.melee_z=cz;
    } else {
      this.melee_cool-=dt;
      if(this.melee_cool<=0){ this.melee_ready=true; this.melee_z=cz; }
    }
    if(this.melee_combo>0 && now-this.melee_combo_t>MELEE_COMBO_TIMEOUT){ this.melee_combo=0; }
    this.trigger=this.trig||fired||punch_fired;
    this.fire_edge=fired||punch_fired;
    this.melee_edge=melee_fired;
    this.lock=this.pos;
    if(this.fire_edge){
      let locked=false;
      for(let k=this.hist.length-1;k>=0;k--){
        if(this.hist[k][0]<=now-AIM_LOCK_BACK){ this.lock=[this.hist[k][1],this.hist[k][2]]; locked=true; break; }
      }
      if(!locked){ this.lock=[this.hist[0][1],this.hist[0][2]]; }
    }
    if(this.pose==="PALM"){
      if(this.palm_t===null) this.palm_t=now;
      this.palm_prog=clamp((now-this.palm_t)/PALM_RELOAD,0,1);
      if(!this.palm_used&&now-this.palm_t>=PALM_RELOAD){ this.reload_edge=true; this.palm_used=true; }
    } else { this.palm_t=null; this.palm_used=false; this.palm_prog=0; }
    const pe=this.pose==="PEACE";
    if(pe&&!this.peace_prev&&now>=this.switch_cd){ this.switch_edge=true; this.switch_cd=now+0.6; }
    this.peace_prev=pe;
    const punch_dbg=this.punch_z!==null?(this.punch_z-cz).toFixed(2):"0.00";
    const melee_dbg=this.melee_z!==null?(this.melee_z-cz).toFixed(2):"0.00";
    this.dbg=`${this.pose}  thumb${tr.toFixed(2)} arm=${this.armed?1:0} punch=${punch_dbg} melee=${melee_dbg} ${this.trigger?"FIRE":""}`;
  }
}
class MouseCtl extends Ctl{
  constructor(){ super(); this.present=true; this.mx=V.W/2; this.my=V.H/2; this.down=false; this.prev=false; this.req_reload=false; this.req_switch=false; this.size=55; }
  event(ev,x,y){ this.mx=x; this.my=y; if(ev==="mousedown"){ this.down=true; if(ev.which===1||ev.button===0){} } if(ev==="mouseup") this.down=false; if(ev==="contextmenu"){ this.req_reload=true; } }
  update(lm,now,dt){
    this.present=true;
    this.pos=this.tip=this.center=this.lock=[this.mx,this.my];
    this.trigger=this.down;
    this.fire_edge=this.down&&!this.prev;
    this.prev=this.down;
    this.reload_edge=this.req_reload; this.req_reload=false;
    this.switch_edge=this.req_switch; this.req_switch=false;
    this.pose="MOUSE";
  }
}
class BotCtl extends Ctl{
  constructor(){ super(); this.present=true; this.center=[V.W*0.8,V.H*0.5]; this.target=this.center.slice(); this.t_next=0; this.fire_cd=1.5; }
  update(now,dt,foe){
    const W=V.W,H=V.H;
    if(now>this.t_next){ this.target=[randomRange(0.62,0.93)*W,randomRange(0.22,0.85)*H]; this.t_next=now+randomRange(0.7,1.6); }
    let [cx,cy]=this.center;
    const dx=this.target[0]-cx, dy=this.target[1]-cy;
    const d=hypot(dx,dy);
    if(d>1){ const st=Math.min(d,240*V.s*dt); cx+=dx/d*st; cy+=dy/d*st; }
    this.center=[cx,cy];
    this.size=S(70);
    const ang=Math.atan2(foe.center[1]-cy, foe.center[0]-cx)+(Math.random()-0.5)*0.1;
    this.dir=[Math.cos(ang),Math.sin(ang)];
    this.tip=[cx+this.dir[0]*S(62), cy+this.dir[1]*S(62)];
    this.pos=this.tip.slice();
    this.fire_edge=this.trigger=false; this.reload_edge=this.switch_edge=false;
    this.fire_cd-=dt;
    if(this.fire_cd<=0&&foe.present){ this.fire_edge=this.trigger=true; this.fire_cd=randomRange(0.45,1.0); }
    this.pose="BOT";
  }
}
class OneEuro{
  constructor(mincut=1.6,beta=0.015,dcut=1.0){ this.mincut=mincut; this.beta=beta; this.dcut=dcut; this.x=null; this.dx=[0,0]; }
  reset(){ this.x=null; this.dx=[0,0]; }
  _a(cut,dt){ return 1/(1+(1/(2*Math.PI*cut))/dt); }
  __call__(p,dt){
    dt=Math.max(dt,1e-3);
    if(this.x===null){ this.x=[p[0],p[1]]; this.dx=[0,0]; return this.x; }
    const ad=this._a(this.dcut,dt);
    const rx=(p[0]-this.x[0])/dt/V.s, ry=(p[1]-this.x[1])/dt/V.s;
    this.dx=[this.dx[0]+(rx-this.dx[0])*ad, this.dx[1]+(ry-this.dx[1])*ad];
    const a=this._a(this.mincut+this.beta*hypot(this.dx[0],this.dx[1]),dt);
    this.x=[this.x[0]+(p[0]-this.x[0])*a, this.x[1]+(p[1]-this.x[1])*a];
    return this.x;
  }
}

/* ---------- 무기와 저장 ---------- */
class Arsenal{
  constructor(guns,reserve,infinite=false,grenades=0,equipped=null,allow_grenade=false){
    this.guns=guns||["pistol"];
    this.infinite=infinite; this.grenades=grenades; this.allow_grenade=allow_grenade;
    this.mag={}; this.res={};
    for(const g of this.guns){
      const m=WEAPONS[g].mag;
      if(infinite||g==="pistol"){ this.res[g]=INF; this.mag[g]=m; }
      else { const have=parseInt(reserve[g]||0,10); const take=Math.min(m,have); this.mag[g]=take; this.res[g]=have-take; }
    }
    this.cur = equipped&&this.guns.includes(equipped)?equipped:this.guns[0];
    this.last=-9; this.reload_end=null; this.reload_start=0;
  }
  get w(){ return WEAPONS[this.cur]; }
  slots(){ return this.guns.concat(this.allow_grenade&&this.grenades>0?["grenade"]:[]); }
  select(name){
    if(name==="grenade"){ if(!this.allow_grenade) return false; }
    else if(!this.guns.includes(name)) return false;
    if(name!==this.cur){ this.cur=name; this.reload_end=null; }
    return true;
  }
  cycle(d=1){
    const order=this.guns.concat(this.allow_grenade&&this.grenades>0?["grenade"]:[]);
    if(!order.includes(this.cur)){ this.select(order[0]); return; }
    this.select(order[(order.indexOf(this.cur)+d)%order.length]);
  }
  reloading(){ return this.reload_end!==null; }
  reload_frac(now){
    if(this.reload_end===null) return 0;
    return clamp((now-this.reload_start)/Math.max(0.01,this.reload_end-this.reload_start),0,1);
  }
  start_reload(now){
    const c=this.cur;
    if(c==="grenade"||this.reloading()) return false;
    if(this.mag[c]>=WEAPONS[c].mag||this.res[c]<=0) return false;
    this.reload_start=now;
    this.reload_end=now+WEAPONS[c].reload;
    return true;
  }
  update(now){
    if(this.reload_end!==null&&now>=this.reload_end){
      const c=this.cur;
      const need=WEAPONS[c].mag-this.mag[c];
      const take=Math.min(need,this.res[c]);
      this.mag[c]+=take;
      if(this.res[c]<INF/2) this.res[c]-=take;
      this.reload_end=null;
      return true;
    }
    return false;
  }
  shoot(now){
    const c=this.cur, w=WEAPONS[c];
    if(this.reloading()) return "reloading";
    if(now-this.last<w.rate) return "busy";
    if(c==="grenade"){
      if(this.grenades<=0) return "empty";
      this.grenades-=1; this.last=now; return "ok";
    }
    if(this.mag[c]<=0){ this.last=now; return this.start_reload(now)?"reload":"empty"; }
    this.mag[c]-=1; this.last=now; return "ok";
  }
  ammo_text(){
    const c=this.cur;
    if(c==="grenade") return "x"+this.grenades;
    const r=this.res[c];
    return this.mag[c]+" / "+(r>=INF/2?"INF":String(r));
  }
  totals(){ const o={}; for(const g of this.guns) if(this.res[g]<INF/2) o[g]=this.mag[g]+this.res[g]; return o; }
}
class Dwell{
  constructor(){ this.key=null; this.t=0; this.done=false; }
  update(hover,dt){
    if(hover!==this.key){ this.key=hover; this.t=0; this.done=false; }
    if(hover===null||this.done) return null;
    this.t+=dt;
    if(this.t>=DWELL_TIME){ this.done=true; return hover; }
    return null;
  }
  prog(key){
    if(key!==this.key) return 0;
    return this.done?1:clamp(this.t/DWELL_TIME,0,1);
  }
}

/* ---------- 세이브 ---------- */
class Save{
  constructor(){
    this.d=JSON.parse(JSON.stringify(DEFAULT_SAVE));
    try{
      const raw=localStorage.getItem("gesture_gun_save");
      if(raw){ const data=JSON.parse(raw); for(const k in data){ const v=data[k]; if(typeof v==="object"&&v!==null&&typeof this.d[k]==="object"&&this.d[k]!==null){ for(const kk in v) this.d[k][kk]=v[kk]; } else this.d[k]=v; } }
    }catch(e){}
    if(!this.d.owned.includes(this.d.equipped)) this.d.equipped="pistol";
    if(!this.d.owned.includes("pistol")) this.d.owned.unshift("pistol");
  }
  write(){
    try{ localStorage.setItem("gesture_gun_save",JSON.stringify(this.d)); }catch(e){}
  }
}

/* ---------- 게임 모드 ---------- */
class Mode{
  constructor(g){ this.g=g; this.cursor=true; }
  leave(){}
  update(dt,now){}
  draw(bg,now){ const c=bg.getContext('2d'); c.drawImage(bg,0,0); return bg; }
}
class PlayMode extends Mode{
  constructor(g){ super(g); this.cursor=false; this.dwell=new Dwell(); this.btns={}; this.ar=null; }
  menu_rect(){ return [V.W-S(124),S(12),V.W-S(12),S(52)]; }
  layout(){ this.btns={"menu":[this.menu_rect(),"MENU",""]}; }
  hud_hit(pos){ return Object.values(this.btns).some(b=>inside(b[0],pos)); }
  run_dwell(dt,ctl){
    let hov=null;
    if(ctl.present){
      for(const k in this.btns){ if(inside(this.btns[k][0],ctl.pos)){ hov=k; break; } }
    }
    return this.dwell.update(hov,dt);
  }
  weapon_inputs(ctl,now){
    const ar=this.ar, g=this.g;
    if(ar.update(now)) g.sfx.play("reload");
    if(ctl.switch_edge||g.take("cycle")){ ar.cycle(1); g.sfx.play("ui"); }
    if(ctl.reload_edge||g.take("reload")){ if(ar.start_reload(now)) g.sfx.play("reload"); }
    for(let i=0;i<ORDER.length;i++){ if(g.take("w"+(i+1))){ if(ar.select(ORDER[i])) g.sfx.play("ui"); } }
  }
  draw_weapon_hud(imgCtx,now,y_text){
    const ar=this.ar, w=ar.w;
    text(imgCtx,w.name,V.W/2,y_text-S(26),0.8,w.col,2,"c");
    const txt=ar.reloading()?"RELOADING":ar.ammo_text();
    text(imgCtx,txt,V.W/2,y_text,0.85,ar.reloading()?[0,200,255]:[255,255,255],2,"c");
    if(ar.reloading()) bar(imgCtx,V.W/2-S(80),y_text+S(8),S(160),S(8),ar.reload_frac(now),[0,200,255]);
  }
  draw_cross(imgCtx,ctl,now){
    if(!ctl.present){
      if(Math.floor(now*2)%2===0) text(imgCtx,"SHOW YOUR HAND (gun pose)",V.W/2,V.H/2,0.8,[0,255,255],2,"c");
      return;
    }
    const ar=this.ar, w=ar.w;
    const r=S(16)+Math.floor(S(w.spread)*0.35);
    const col=ar.reloading()?[0,200,255]:[255,255,255];
    crosshair(imgCtx,ctl.pos,r,col,T(2));
    if(ar.reloading()){
      ctx2_ellipse(imgCtx,ctl.pos,[r+S(8),r+S(8)],0,-90,-90+360*ar.reload_frac(now),[0,200,255],T(3));
    }
    if(ctl.palm_prog>0&&!ar.reloading()){
      ctx2_ellipse(imgCtx,ctl.pos,[r+S(14),r+S(14)],0,-90,-90+360*ctl.palm_prog,[0,255,0],T(3));
    }
  }
  draw_menu_btn(imgCtx,ctl){
    const [r,label,_]=this.btns.menu;
    const hov=ctl.present&&inside(r,ctl.pos);
    btn_draw(imgCtx,r,label,hov,false,[70,40,40],this.dwell.prog("menu"),0.6);
  }
}
function ctx2_ellipse(c,center,[rx,ry],rotation,startAngle,endAngle,color,lineWidth){
  c.save();
  c.translate(center[0],center[1]);
  c.rotate(rotation*Math.PI/180);
  c.scale(1,ry/rx);
  c.strokeStyle="rgb("+C(color).join(",")+")";
  c.lineWidth=lineWidth;
  c.beginPath();
  c.arc(0,0,rx,startAngle*Math.PI/180,endAngle*Math.PI/180);
  c.stroke();
  c.restore();
}

/* ---------- 메뉴 ---------- */
class Menu extends Mode{
  constructor(g){ super(g); this.cursor=true; }
  items(){
    const d=DIFFS[this.g.save.d.settings.difficulty];
    return [["PVE ZOMBIES","pve"],["PVP DUEL","pvp"],["SHOOTING RANGE","range"],["INVENTORY / SHOP","inv"],["TUTORIAL","tutorial"],["DIFFICULTY: "+d.name,"diff"],["QUIT","quit"]];
  }
  rects(){
    const bw=S(430),bh=S(50),gap=S(10);
    const n=this.items().length;
    const total=n*bh+(n-1)*gap;
    const top=Math.max(S(140),Math.floor(V.H*0.5-total/2+S(10)));
    const x0=V.W/2-bw/2;
    return this.items().map((_,i)=>[x0,top+i*(bh+gap),x0+bw,top+i*(bh+gap)+bh]);
  }
  update(dt,now){
    const ctl=this.g.ptr();
    if(ctl.present&&ctl.fire_edge){
      const rects=this.rects();
      for(let i=0;i<rects.length;i++){
        if(inside(rects[i],ctl.pos)){
          const key=this.items()[i][1];
          this.g.sfx.play("ui");
          if(key==="diff"){
            const st=this.g.save.d.settings;
            st.difficulty=(st.difficulty+1)%DIFFS.length;
            this.g.save.write();
          } else this.g.go(key);
          return;
        }
      }
    }
  }
  draw(bg,now){
    const g=this.g;
    const c=bg.getContext('2d');
    c.globalAlpha=0.42; c.drawImage(bg,0,0); c.globalAlpha=1;
    text(c,"GESTURE GUN",V.W/2,S(86),2.2,[0,220,255],3,"c");
    text(c,"finger-gun shooter",V.W/2,S(118),0.7,[210,210,210],1,"c");
    const ctl=g.ptr();
    const rects=this.rects();
    this.items().forEach(([label,key],i)=>{
      const col = key!=="diff"?[80,60,30]:[60,60,90];
      btn_draw(c,rects[i],label,ctl.present&&inside(rects[i],ctl.pos),false,col,0,0.8);
    });
    if(!g.save.d.settings.tutorial_done&&Math.floor(now*2)%2===0){
      const i=this.items().findIndex(([,k])=>k==="tutorial");
      const r=rects[i];
      text(c,"< START HERE",r[2]+S(14),(r[1]+r[3])/2+S(8),0.7,[0,255,255],2);
    }
    const d=g.save.d;
    text(c,"$ "+d.coins,V.W-S(20),S(40),0.9,[0,215,255],2,"r");
    text(c,"BEST wave "+d.best.pve_wave+" | score "+d.best.pve_score+" | range "+d.best.range+" | kills "+d.kills,V.W-S(20),S(66),0.5,[220,220,220],1,"r");
    const lines=["GUN POSE(index up)=aim  THUMB DOWN=fire","OPEN PALM=reload  PEACE=switch  FIST=guard","Aim a button & fire to select. SPACE fire, R reload, TAB switch, F fullscreen, ESC back"];
    lines.forEach((ln,i)=>text(c,ln,V.W/2,V.H-S(62)+i*S(22),0.48,[230,230,230],1,"c"));
    if(!ctl.present){
      if(Math.floor(now*2)%2===0) text(c,"SHOW YOUR HAND TO THE CAMERA",V.W/2,S(150),0.7,[0,255,255],2);
    }
    g.draw_hand(c,g.hand_main?g.hand_main:null);
    g.draw_cursor(c,ctl);
    return bg;
  }
}

/* ---------- 좀비 ---------- */
class Zombie{
  constructor(kind,wave,hp_mult=1){
    const t=ZT[kind];
    this.kind=kind;
    this.lane=randomRange(0.12,0.88);
    this.z=0;
    this.max=t.hp*(1+0.06*(wave-1))*hp_mult;
    this.hp=this.max;
    this.spd=t.spd*randomRange(0.85,1.2)*(1+0.02*wave);
    this.phase=Math.random()*Math.PI*2;
    this.hurt=0;
    this.bite=0.3;
  }
}
function zgeom(zb){
  const z=zb.z;
  const sc=0.18+0.95*z;
  const h=S(300)*sc*ZT[zb.kind].h;
  const x=V.W*(0.5+(zb.lane-0.5)*(0.35+0.85*z));
  const yf=V.H*(0.40+0.52*z);
  return [x,yf,h];
}
function draw_zombie(imgCtx,zb,now){
  const t=ZT[zb.kind];
  const [x,yf,h]=zgeom(zb);
  if(x<-h||x>V.W+h||yf-h>V.H) return;
  const fog=0.55+0.45*zb.z;
  const colf=(c)=>[c[0]*fog,c[1]*fog,c[2]*fog];
  const skin=colf(t.skin), cloth=colf(t.cloth), dark=colf([35,30,30]);
  const sw=Math.sin(now*(4+zb.spd*20)+zb.phase);
  const lw=Math.max(2,Math.floor(h*0.13));
  for(const sg of [-1,1]){
    const lx=x+sg*h*0.09;
    imgCtx.strokeStyle="rgb("+C(dark).join(",")+")";
    imgCtx.lineWidth=lw;
    imgCtx.beginPath(); imgCtx.moveTo(lx,yf-h*0.30); imgCtx.lineTo(lx+sw*sg*h*0.05,yf); imgCtx.stroke();
  }
  imgCtx.fillStyle="rgb("+C(cloth).join(",")+")";
  imgCtx.fillRect(x-h*0.19,yf-h*0.72,h*0.38,h*0.42);
  if(zb.kind==="tank"||zb.kind==="boss"){
    imgCtx.fillStyle="rgb("+C(colf([120,120,130])).join(",")+")";
    imgCtx.fillRect(x-h*0.19,yf-h*0.72,h*0.38,h*0.17);
  }
  const aw=Math.max(2,Math.floor(h*0.085));
  for(const sg of [-1,1]){
    const sx=x+sg*h*0.19, sy=yf-h*0.68;
    const ex=x+sg*h*0.30+sw*h*0.02, ey=yf-h*0.50+sw*sg*h*0.03;
    imgCtx.strokeStyle="rgb("+C(skin).join(",")+")";
    imgCtx.lineWidth=aw;
    imgCtx.beginPath(); imgCtx.moveTo(sx,sy); imgCtx.lineTo(ex,ey); imgCtx.stroke();
    imgCtx.fillStyle="rgb("+C(skin).join(",")+")";
    imgCtx.beginPath(); imgCtx.arc(ex,ey,Math.max(2,Math.floor(h*0.05)),0,Math.PI*2); imgCtx.fill();
  }
  const hx=x+sw*h*0.015, hy=yf-h*0.84, hr=h*0.125;
  imgCtx.fillStyle="rgb("+C(skin).join(",")+")";
  imgCtx.beginPath(); imgCtx.arc(hx,hy,Math.max(3,Math.floor(hr)),0,Math.PI*2); imgCtx.fill();
  const er=Math.max(1,Math.floor(hr*0.2));
  for(const sg of [-1,1]){
    imgCtx.fillStyle=[20,20,255];
    imgCtx.beginPath(); imgCtx.arc(hx+sg*hr*0.4,hy-hr*0.1,er,0,Math.PI*2); imgCtx.fill();
  }
  imgCtx.strokeStyle="rgb("+C(dark).join(",")+")";
  imgCtx.lineWidth=Math.max(1,Math.floor(hr*0.12));
  imgCtx.beginPath(); imgCtx.moveTo(hx-hr*0.4,hy+hr*0.45); imgCtx.lineTo(hx+hr*0.4,hy+hr*0.45); imgCtx.stroke();
  if(zb.kind==="boss"){
    imgCtx.strokeStyle=[30,30,230];
    imgCtx.lineWidth=Math.max(2,Math.floor(hr*0.22));
    for(const sg of [-1,1]){
      imgCtx.beginPath(); imgCtx.moveTo(hx+sg*hr*0.6,hy-hr*0.7); imgCtx.lineTo(hx+sg*hr*0.9,hy-hr*1.5); imgCtx.stroke();
    }
  }
  if(zb.hp<zb.max){
    const bw=Math.floor(h*0.4);
    bar(imgCtx,x-bw/2,yf-h*1.04,bw,Math.max(3,Math.floor(h*0.035)),zb.hp/zb.max,zb.kind!=="boss"?[60,60,255]:[0,140,255],[30,30,30],[200,200,200]);
  }
}

/* ---------- PvE ---------- */
class PvE extends PlayMode{
  constructor(g){ super(g); const sv=g.save.d; this.diff=DIFFS[clamp(sv.settings.difficulty,0,DIFFS.length-1)]; this.items=JSON.parse(JSON.stringify(sv.items)); this.ar=new Arsenal(GUNS.filter(w=>sv.owned.includes(w)),sv.ammo,false,sv.items.grenade||0,sv.equipped,true); this.hp=100; this.armor=0; this.wave=0; this.zs=[]; this.queue=[]; this.crates=[]; this.nades=[]; this.spawn_t=0; this.score=0; this.kills=0; this.earned=0; this.state="READY"; this.t_state=g.now+3; this.last_count=4; this.banner=["",0]; this.break_until=0; this.finished=false; this.hit_marker=0; this.new_best=false; this.layout(); }
  layout(){
    const W=V.W,H=V.H; const bw=S(124),bh=S(52),y=H-S(52)-S(14);
    const b={"menu":[this.menu_rect(),"MENU",""]};
    let x=S(14);
    b.medkit=[[x,y,x+bw,y+bh],"MEDKIT","x"+this.items.medkit+" [H]"];
    x+=bw+S(8);
    b.armor=[[x,y,x+bw,y+bh],"ARMOR","x"+this.items.armor+" [A]"];
    const sw=S(84);
    const slots=this.ar.slots();
    x=W-S(14)-slots.length*(sw+S(6))+S(6);
    for(const wn of slots){
      const n = wn==="grenade"?this.ar.grenades:null;
      b["w:"+wn]=[[x,y,x+sw,y+bh],WEAPONS[wn].name.slice(0,7), n!==null?"x"+n:""];
      x+=sw+S(6);
    }
    this.btns=b;
  }
  start_wave(now){
    const n=this.wave;
    let q=Array(4+2*n).fill("walker");
    if(n>=2) q=q.concat(Array(n).fill("runner"));
    if(n>=4) q=q.concat(Array(Math.floor(n/3)).fill("tank"));
    q.sort(()=>Math.random()-0.5);
    if(n%5===0){ q=["boss"].concat(q.slice(0,Math.max(4,Math.floor(q.length/2)))); }
    this.queue=q;
    this.spawn_t=1.2;
    this.banner=["BOSS WAVE "+n,now+2.5];
    this.g.sfx.play("go");
  }
  hurt_player(dmg,ctl){
    dmg*=this.diff.zdmg;
    if(ctl.guard) dmg*=0.5;
    const ab=Math.min(this.armor,dmg*0.5);
    this.armor-=ab;
    this.hp-=dmg-ab;
    this.g.fx.hurt=0.55;
    this.g.fx.shake=Math.max(this.g.fx.shake,9);
    this.g.sfx.play("hurt");
    if(this.hp<=0&&this.state==="PLAY"){ this.hp=0; this.finish(true); }
  }
  finish(over=false){
    if(this.finished) return;
    this.finished=true;
    const sv=this.g.save.d;
    if(over) this.state="OVER";
    for(const [gname,tot] of Object.entries(this.ar.totals())) sv.ammo[gname]=tot;
    sv.items.grenade=this.ar.grenades;
    sv.items=this.items;
    sv.coins+=this.earned;
    sv.kills+=this.kills;
    const b=sv.best;
    if(this.wave>b.pve_wave){ b.pve_wave=this.wave; this.new_best=true; }
    if(this.score>b.pve_score) b.pve_score=this.score;
    this.g.save.write();
  }
  leave(){ this.finish(); }
  kill(zb,head){
    const t=ZT[zb.kind];
    this.zs=this.zs.filter(z=>z!==zb);
    this.kills+=1;
    const c=Math.round((t.coin+(head?3:0))*this.diff.coin);
    this.earned+=c;
    this.score+=t.score*(head?2:1);
    const [x,yf,h]=zgeom(zb);
    const fx=this.g.fx;
    fx.burst(x,yf-h*0.5,[40,40,200],18,300,0.6,3);
    fx.burst(x,yf-h*0.5,[60,170,70],8,200,0.5,3);
    fx.text(x,yf-h,"+$"+c,[0,215,255],0.7);
    this.g.sfx.play("kill");
  }
  damage_zombie(zb,dmg,head,pierce=false){
    const fx=this.g.fx;
    dmg=Math.floor(dmg);
    zb.hp-=dmg;
    zb.hurt=0.18;
    zb.z=Math.max(0,zb.z-Math.min(0.05,dmg*0.0004));
    const [x,yf,h]=zgeom(zb);
    const y=yf-h*(head?0.84:0.5);
    fx.burst(x,y,[30,30,190],6,220,0.4,2);
    fx.text(x+randomRange(-10,10),y-h*0.1,(head?"HEADSHOT -":"-")+dmg,head?[60,60,255]:[80,230,255],0.6);
    this.hit_marker=0.15;
    if(zb.hp<=0) this.kill(zb,head);
    else this.g.sfx.play("hit");
  }
  hit_point(x,y,dmg,pierce){
    for(const c of this.crates){
      if(hypot(x-c[0],y-(c[1]-S(18)))<S(44)){ this.collect(c); return true; }
    }
    let hit=false;
    const sorted=[...this.zs].sort((a,b)=>b.z-a.z);
    for(const zb of sorted){
      const [zx,yf,h]=zgeom(zb);
      const hx=zx, hy=yf-h*0.84, hr=h*0.15;
      const head=hypot(x-hx,y-hy)<=hr;
      const body=Math.abs(x-zx)<=h*0.23&&yf-h*0.74<=y&&y<=yf;
      if(head||body){
        this.damage_zombie(zb,dmg*(head?2:1),head,pierce);
        hit=true;
        if(!pierce) break;
      }
    }
    return hit;
  }
  collect(c){
    this.crates=this.crates.filter(cr=>cr!==c);
    const fx=this.g.fx, r=Math.random();
    let msg="";
    if(r<0.3){ this.items.medkit+=1; msg="MEDKIT +1"; }
    else if(r<0.5){ this.items.armor+=1; msg="ARMOR +1"; }
    else if(r<0.75){
      const lim=this.ar.guns.filter(g=>g!=="pistol");
      if(lim.length){
        const gn=lim[Math.floor(Math.random()*lim.length)];
        this.ar.res[gn]+=WEAPONS[gn].pack;
        msg=WEAPONS[gn].name+" AMMO +"+WEAPONS[gn].pack;
      } else { this.earned+=20; msg="+$20"; }
    } else { this.ar.grenades+=1; msg="GRENADE +1"; }
    fx.text(c[0],c[1]-S(40),msg,[120,255,120],0.8);
    fx.burst(c[0],c[1]-S(20),[120,255,120],14,220,0.5,3);
    this.g.sfx.play("coin");
    this.layout();
  }
  explode(x,y,now){
    const fx=this.g.fx;
    const R=S(190);
    fx.burst(x,y,[40,140,255],40,420,0.7,4);
    fx.burst(x,y,[40,40,255],20,300,0.6,4);
    fx.ring(x,y,R,[60,180,255],0.45);
    fx.shake=Math.max(fx.shake,20);
    fx.flash=0.3;
    this.g.sfx.play("boom");
    for(const zb of this.zs){
      const [zx,yf,h]=zgeom(zb);
      const d=hypot(zx-x,(yf-h*0.4)-y);
      if(d<R+h*0.25) this.damage_zombie(zb,Math.floor(WEAPONS.grenade.dmg*(1-0.5*Math.min(1,d/(R+h*0.25)))),false);
    }
  }
  fire(ctl,now){
    const ar=this.ar, g=this.g;
    const res=ar.shoot(now);
    if(res==="empty"){ g.sfx.play("empty"); return; }
    if(res==="reload"){ g.sfx.play("reload"); return; }
    if(res!=="ok") return;
    const w=ar.w, pos=ctl.shot_pos();
    g.sfx.play(w.snd);
    g.fx.shake=Math.max(g.fx.shake,3+w.dmg/40);
    g.fx.burst(pos[0],pos[1],[120,230,255],5,160,0.15,3,0);
    if(ar.cur==="grenade"){
      this.nades.push([pos[0],pos[1],now+0.55]);
      this.layout();
      return;
    }
    for(let i=0;i<w.pellets;i++){
      const a=Math.random()*Math.PI*2, rr=Math.sqrt(Math.random())*S(w.spread);
      this.hit_point(pos[0]+Math.cos(a)*rr,pos[1]+Math.sin(a)*rr,w.dmg,w.pierce);
    }
  }
  melee_attack(ctl,now){
    const g=this.g;
    g.sfx.play("melee");
    g.fx.shake=Math.max(g.fx.shake,6);
    g.fx.burst(ctl.pos[0],ctl.pos[1],[255,100,100],12,200,0.4,3,0);
    const combo=ctl.melee_combo;
    const bonusMult = combo>1 ? 1+(combo-1)*(MELEE_COMBO_BONUS-1)/(MELEE_COMBO_MAX-1) : 1;
    const dmg=Math.floor(MELEE_DMG*bonusMult);
    let hitAny=false;
    for(const zb of this.zs){
      const [zx,yf,h]=zgeom(zb);
      const dist=hypot(ctl.pos[0]-zx,ctl.pos[1]-(yf-h*0.5));
      if(dist<MELEE_RANGE){
        this.damage_zombie(zb,dmg,false);
        hitAny=true;
      }
    }
    if(hitAny){
      g.fx.text(ctl.pos[0],ctl.pos[1]-S(40), combo>1?"x"+combo+" COMBO":"MELEE", [255,100,100], 0.8);
      g.fx.ring(ctl.pos[0],ctl.pos[1],MELEE_RANGE,[255,80,80],0.4);
    }
  }
  use_item(key,ctl){
    const fx=this.g.fx;
    if(key==="medkit"&&this.items.medkit>0&&this.hp<100){
      this.items.medkit-=1; this.hp=Math.min(100,this.hp+50);
      fx.text(V.W/2,V.H*0.4,"+50 HP",[80,255,80],1.0);
      this.g.sfx.play("coin");
    } else if(key==="armor"&&this.items.armor>0&&this.armor<100){
      this.items.armor-=1; this.armor=Math.min(100,this.armor+50);
      fx.text(V.W/2,V.H*0.4,"+50 ARMOR",[255,200,80],1.0);
      this.g.sfx.play("coin");
    }
    this.layout();
  }
  over_buttons(ctl){ /* stub */ }
  update(dt,now){
    const g=this.g;
    const ctl=g.ptr();
    this.layout();
    this.hit_marker=Math.max(0,this.hit_marker-dt);
    const act=this.run_dwell(dt,ctl);
    if(act==="menu"){ g.go("menu"); return; }
    if(act==="medkit"||act==="armor") this.use_item(act,ctl);
    else if(act&&act.startsWith("w:")){ if(this.ar.select(act.slice(2))) g.sfx.play("ui"); }
    if(g.take("medkit")) this.use_item("medkit",ctl);
    if(g.take("armor")) this.use_item("armor",ctl);
    if(this.state==="READY"){
      const left=this.t_state-now;
      let n=Math.ceil(left);
      if(n!==this.last_count&&n>=1){ this.last_count=n; g.sfx.play("beep"); }
      if(left<=0){ this.state="PLAY"; this.wave=1; this.start_wave(now); }
      this.weapon_inputs(ctl,now);
      return;
    }
    if(this.state==="OVER"){ this.over_buttons(ctl); return; }
    this.weapon_inputs(ctl,now);
    if(ctl.present){
      const ar=this.ar;
      const want=ar.w.auto?ctl.trigger:ctl.fire_edge;
      if(want&&!this.hud_hit(ctl.pos)) this.fire(ctl,now);
      if(ctl.melee_edge&&!this.hud_hit(ctl.pos)) this.melee_attack(ctl,now);
    }
    // 좀비 스폰
    if(this.spawn_t>0){
      this.spawn_t-=dt;
      if(this.spawn_t<=0&&this.queue.length>0){
        const kind=this.queue.shift();
        this.zs.push(new Zombie(kind,this.wave));
        this.spawn_t=randomRange(0.8,1.5);
      }
    }
    for(const nade of this.nades){
      if(now>=nade[2]){
        this.nades=this.nades.filter(x=>x!==nade);
        this.explode(nade[0],nade[1],now);
      }
    }
    for(const zb of this.zs){
      zb.hurt=Math.max(0,zb.hurt-dt);
      if(zb.z<1.0){
        zb.z+=zb.spd*dt;
        const [zx,yf,h]=zgeom(zb);
        if(yf-h*0.84>V.H*0.95) this.hurt_player(10,ctl);
      }
    }
    if(Math.random()<0.02&&this.crates.length<3){
      this.crates.push([randomRange(0.2,0.8)*V.W, randomRange(0.3,0.7)*V.H]);
    }
  }
  draw(bg,now){
    const g=this.g;
    const c=bg.getContext('2d');
    // shake (화면 전체 흔들림)
    if(g.fx.shake>0){
      c.save();
      const sx=(Math.random()-0.5)*g.fx.shake, sy=(Math.random()-0.5)*g.fx.shake;
      c.translate(sx,sy);
      if(g.fx.flash>0){
        c.fillStyle="rgba(255,255,255,"+g.fx.flash+")";
        c.fillRect(0,0,V.W,V.H);
      }
      if(g.fx.hurt>0){
        c.fillStyle="rgba(255,0,0,"+Math.min(1,g.fx.hurt*0.4)+")";
        c.fillRect(0,0,V.W,V.H);
      }
      for(const zb of this.zs) draw_zombie(c,zb,now);
      for(const crate of this.crates){
        c.fillStyle=[120,255,120];
        c.beginPath(); c.arc(crate[0],crate[1]-S(18),S(44),0,Math.PI*2); c.fill();
      }
      c.restore();
    } else {
      if(g.fx.flash>0){
        c.fillStyle="rgba(255,255,255,"+g.fx.flash+")";
        c.fillRect(0,0,V.W,V.H);
      }
      if(g.fx.hurt>0){
        c.fillStyle="rgba(255,0,0,"+Math.min(1,g.fx.hurt*0.4)+")";
        c.fillRect(0,0,V.W,V.H);
      }
      for(const zb of this.zs) draw_zombie(c,zb,now);
      for(const crate of this.crates){
        c.fillStyle=[120,255,120];
        c.beginPath(); c.arc(crate[0],crate[1]-S(18),S(44),0,Math.PI*2); c.fill();
      }
    }
    this.draw_weapon_hud(c,now,V.H-S(40));
    this.draw_cross(c,ctl,now);
    this.draw_menu_btn(c,ctl);
    text(c,"HP "+Math.floor(this.hp)+"  ARMOR "+Math.floor(this.armor),S(14),S(34),0.7,[255,255,255],2);
    text(c,"WAVE "+this.wave+"  SCORE "+this.score+"  $ "+this.earned,V.W/2,S(34),0.7,[255,255,255],2,"c");
    // 근접 공격 쿨다운 / 콤보 HUD
    if(ctl&&ctl.present){
      if(ctl.melee_combo>0){
        text(c,"MELEE x"+ctl.melee_combo+" COMBO",V.W/2,S(100),0.8,[255,100,100],2,"c");
      } else if(!ctl.melee_ready){
        const coolLeft=Math.max(0,Math.ceil(ctl.melee_cool));
        text(c,"MELEE "+coolLeft+"s",V.W/2,S(100),0.8,[255,200,100],2,"c");
      } else {
        text(c,"MELEE READY",V.W/2,S(100),0.8,[100,255,100],2,"c");
      }
    }
    if(this.state==="READY") text(c,"STARTING... "+Math.ceil(this.t_state-now),V.W/2,V.H/2,1.5,[0,255,255],3,"c");
    if(this.state==="OVER") text(c,"GAME OVER",V.W/2,V.H/2,1.5,[255,60,60],3,"c");
    this.g.fx.draw(c);
    g.draw_hand(c,g.hand_main);
    g.draw_cursor(c,ctl);
    return bg;
  }
}

/* ---------- PVP (간단) ---------- */
class PvP extends PlayMode{
  constructor(g){ super(g); const sv=g.save.d; this.ar=new Arsenal(GUNS.filter(w=>sv.owned.includes(w)),sv.ammo,false,sv.items.grenade||0,sv.equipped,true); this.hp=100; this.foe_hp=100; this.foe=new BotCtl(); this.layout(); this.state="PLAY"; }
  layout(){
    const W=V.W,H=V.H;
    const b={"menu":[this.menu_rect(),"MENU",""]};
    this.btns=b;
  }
  update(dt,now){
    const g=this.g;
    const ctl=g.ptr();
    const act=this.run_dwell(dt,ctl);
    if(act==="menu"){ g.go("menu"); return; }
    this.weapon_inputs(ctl,now);
    this.foe.update(now,dt,ctl);
    if(ctl.present){
      const ar=this.ar;
      const want=ar.w.auto?ctl.trigger:ctl.fire_edge;
      if(want&&!this.hud_hit(ctl.pos)) this.fire(ctl,now);
    }
    if(this.foe.fire_edge){
      const pos=this.foe.shot_pos();
      const w=this.ar.w;
      if(hypot(pos[0]-ctl.pos[0],pos[1]-ctl.pos[1])<S(60)) this.hurt_player(w.dmg,ctl);
    }
  }
  fire(ctl,now){
    const ar=this.ar, g=this.g;
    const res=ar.shoot(now);
    if(res!=="ok") return;
    const w=ar.w, pos=ctl.shot_pos();
    g.sfx.play(w.snd);
    g.fx.shake=Math.max(g.fx.shake,3);
    g.fx.burst(pos[0],pos[1],[120,230,255],5,160,0.15,3,0);
    if(hypot(pos[0]-this.foe.pos[0],pos[1]-this.foe.pos[1])<S(90)){
      this.foe_hp-=w.dmg;
      g.fx.text(V.W*0.8,V.H*0.3,"-"+w.dmg,[255,80,80],0.8);
      g.sfx.play("hit");
    }
    if(this.foe_hp<=0){ g.sfx.play("win"); this.state="WIN"; }
  }
  draw(bg,now){
    const g=this.g;
    const c=bg.getContext('2d');
    const pctl = g.ptr()||{present:false};
    this.draw_cross(c,pctl,now);
    this.draw_menu_btn(c,pctl);
    text(c,"YOU "+Math.floor(this.hp)+"HP",S(14),S(34),0.7,[120,255,120],2);
    text(c,"ENEMY "+Math.floor(this.foe_hp)+"HP",V.W-S(14),S(34),0.7,[255,120,120],2,"r");
    c.fillStyle=[80,150,255];
    c.beginPath(); c.arc(this.foe.pos[0],this.foe.pos[1],S(20),0,Math.PI*2); c.fill();
    if(this.state==="WIN") text(c,"YOU WIN!",V.W/2,V.H/2,1.5,[0,255,0],3,"c");
    this.g.fx.draw(c);
    g.draw_cursor(c,pctl);
    return bg;
  }
}

/* ---------- 메인 게임 ---------- */
class Game{
  constructor(){
    this.now=performance.now()/1000;
    this.last=this.now;
    this.dt=0;
    this.save=new Save();
    this.modes={menu:new Menu(this), pve:null, pvp:null};
    this.mode=this.modes.menu;
    this.hand_main=new HandCtl();
    this.mouse=new MouseCtl();
    this.ctl=this.hand_main;
    this.mouse_mode=false;
    this.fx=new FX();
    this.keys={};
    this.take_map={};
    this.fullscreen=false;
    this.running=true;
    this.canvas=canvas;
    this.ctx=ctx;
    this.video=video;
    this.hands=null;
    this.cameraReady=false;
    this.animId=null;
    this.setupInput();
  }
  ptr(){ return this.ctl; }
  take(key){
    if(this.take_map[key]){ this.take_map[key]=false; return true; }
    return false;
  }
  go(key){
    if(key==="menu") this.mode=this.modes.menu;
    else if(key==="pve"){
      if(!this.modes.pve) this.modes.pve=new PvE(this);
      this.mode=this.modes.pve;
    } else if(key==="pvp"){
      if(!this.modes.pvp) this.modes.pvp=new PvP(this);
      this.mode=this.modes.pvp;
    } else if(key==="quit"){
      if(confirm("게임을 종료할까요?")){ this.running=false; cancelAnimationFrame(this.animId); }
    }
  }
  setupInput(){
    window.addEventListener("keydown",e=>{
      this.keys[e.code]=true;
      if(e.code==="Space"){ if(!this.take_map.space) this.take_map.space=true; }
      if(e.code==="KeyR"){ this.take_map.reload=true; }
      if(e.code==="Tab"){ this.take_map.cycle=true; }
      for(let i=1;i<=6;i++){ if(e.code==="Digit"+i) this.take_map["w"+i]=true; }
      if(e.code==="KeyH") this.take_map.medkit=true;
      if(e.code==="KeyA") this.take_map.armor=true;
      if(e.code==="KeyP"){ /* pause */ }
      if(e.code==="KeyM"){ sfx.on=!sfx.on; }
      if(e.code==="KeyF"){ this.toggleFullscreen(); }
      if(e.code==="KeyV"){ this.toggleInput(); }
      if(e.code==="Escape"){ this.go("menu"); }
    });
    window.addEventListener("keyup",e=>{ this.keys[e.code]=false; });
    const getCanvasPos=(e)=>{
      const rect=canvas.getBoundingClientRect();
      const scaleX=canvas.width/rect.width;
      const scaleY=canvas.height/rect.height;
      return [(e.clientX-rect.left)*scaleX,(e.clientY-rect.top)*scaleY];
    };
    canvas.addEventListener("mousedown",e=>{ const p=getCanvasPos(e); this.mouse.event("mousedown",p[0],p[1]); });
    canvas.addEventListener("mouseup",e=>{ const p=getCanvasPos(e); this.mouse.event("mouseup",p[0],p[1]); });
    canvas.addEventListener("mousemove",e=>{ const p=getCanvasPos(e); this.mouse.event("mousemove",p[0],p[1]); });
    canvas.addEventListener("contextmenu",e=>{ e.preventDefault(); const p=getCanvasPos(e); this.mouse.event("contextmenu",p[0],p[1]); });
    canvas.addEventListener("click",()=>{ ensureAudio(); });
    window.addEventListener("click",()=>{ ensureAudio(); });
  }
  toggleInput(){
    this.mouse_mode=!this.mouse_mode;
    this.ctl=this.mouse_mode?this.mouse:this.hand_main;
  }
  toggleFullscreen(){
    const el=document.body;
    if(!this.fullscreen){
      if(el.requestFullscreen) el.requestFullscreen();
      else if(el.webkitRequestFullscreen) el.webkitRequestFullscreen();
      this.fullscreen=true;
    } else {
      if(document.exitFullscreen) document.exitFullscreen();
      else if(document.webkitExitFullscreen) document.webkitExitFullscreen();
      this.fullscreen=false;
    }
  }
  async startCamera(){
    try{
      const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:"user", width:{ideal:1280}, height:{ideal:720}}});
      this.video.srcObject=stream;
      await this.video.play();
      this.cameraReady=true;
      document.getElementById('loading').style.display='none';
    }catch(e){
      console.error(e);
      document.getElementById('loading').textContent="카메라 권한이 필요합니다. 마우스 모드(V)로 플레이할 수 있습니다.";
      setTimeout(()=>document.getElementById('loading').style.display='none',2500);
    }
  }
  async initHands(){
    const Hands = window.Hands;
    if(!Hands) return;
    this.hands=new Hands({locateFile:(file)=>`https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`});
    this.hands.setOptions({maxNumHands:1, modelComplexity:1, minDetectionConfidence:0.5, minTrackingConfidence:0.5});
    this.hands.onResults(results=>this.onHandResults(results));
    this.cameraReady=true;
  }
  onHandResults(results){
    const lm = results.multiHandLandmarks&&results.multiHandLandmarks[0]?results.multiHandLandmarks[0]:null;
    // 미디어파이프는 좌우가 반전되어 오므로 x를 미러링
    const mirrored = lm?lm.map(p=>({x:1-p.x,y:p.y,z:p.z})):null;
    this.hand_main.update(mirrored,this.now,this.dt);
  }
  async cameraLoop(){
    if(!this.hands||!this.cameraReady) return;
    // 비디오 프레임을 핸즈에 전달
    this.hands.send({image:this.video});
  }
  drawHand(c,hand){
    if(!hand||!hand.pts) return;
    const pts=hand.pts;
    c.strokeStyle="rgb(0,255,255)";
    c.lineWidth=T(2);
    c.lineCap="round";
    for(const [a,b] of CONN){
      c.beginPath(); c.moveTo(pts[a][0],pts[a][1]); c.lineTo(pts[b][0],pts[b][1]); c.stroke();
    }
    for(const p of pts){
      c.fillStyle="rgb(255,255,255)";
      c.beginPath(); c.arc(p[0],p[1],Math.max(2,T(2)),0,Math.PI*2); c.fill();
    }
    if(hand.trigger){
      c.fillStyle="rgb(255,80,80)";
      c.beginPath(); c.arc(hand.pos[0],hand.pos[1],S(8),0,Math.PI*2); c.fill();
    }
    if(hand.palm_prog>0){
      c.strokeStyle="rgb(0,255,0)";
      c.lineWidth=T(3);
      c.beginPath(); c.arc(hand.pos[0],hand.pos[1],hand.size+S(14),-Math.PI/2,-Math.PI/2+2*Math.PI*hand.palm_prog); c.stroke();
    }
    text(c,hand.dbg,S(14),V.H-S(34),0.45,[200,230,255],1);
  }
  draw_cursor(c,ctl){
    if(!this.mouse_mode&&!ctl.present) return;
    if(this.mouse_mode){
      c.strokeStyle="rgb(0,255,255)";
      c.lineWidth=T(2);
      c.beginPath(); c.arc(ctl.pos[0],ctl.pos[1],S(10),0,Math.PI*2); c.stroke();
    }
  }
  loop(){
    if(!this.running) return;
    const now=performance.now()/1000;
    this.dt=now-this.now;
    this.now=now;
    if(this.dt>0.1) this.dt=0.1;
    // 카메라 루프
    if(this.cameraReady&&this.video.readyState>=2) this.cameraLoop();
    // 배경: 비디오 프레임
    this.ctx.save();
    this.ctx.setTransform(1,0,0,1,0,0);
    this.ctx.clearRect(0,0,V.W,V.H);
    if(this.cameraReady&&this.video.readyState>=2){
      this.ctx.save();
      this.ctx.translate(V.W,0);
      this.ctx.scale(-1,1);
      this.ctx.drawImage(this.video,0,0,V.W,V.H);
      this.ctx.restore();
    } else {
      this.ctx.fillStyle="#0b0c10";
      this.ctx.fillRect(0,0,V.W,V.H);
    }
    // 모드 업데이트/그리기
    this.mode.update(this.dt,this.now);
    this.mode.draw(this.canvas,this.now);
    this.ctx.restore();
    this.fx.update(this.dt);
    this.animId=requestAnimationFrame(()=>this.loop());
  }
  start(){
    sfx.init();
    ensureAudio();
    this.startCamera();
    this.initHands();
    this.loop();
  }
}

const game=new Game();
game.start();
