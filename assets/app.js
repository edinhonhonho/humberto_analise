(function(){
const B=document.body,SHELL=!!B.dataset.shell,ROOT=B.dataset.root||'';
const LOCAL=/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
const mk=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e};
const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const nf=(x,d)=>x.toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const norm=t=>String(t).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const app=document.getElementById('app');
let offs=[],TIPS={},BM={},D=null,cur=null,dr=null,lastFocus=null,names=[];
function on(t,ev,fn,o){t.addEventListener(ev,fn,o);offs.push(()=>t.removeEventListener(ev,fn,o))}

/* ---------- dica flutuante ---------- */
const tip=mk('div');tip.id='tip';tip.hidden=true;B.appendChild(tip);
function place(x,y){const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+16,t=y+16;
 if(l+w>innerWidth-8)l=x-w-16;if(t+h>innerHeight-8)t=y-h-16;tip.style.left=Math.max(8,l)+'px';tip.style.top=Math.max(8,t)+'px'}
function show(x,y,title,rows){tip.replaceChildren();const s=mk('strong',null,title);tip.appendChild(s);
 (rows||[]).forEach(([k,v])=>{const d=mk('div','r'+(String(v).length>34?' long':''));d.append(mk('span',null,k),mk('b',null,v));tip.appendChild(d)});
 tip.hidden=false;place(x,y)}
function tipdata(el){const t=el.closest&&el.closest('[data-tip]');if(t)return JSON.parse(t.getAttribute('data-tip'));
 const u=el.closest&&el.closest('use.p[data-id]');if(!u)return null;const c=u.closest('.mapcard');
 const T=c&&TIPS[c.id];if(!T)return null;const id=u.getAttribute('data-id'),e=T.tp[id];if(!e)return null;
 if(!T.tl)return e;const mm=D&&D.mun&&D.mun[id];return [e[0]||(mm?mm.n:''),e[1].map(([i,v])=>[T.tl[i],v])]}
function onmove(e){let d=null;try{d=tipdata(e.target)}catch(_){}
 if(!d){if(!e.target.closest||!e.target.closest('.pareto .cap'))tip.hidden=true;return}
 show(e.clientX,e.clientY,d[0],d[1])}
document.addEventListener('pointermove',onmove);document.addEventListener('pointerdown',onmove);
addEventListener('scroll',()=>{tip.hidden=true},{passive:true});

/* ---------- renderizadores de blocos (tabelas e mapas vêm como dados) ---------- */
function tabHtml(b){
 const mx=b.c.map((c,j)=>c[1]==='ib'?(Math.max(0,...b.r.map(r=>r[j]==null?0:r[j]))||1):0);
 const dec={i:0,d1:1,d2:2,ib:0};
 const th=b.c.map(([h,t])=>`<th class="${t==='t'||t==='tw'?'t':''}">${esc(h)}</th>`).join('');
 const tr=b.r.map(r=>'<tr>'+b.c.map(([h,t],j)=>{const v=r[j];
  if(t==='t'||t==='tw')return `<td class="t${t==='tw'?' wrap':''}">${v===null||v===''?'–':esc(v)}</td>`;
  if(t==='ib')return `<td class="num ib"${v===null?'':` data-v="${v}"`}><i style="width:${v===null?'0.0':(100*v/mx[j]).toFixed(1)}%"></i><span>${v===null?'–':nf(v,0)}</span></td>`;
  return `<td class="num"${v===null?'':` data-v="${v}"`}>${v===null?'–':nf(v,dec[t])}</td>`}).join('')+'</tr>').join('');
 return (b.s?`<input class="search" type="search" placeholder="Buscar município" data-for="${b.id}" aria-label="Buscar">`:'')+
  `<div class="tw"><table class="sortable" id="${b.id}"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`}
const IC=(d)=>`<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const ZOOM=`<div class="zoomctl" role="group" aria-label="Zoom do mapa"><button type="button" data-z="in" aria-label="Aproximar" title="Aproximar">${IC('<path d="M12 5v14M5 12h14"/>')}</button><button type="button" data-z="out" aria-label="Afastar" title="Afastar">${IC('<path d="M5 12h14"/>')}</button><button type="button" data-z="reset" aria-label="Centralizar o mapa" title="Centralizar">${IC('<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>')}</button></div>`;
function mapHtml(b){
 const paths=b.i.map((id,j)=>`<use href="#g${id}" class="p k-${b.k[j].split(' ')[0]}" data-id="${id}" data-k="${b.k[j]}"/>`).join('');
 const seg=b.m.map((m,i)=>`<button type="button" role="radio" aria-checked="${i===0}" data-m="${i}">${esc(m.label)}</button>`).join('');
 return `<div class="mapcard" id="${b.id}"><div class="mapmain">${ZOOM}<svg class="map" viewBox="${b.vb}" role="img" aria-label="${esc(b.aria)}"><g class="polys">${paths}</g></svg></div>`+
  `<aside class="mapside"><div class="seg" role="radiogroup" aria-label="Métrica do mapa">${seg}</div><p class="note mnote"></p><ul class="legend"></ul></aside></div>`}


/* zoom e deslocamento dos mapas */
function zoomMapa(card){
 const svg=card.querySelector('svg.map');if(!svg)return;
 const mm=card.querySelector('.mapmain');
 if(!mm.querySelector('.zoomctl'))mm.insertAdjacentHTML('afterbegin',ZOOM);
 const vb0=svg.getAttribute('viewBox').split(/[ ,]+/).map(Number);let v=vb0.slice();
 const apply=()=>{svg.setAttribute('viewBox',v.map(x=>+x.toFixed(2)).join(' '));card.classList.toggle('zoomed',v[2]<vb0[2]-.01)};
 const clamp=()=>{v[0]=Math.min(Math.max(v[0],vb0[0]),vb0[0]+vb0[2]-v[2]);v[1]=Math.min(Math.max(v[1],vb0[1]),vb0[1]+vb0[3]-v[3])};
 function pt(cx,cy){const r=svg.getBoundingClientRect(),s=Math.min(r.width/v[2],r.height/v[3]),ox=(r.width-v[2]*s)/2,oy=(r.height-v[3]*s)/2;
  return {x:v[0]+(cx-r.left-ox)/s,y:v[1]+(cy-r.top-oy)/s,s}}
 function zoom(f,cx,cy){let nw=Math.min(vb0[2],Math.max(vb0[2]/14,v[2]/f));const k=nw/v[2];
  if(cx==null){cx=v[0]+v[2]/2;cy=v[1]+v[3]/2}
  v=[cx-(cx-v[0])*k,cy-(cy-v[1])*k,nw,v[3]*k];clamp();apply()}
 card.querySelectorAll('.zoomctl button').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();const z=b.dataset.z;
  if(z==='in')zoom(1.6);else if(z==='out')zoom(1/1.6);else{v=vb0.slice();apply()}}));
 svg.addEventListener('wheel',e=>{if(!(e.ctrlKey||e.metaKey))return;e.preventDefault();const p=pt(e.clientX,e.clientY);zoom(Math.exp(-e.deltaY*.012),p.x,p.y)},{passive:false});
 const ptrs=new Map();let drag=false,moved=false,last=null,d0=0;
 svg.addEventListener('pointerdown',e=>{if(e.pointerType==='mouse'&&e.button!==0)return;ptrs.set(e.pointerId,[e.clientX,e.clientY]);moved=false;
  if(ptrs.size===2){const [a,b]=[...ptrs.values()];d0=Math.hypot(a[0]-b[0],a[1]-b[1])}last=[e.clientX,e.clientY]});
 svg.addEventListener('pointermove',e=>{if(!ptrs.has(e.pointerId))return;
  if(ptrs.size===2){const o=[...ptrs.entries()].find(([id])=>id!==e.pointerId)[1],a=[e.clientX,e.clientY],d=Math.hypot(a[0]-o[0],a[1]-o[1]);
   ptrs.set(e.pointerId,a);if(d0&&d>0){const p=pt((a[0]+o[0])/2,(a[1]+o[1])/2);zoom(d/d0,p.x,p.y)}d0=d;moved=true;return}
  ptrs.set(e.pointerId,[e.clientX,e.clientY]);if(!card.classList.contains('zoomed')||!last)return;
  const dx=e.clientX-last[0],dy=e.clientY-last[1];
  if(!moved&&Math.hypot(dx,dy)<5)return;
  if(!moved){moved=true;try{svg.setPointerCapture(e.pointerId)}catch(_){}tip.hidden=true}
  const s=pt(0,0).s||1;v[0]-=dx/s;v[1]-=dy/s;clamp();apply();last=[e.clientX,e.clientY]});
 const fim=e=>{ptrs.delete(e.pointerId);if(ptrs.size<2)d0=0;if(ptrs.size===0)last=null;else{const r=[...ptrs.values()][0];last=r}};
 svg.addEventListener('pointerup',fim);svg.addEventListener('pointercancel',fim);
 card.addEventListener('click',e=>{if(moved){e.stopPropagation();e.preventDefault();moved=false}},true)}

/* ---------- comportamento de cada página (refeito a cada troca) ---------- */
function iniciar(){
 app.querySelectorAll('.mapcard').forEach(card=>{
  const b=BM[card.id];let cfg;if(b)cfg={metrics:b.m};else{try{cfg=JSON.parse(card.querySelector('.mcfg').textContent)}catch(_){return}}
  const paths=[...card.querySelectorAll('.map .p')],legend=card.querySelector('.legend'),note=card.querySelector('.mnote'),btns=[...card.querySelectorAll('.seg button')];
  if(btns.length<2)card.querySelector('.seg').hidden=true;
  function set(i){btns.forEach((x,j)=>x.setAttribute('aria-checked',j===i));
   paths.forEach(p=>p.setAttribute('class','p k-'+p.dataset.k.split(' ')[i]));
   legend.replaceChildren(...cfg.metrics[i].legend.map(([c,l])=>{const li=mk('li'),sw=mk('i','sw k-'+c);li.append(sw,document.createTextNode(l));return li}));note.textContent=cfg.metrics[i].note}
  btns.forEach((x,i)=>x.addEventListener('click',()=>set(i)));set(0);
  const chk=card.querySelector('.showpts');if(chk)chk.addEventListener('change',()=>{card.querySelector('.pts').hidden=!chk.checked});
  zoomMapa(card);
  paths.forEach(p=>p.addEventListener('pointerenter',()=>{if(p.nextElementSibling&&!p.classList.contains('sel'))p.parentNode.appendChild(p)}))});
 app.querySelectorAll('.pareto').forEach(w=>{
  const d=JSON.parse(w.querySelector('.pdat').textContent),svg=w.querySelector('svg'),xh=svg.querySelector('.xh'),
   cap=svg.querySelector('.cap'),xl=xh.querySelector('.xl'),dot=xh.querySelector('circle');
  const f=v=>v.toLocaleString('pt-BR',{maximumFractionDigits:1});
  cap.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*d.w;
   let k=Math.round((x-d.ml)/d.pw*(d.xmax-1))+1;k=Math.max(1,Math.min(d.s.length,k));const row=d.s[k-1];
   const px=d.ml+d.pw*(k-1)/Math.max(d.xmax-1,1),py=d.mt+d.ph*(1-row[3]/100);
   xl.setAttribute('x1',px);xl.setAttribute('x2',px);dot.setAttribute('cx',px);dot.setAttribute('cy',py);xh.hidden=false;
   show(e.clientX,e.clientY,'Os '+k+' municípios mais votados',[['Somam',f(row[3])+'% dos votos'],['O '+k+'º é',row[1]],['Votos nele',row[2].toLocaleString('pt-BR')]])});
  cap.addEventListener('pointerleave',()=>{xh.hidden=true;tip.hidden=true})});
 (function(){const hs=[...app.querySelectorAll('h2[id]')],bar=document.getElementById('secbar');
  if(!bar)return;bar.hidden=true;if(!hs.length)return;const bn=bar.querySelector('.n'),bt=bar.querySelector('.t');
  let c0=null;function upd(){let act=null;hs.forEach(h=>{if(h.getBoundingClientRect().top<=120)act=h});
   if(act===c0)return;c0=act;if(!act){bar.hidden=true;return}
   const n=act.querySelector('.n');bn.textContent=n?n.textContent:'';bt.textContent=act.textContent.replace(n?n.textContent:'','').trim();bar.hidden=false}
  on(window,'scroll',upd,{passive:true});on(window,'resize',upd);upd()})();
 app.querySelectorAll('.cscroll').forEach(w=>{
  const bar=w.querySelector('.ctabs'),L=w.querySelector('.arr.l'),R=w.querySelector('.arr.r');
  function upd(){const max=bar.scrollWidth-bar.clientWidth,x=bar.scrollLeft;L.hidden=x<4;R.hidden=x>max-4;
   bar.style.setProperty('--ml',x<4?'0px':'56px');bar.style.setProperty('--mr',x>max-4?'0px':'56px')}
  bar.addEventListener('scroll',upd,{passive:true});on(window,'resize',upd);
  L.addEventListener('click',()=>bar.scrollBy({left:-bar.clientWidth*.7,behavior:'smooth'}));
  R.addEventListener('click',()=>bar.scrollBy({left:bar.clientWidth*.7,behavior:'smooth'}));
  let down=false,sx=0,sl=0,moved=false;
  bar.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse')return;down=true;moved=false;sx=e.clientX;sl=bar.scrollLeft});
  on(window,'pointermove',e=>{if(!down)return;const dx=e.clientX-sx;if(Math.abs(dx)>5){moved=true;bar.classList.add('drag')}if(moved)bar.scrollLeft=sl-dx});
  on(window,'pointerup',()=>{if(!down)return;down=false;bar.classList.remove('drag');
   if(moved)bar.addEventListener('click',ev=>ev.stopPropagation(),{capture:true,once:true})});
  upd();setTimeout(upd,60)});
 app.querySelectorAll('.tabset').forEach(ts=>{
  const bar=ts.querySelector(':scope > .tablist, :scope > .cscroll .ctabs'),btns=[...bar.querySelectorAll('button')],panes=[...ts.querySelectorAll(':scope > .pane')];
  function sel(i){btns.forEach((b,j)=>b.setAttribute('aria-selected',j===i));panes.forEach((p,j)=>{p.hidden=j!==i});
   if(bar.classList.contains('ctabs')){const b=btns[i];bar.scrollTo({left:b.offsetLeft-(bar.clientWidth-b.offsetWidth)/2,behavior:'smooth'})}}
  btns.forEach((b,i)=>b.addEventListener('click',()=>sel(i)));sel(0)});
 app.querySelectorAll('table.sortable').forEach(t=>{
  t.querySelectorAll('th').forEach((th,i)=>th.addEventListener('click',()=>{
   const tb=t.tBodies[0],rows=[...tb.rows],asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
   const val=r=>{const c=r.cells[i];return c.dataset.v!==undefined?parseFloat(c.dataset.v):c.textContent};
   rows.sort((a,b)=>{const x=val(a),y=val(b);if(typeof x==='number'&&typeof y==='number'){if(isNaN(x))return 1;if(isNaN(y))return -1;return asc?x-y:y-x}
    return asc?String(x).localeCompare(String(y),'pt-BR'):String(y).localeCompare(String(x),'pt-BR')});
   rows.forEach(r=>tb.appendChild(r))}))});
 app.querySelectorAll('input.search').forEach(inp=>{const t=document.getElementById(inp.dataset.for);
  inp.addEventListener('input',()=>{const q=inp.value.toLowerCase();[...t.tBodies[0].rows].forEach(r=>{r.hidden=q&&!r.textContent.toLowerCase().includes(q)})})});
 busca()}

/* ---------- busca de município, seleção nos mapas e painel de detalhes ---------- */
const FMT={i:v=>nf(Math.round(v),0),d1:v=>nf(v,1),d2:v=>nf(v,2),p1:v=>nf(v,1)+'%',p2:v=>nf(v,2)+'%',km:v=>nf(v,0)+' km',
 pos:v=>Math.round(v)+'º',s:v=>(v>0?'+':v<0?'−':'')+nf(Math.abs(Math.round(v)),0),t:v=>String(v)};
function drawer(){if(dr&&dr.isConnected)return dr;dr=mk('aside','mdrawer');dr.id='mdrawer';dr.hidden=true;dr.setAttribute('role','dialog');
 dr.setAttribute('aria-label','Detalhes do município');B.appendChild(dr);return dr}
function mark(cd){document.querySelectorAll('.map .p.sel').forEach(p=>p.classList.remove('sel'));
 if(cd==null)return;document.querySelectorAll('.map .p[data-id="'+cd+'"]').forEach(p=>{p.classList.add('sel');p.parentNode.appendChild(p)})}
function url(cd){try{const u=new URL(location.href);if(cd==null)u.searchParams.delete('m');else u.searchParams.set('m',cd);history.replaceState(null,'',u)}catch(_){}}
function fechar(urlToo){cur=null;mark(null);if(urlToo!==false)url(null);if(dr)dr.hidden=true;if(lastFocus&&lastFocus.focus)try{lastFocus.focus({preventScroll:true})}catch(_){}}
function abrir(cd){if(!D||!D.mun)return;const m=D.mun[cd];if(!m)return;cur=cd;mark(cd);url(cd);const d=drawer();d.replaceChildren();
 const h=mk('header');const x=mk('button','x','×');x.type='button';x.setAttribute('aria-label','Fechar');x.addEventListener('click',()=>fechar());h.append(mk('h3',null,m.n),x);d.appendChild(h);
 const dl=mk('dl');D.fields.forEach(([lab,key,f])=>{const v=m[key];if(v===null||v===undefined||v==='')return;dl.append(mk('dt',null,lab),mk('dd',null,(FMT[f]||FMT.t)(v)))});d.appendChild(dl);
 const top=(D.top||{})[cd];if(top&&top.length){d.appendChild(mk('h4',null,'Mais votados no município'));
  const ol=mk('ol','topl');top.forEach(r=>{const li=mk('li');const a=mk('span','nm',r[1]+' ');a.appendChild(mk('i',null,r[2]));
   li.append(a,mk('b',null,nf(r[3],0)+' · '+nf(r[4],1)+'%'));if(r[5])li.classList.add('foco');ol.appendChild(li)});d.appendChild(ol)}
 d.hidden=false;d.scrollTop=0}
document.addEventListener('click',e=>{const p=e.target.closest&&e.target.closest('.map .p[data-id]');if(p&&D){lastFocus=null;abrir(p.getAttribute('data-id'))}});
addEventListener('keydown',e=>{if(e.key==='Escape'&&cur!=null)fechar()});
function busca(){
 const inp=document.getElementById('msq'),list=document.getElementById('msl');if(!inp||!list||!D||!D.mun)return;
 let items=[],act=-1;
 const hide=()=>{list.hidden=true;inp.setAttribute('aria-expanded','false');act=-1};
 function paint(){[...list.children].forEach((li,i)=>li.setAttribute('aria-selected',i===act))}
 function pick(i){const it=items[i];if(!it)return;hide();inp.value=it.n;lastFocus=inp;abrir(it.cd);
  const c=document.getElementById('mapa-estado');if(c){const r=c.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)c.scrollIntoView({block:'center',behavior:'smooth'})}}
 function upd(){const q=norm(inp.value.trim());list.replaceChildren();if(!q){hide();return}
  const a=names.filter(n=>n.k.startsWith(q)),b=names.filter(n=>!n.k.startsWith(q)&&n.k.includes(q));items=a.concat(b).slice(0,8);
  if(!items.length)list.appendChild(mk('li','vazio','Nenhum município com esse nome'));
  items.forEach((it,i)=>{const li=mk('li',null,it.n);li.setAttribute('role','option');li.addEventListener('pointerdown',ev=>{ev.preventDefault();pick(i)});list.appendChild(li)});
  act=items.length?0:-1;paint();list.hidden=false;inp.setAttribute('aria-expanded','true')}
 inp.addEventListener('input',upd);inp.addEventListener('focus',()=>{if(inp.value)upd()});inp.addEventListener('blur',()=>setTimeout(hide,120));
 inp.addEventListener('keydown',e=>{if(list.hidden&&e.key==='ArrowDown'){upd();return}
  if(e.key==='ArrowDown'){e.preventDefault();act=Math.min(items.length-1,act+1);paint()}
  else if(e.key==='ArrowUp'){e.preventDefault();act=Math.max(0,act-1);paint()}
  else if(e.key==='Enter'){e.preventDefault();if(act>=0)pick(act)}
  else if(e.key==='Escape'){if(!list.hidden){e.stopPropagation();hide()}}})}
const abreGuia=()=>{const d=document.getElementById('guia');if(d&&d.tagName==='DETAILS')d.open=true};
document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('a[href="#guia"]'))abreGuia()});

/* ---------- desenho da página ---------- */
function desenhar(P,geoSvg,o){
 const keep=o&&o.manter?cur:null;
 offs.forEach(f=>f());offs=[];if(cur!=null)fechar(false);TIPS={};BM={};
 D=P.d||null;names=D&&D.mun?Object.entries(D.mun).map(([cd,m])=>({cd,n:m.n,k:norm(m.n)})).sort((a,b)=>a.n.localeCompare(b.n,'pt-BR')):[];
 const S=window.__S||{};
 app.innerHTML=(geoSvg||'')+P.h.replace(/<!--S:(\w+)-->/g,(m,k)=>S[k]||'');
 (P.b||[]).forEach((b,i)=>{const el=app.querySelector('.blk[data-b="'+i+'"]');if(!el)return;
  if(b.t==='map'){BM[b.id]=b;TIPS[b.id]=b;const t=document.createElement('template');t.innerHTML=mapHtml(b);el.replaceWith(t.content)}
  else{const t=document.createElement('template');t.innerHTML=tabHtml(b);el.replaceWith(t.content)}});
 document.title=SHELL?'Eleições':P.t;
 {const f=document.getElementById('foot');if(f)app.appendChild(f.content.cloneNode(true))}
 iniciar();
 if(keep!=null&&D&&D.mun&&D.mun[keep])abrir(keep);
 if(location.hash==='#guia')abreGuia();
 const m0=new URLSearchParams(location.search).get('m');
 if(m0&&D&&D.mun&&D.mun[m0]){abrir(m0);const c=document.getElementById('mapa-estado');if(c)setTimeout(()=>c.scrollIntoView({block:'center'}),50)}}

/* ---------- carga de dados e roteamento (página única) ---------- */
const cacheP={},ordem=[];
const bust=LOCAL?'?'+Date.now():'';
let barra=null,seq=0;
function indo(){B.classList.add('indo');if(!barra){barra=mk('div');barra.id='progresso';B.appendChild(barra)}barra.classList.remove('on');void barra.offsetWidth;barra.classList.add('on')}
function fim(){B.classList.remove('indo');if(barra)barra.classList.remove('on')}

/* ---------- motor de cálculo (Web Worker): lê os dados da UF e calcula a análise na hora ---------- */
const SLUG={'presidente':1,'governador':3,'senador':5,'deputado-federal':6,'deputado-estadual':7,'deputado-distrital':8};
let W=null,wid=0,espera={};
function worker(){if(W)return W;
 W=new Worker(ROOT+'assets/motor.js'+bust);
 W.onmessage=e=>{const m=e.data,f=espera[m.id];if(f)f(m)};
 W.onerror=ev=>{const fs=Object.values(espera);espera={};W=null;fs.forEach(f=>f({tipo:'erro',msg:(ev&&ev.message)||'falha no motor'}))};
 return W}
function cancelar(){if(W&&Object.keys(espera).length){W.terminate();W=null;espera={}}}
function calcular(key,aoEtapa){return new Promise((ok,err)=>{
 const [ano,uf,slug,num]=key.split('/'),cargo=SLUG[slug];if(!cargo||!window.Worker){err(new Error('sem motor'));return}
 const id=++wid;
 espera[id]=m=>{if(m.tipo==='erro'){delete espera[id];err(new Error(m.msg));return}
  aoEtapa(m.P,m.etapa);if(m.final){delete espera[id];ok(m.P)}};
 worker().postMessage({tipo:'calcular',id,base:new URL(ROOT+'data/br',location.href).href,ano:+ano,uf:uf.toUpperCase(),cargo,turno:1,numero:+num})})}

const partidoDe=n=>{n=Math.trunc(Number(n));if(n<100)return n;if(n<1000)return Math.floor(n/10);if(n<10000)return Math.floor(n/100);return Math.floor(n/1000)};
let manP=null;
async function bloqueado(key){const num=key.split('/')[3];
 if(!manP){manP=window.__MAN?Promise.resolve(window.__MAN):fetch(ROOT+'data/manifest.json').then(r=>r.json()).catch(()=>({}))}
 const m=await manP;return !!m.espectro&&m.espectro[String(partidoDe(num))]==='direita'}
const App=window.App={atual:null,
 pre(key){},
 async ir(key,o){o=o||{};const my=++seq;cancelar();indo();let primeira=true,P=cacheP[key];
  if(await bloqueado(key)){if(my!==seq)return;document.title='Análise indisponível';app.innerHTML='<p class="carregando">A análise de candidatos de partidos de direita não está disponível neste site. Escolha outro candidato em <b>Trocar candidato</b>.</p>';return}
  const publicar=(Pn,et)=>{if(my!==seq)return;
   if(primeira){
    if(o.push!==false){const u=new URL(location.href);u.search='?c='+key;u.hash='';
     (o.replace?history.replaceState:history.pushState).call(history,null,'',u)}
    App.atual=key;desenhar(Pn,Pn.gs||'');if(!o.semScroll)scrollTo(0,0);primeira=false;
    if(window.va)try{va('pageview',{route:null,path:'/'+key})}catch(_){}
    document.dispatchEvent(new CustomEvent('app:page',{detail:Pn.m||null}))}
   else{const y=scrollY;desenhar(Pn,Pn.gs||'',{manter:true});scrollTo(0,y)}};
  try{
   if(P)publicar(P,3);
   else{P=await calcular(key,publicar);if(my!==seq)return;cacheP[key]=P;ordem.push(key);while(ordem.length>8)delete cacheP[ordem.shift()]}
   fim()}
  catch(er){if(my!==seq)return;fim();
   if(primeira)app.innerHTML='<p class="carregando">'+(/sem votos/.test(er.message)?'Esse candidato não tem votos neste cargo e estado.':'Não consegui carregar essa análise. Tente de novo ou escolha outro candidato em <b>Trocar candidato</b>.')+'</p>'}}};
if(SHELL){
 const k0=new URLSearchParams(location.search).get('c');let pad=null;try{pad=JSON.parse(B.dataset.padrao)}catch(_){}
 const k=k0||pad;
 if(k)App.ir(k,{push:false,semScroll:true});else app.innerHTML='<p class="carregando">Nenhuma análise publicada ainda.</p>';
 addEventListener('popstate',()=>{const c=new URLSearchParams(location.search).get('c')||pad;if(c&&c!==App.atual)App.ir(c,{push:false,semScroll:true})})
}else if(window.__P0){
 const P=window.__P0;desenhar(P,P.gs||'')}
})();
