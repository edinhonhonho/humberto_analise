(function(){
const tip=document.createElement('div');tip.id='tip';tip.hidden=true;document.body.appendChild(tip);
function place(x,y){const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+16,t=y+16;
 if(l+w>innerWidth-8)l=x-w-16;if(t+h>innerHeight-8)t=y-h-16;tip.style.left=Math.max(8,l)+'px';tip.style.top=Math.max(8,t)+'px'}
function show(x,y,title,rows){tip.replaceChildren();const s=document.createElement('strong');s.textContent=title;tip.appendChild(s);
 (rows||[]).forEach(([k,v])=>{const d=document.createElement('div');d.className='r'+(String(v).length>34?' long':'');
  const a=document.createElement('span');a.textContent=k;const b=document.createElement('b');b.textContent=v;d.append(a,b);tip.appendChild(d)});
 tip.hidden=false;place(x,y)}
function onmove(e){const t=e.target.closest&&e.target.closest('[data-tip]');
 if(!t){if(!e.target.closest||!e.target.closest('.pareto .cap'))tip.hidden=true;return}
 try{const [title,rows]=JSON.parse(t.getAttribute('data-tip'));show(e.clientX,e.clientY,title,rows)}catch(_){tip.hidden=true}}
document.addEventListener('pointermove',onmove);document.addEventListener('pointerdown',onmove);
addEventListener('scroll',()=>{tip.hidden=true},{passive:true});

document.querySelectorAll('.mapcard').forEach(card=>{
 const cfg=JSON.parse(card.querySelector('.mcfg').textContent),paths=[...card.querySelectorAll('.map .p')];
 const legend=card.querySelector('.legend'),note=card.querySelector('.mnote'),btns=[...card.querySelectorAll('.seg button')];
 if(btns.length<2)card.querySelector('.seg').hidden=true;
 function set(i){btns.forEach((b,j)=>b.setAttribute('aria-checked',j===i));
  paths.forEach(p=>p.setAttribute('class','p k-'+p.dataset.k.split(' ')[i]));
  legend.replaceChildren(...cfg.metrics[i].legend.map(([c,l])=>{const li=document.createElement('li'),sw=document.createElement('i');
   sw.className='sw k-'+c;li.append(sw,document.createTextNode(l));return li}));note.textContent=cfg.metrics[i].note}
 btns.forEach((b,i)=>b.addEventListener('click',()=>set(i)));set(0);
 const chk=card.querySelector('.showpts');if(chk)chk.addEventListener('change',()=>{card.querySelector('.pts').hidden=!chk.checked});
 paths.forEach(p=>p.addEventListener('pointerenter',()=>p.parentNode.appendChild(p)));
});

document.querySelectorAll('.pareto').forEach(w=>{
 const d=JSON.parse(w.querySelector('.pdat').textContent),svg=w.querySelector('svg'),xh=svg.querySelector('.xh'),
  cap=svg.querySelector('.cap'),xl=xh.querySelector('.xl'),dot=xh.querySelector('circle');
 const f=v=>v.toLocaleString('pt-BR',{maximumFractionDigits:1});
 cap.addEventListener('pointermove',e=>{const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*d.w;
  let k=Math.round((x-d.ml)/d.pw*(d.xmax-1))+1;k=Math.max(1,Math.min(d.s.length,k));const row=d.s[k-1];
  const px=d.ml+d.pw*(k-1)/Math.max(d.xmax-1,1),py=d.mt+d.ph*(1-row[3]/100);
  xl.setAttribute('x1',px);xl.setAttribute('x2',px);dot.setAttribute('cx',px);dot.setAttribute('cy',py);xh.hidden=false;
  show(e.clientX,e.clientY,'Os '+k+' municípios mais votados',[['Somam',f(row[3])+'% dos votos'],['O '+k+'º é',row[1]],['Votos nele',row[2].toLocaleString('pt-BR')]])});
 cap.addEventListener('pointerleave',()=>{xh.hidden=true;tip.hidden=true});
});

(function(){const b=document.getElementById('idxb'),p=document.getElementById('idxp');if(!b||!p)return;
 const set=o=>{p.hidden=!o;b.setAttribute('aria-expanded',o)};
 b.addEventListener('click',e=>{e.stopPropagation();set(p.hidden)});
 p.addEventListener('click',e=>{if(e.target.closest('a'))set(false)});
 document.addEventListener('click',e=>{if(!p.hidden&&!p.contains(e.target))set(false)});
 addEventListener('keydown',e=>{if(e.key==='Escape')set(false)})})();
(function(){const hs=[...document.querySelectorAll('main h2[id]')],bar=document.getElementById('secbar');
 if(!bar||!hs.length)return;const bn=bar.querySelector('.n'),bt=bar.querySelector('.t'),links={};
 document.querySelectorAll('.idxp a[href^="#"]').forEach(a=>{links[a.getAttribute('href').slice(1)]=a});
 let cur=null;function upd(){const lim=innerHeight>0?120:120;let act=null;
  hs.forEach(h=>{if(h.getBoundingClientRect().top<=lim)act=h});
  if(act===cur)return;cur=act;Object.values(links).forEach(a=>a.classList.remove('on'));
  if(!act){bar.hidden=true;return}
  const n=act.querySelector('.n');bn.textContent=n?n.textContent:'';bt.textContent=act.textContent.replace(n?n.textContent:'','').trim();
  bar.hidden=false;if(links[act.id])links[act.id].classList.add('on')}
 addEventListener('scroll',upd,{passive:true});addEventListener('resize',upd);upd()})();
document.querySelectorAll('.cscroll').forEach(w=>{
 const bar=w.querySelector('.ctabs'),L=w.querySelector('.arr.l'),R=w.querySelector('.arr.r');
 function upd(){const max=bar.scrollWidth-bar.clientWidth,x=bar.scrollLeft;L.hidden=x<4;R.hidden=x>max-4;
  bar.style.setProperty('--ml',x<4?'0px':'56px');bar.style.setProperty('--mr',x>max-4?'0px':'56px')}
 bar.addEventListener('scroll',upd,{passive:true});addEventListener('resize',upd);
 L.addEventListener('click',()=>bar.scrollBy({left:-bar.clientWidth*.7,behavior:'smooth'}));
 R.addEventListener('click',()=>bar.scrollBy({left:bar.clientWidth*.7,behavior:'smooth'}));
 let down=false,sx=0,sl=0,moved=false;
 bar.addEventListener('pointerdown',e=>{if(e.pointerType!=='mouse')return;down=true;moved=false;sx=e.clientX;sl=bar.scrollLeft});
 addEventListener('pointermove',e=>{if(!down)return;const dx=e.clientX-sx;if(Math.abs(dx)>5){moved=true;bar.classList.add('drag')}
  if(moved)bar.scrollLeft=sl-dx});
 addEventListener('pointerup',()=>{if(!down)return;down=false;bar.classList.remove('drag');
  if(moved)bar.addEventListener('click',ev=>ev.stopPropagation(),{capture:true,once:true})});
 upd();setTimeout(upd,60)});
document.querySelectorAll('.tabset').forEach(ts=>{
 const bar=ts.querySelector(':scope > .tablist, :scope > .cscroll .ctabs'),btns=[...bar.querySelectorAll('button')],
  panes=[...ts.querySelectorAll(':scope > .pane')];
 function sel(i){btns.forEach((b,j)=>b.setAttribute('aria-selected',j===i));panes.forEach((p,j)=>{p.hidden=j!==i});
  if(bar.classList.contains('ctabs')){const b=btns[i];bar.scrollTo({left:b.offsetLeft-(bar.clientWidth-b.offsetWidth)/2,behavior:'smooth'})}}
 btns.forEach((b,i)=>b.addEventListener('click',()=>sel(i)));sel(0)});
document.querySelectorAll('table.sortable').forEach(t=>{
 t.querySelectorAll('th').forEach((th,i)=>th.addEventListener('click',()=>{
  const tb=t.tBodies[0],rows=[...tb.rows],asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
  const val=r=>{const c=r.cells[i];return c.dataset.v!==undefined?parseFloat(c.dataset.v):c.textContent};
  rows.sort((a,b)=>{const x=val(a),y=val(b);if(typeof x==='number'&&typeof y==='number'){if(isNaN(x))return 1;if(isNaN(y))return -1;return asc?x-y:y-x}
   return asc?String(x).localeCompare(String(y),'pt-BR'):String(y).localeCompare(String(x),'pt-BR')});
  rows.forEach(r=>tb.appendChild(r))}))});
document.querySelectorAll('input.search').forEach(inp=>{const t=document.getElementById(inp.dataset.for);
 inp.addEventListener('input',()=>{const q=inp.value.toLowerCase();[...t.tBodies[0].rows].forEach(r=>{r.hidden=q&&!r.textContent.toLowerCase().includes(q)})})});
})();

/* ---- busca de município, seleção nos mapas e painel de detalhes ---- */
(function(){
const D=window.__DET;if(!D||!D.mun)return;
const norm=t=>String(t).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const nf=(x,d)=>x.toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const FMT={i:v=>nf(Math.round(v),0),d1:v=>nf(v,1),d2:v=>nf(v,2),p1:v=>nf(v,1)+'%',p2:v=>nf(v,2)+'%',km:v=>nf(v,0)+' km',
 pos:v=>Math.round(v)+'º',s:v=>(v>0?'+':v<0?'−':'')+nf(Math.abs(Math.round(v)),0),t:v=>String(v)};
const names=Object.entries(D.mun).map(([cd,m])=>({cd,n:m.n,k:norm(m.n)})).sort((a,b)=>a.n.localeCompare(b.n,'pt-BR'));
let cur=null,dr=null,lastFocus=null;
function mk(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=txt;return e}
function drawer(){if(dr)return dr;dr=mk('aside','mdrawer');dr.id='mdrawer';dr.hidden=true;dr.setAttribute('role','dialog');
 dr.setAttribute('aria-label','Detalhes do município');document.body.appendChild(dr);return dr}
function mark(cd){document.querySelectorAll('.map .p.sel').forEach(p=>p.classList.remove('sel'));
 if(cd==null)return;document.querySelectorAll('.map .p[data-id="'+cd+'"]').forEach(p=>{p.classList.add('sel');p.parentNode.appendChild(p)})}
function url(cd){try{const u=new URL(location.href);if(cd==null)u.searchParams.delete('m');else u.searchParams.set('m',cd);
 history.replaceState(null,'',u)}catch(_){}}
function close(){cur=null;mark(null);url(null);if(dr)dr.hidden=true;if(lastFocus&&lastFocus.focus)try{lastFocus.focus({preventScroll:true})}catch(_){}}
function open(cd){const m=D.mun[cd];if(!m)return;cur=cd;mark(cd);url(cd);const d=drawer();d.replaceChildren();
 const h=mk('header');const t=mk('h3',null,m.n);const x=mk('button','x','×');x.type='button';x.setAttribute('aria-label','Fechar');
 x.addEventListener('click',close);h.append(t,x);d.appendChild(h);
 const dl=mk('dl');D.fields.forEach(([lab,key,f])=>{const v=m[key];if(v===null||v===undefined||v==='')return;
  const a=mk('dt',null,lab),b=mk('dd',null,(FMT[f]||FMT.t)(v));dl.append(a,b)});d.appendChild(dl);
 const top=(D.top||{})[cd];if(top&&top.length){d.appendChild(mk('h4',null,'Mais votados no município'));
  const ol=mk('ol','topl');top.forEach(r=>{const li=mk('li');const a=mk('span','nm',r[1]+' ');a.appendChild(mk('i',null,r[2]));
   const b=mk('b',null,nf(r[3],0)+' · '+nf(r[4],1)+'%');li.append(a,b);if(r[5])li.classList.add('foco');ol.appendChild(li)});d.appendChild(ol)}
 d.hidden=false;d.scrollTop=0}
document.addEventListener('click',e=>{const p=e.target.closest&&e.target.closest('.map .p[data-id]');
 if(p){lastFocus=null;open(p.getAttribute('data-id'));return}});
addEventListener('keydown',e=>{if(e.key==='Escape'&&cur!=null){close()}});
/* busca */
const inp=document.getElementById('msq'),list=document.getElementById('msl');
if(inp&&list){let items=[],act=-1;
 const hide=()=>{list.hidden=true;inp.setAttribute('aria-expanded','false');act=-1};
 function paint(){[...list.children].forEach((li,i)=>li.setAttribute('aria-selected',i===act))}
 function pick(i){const it=items[i];if(!it)return;hide();inp.value=it.n;lastFocus=inp;open(it.cd);
  const c=document.getElementById('mapa-estado');if(c){const r=c.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)c.scrollIntoView({block:'center',behavior:'smooth'})}}
 function upd(){const q=norm(inp.value.trim());list.replaceChildren();if(!q){hide();return}
  const a=names.filter(n=>n.k.startsWith(q)),b=names.filter(n=>!n.k.startsWith(q)&&n.k.includes(q));items=a.concat(b).slice(0,8);
  if(!items.length){const li=mk('li','vazio','Nenhum município com esse nome');list.appendChild(li)}
  items.forEach((it,i)=>{const li=mk('li',null,it.n);li.setAttribute('role','option');
   li.addEventListener('pointerdown',ev=>{ev.preventDefault();pick(i)});list.appendChild(li)});
  act=items.length?0:-1;paint();list.hidden=false;inp.setAttribute('aria-expanded','true')}
 inp.addEventListener('input',upd);inp.addEventListener('focus',()=>{if(inp.value)upd()});
 inp.addEventListener('blur',()=>setTimeout(hide,120));
 inp.addEventListener('keydown',e=>{if(list.hidden&&e.key==='ArrowDown'){upd();return}
  if(e.key==='ArrowDown'){e.preventDefault();act=Math.min(items.length-1,act+1);paint()}
  else if(e.key==='ArrowUp'){e.preventDefault();act=Math.max(0,act-1);paint()}
  else if(e.key==='Enter'){e.preventDefault();if(act>=0)pick(act)}
  else if(e.key==='Escape'){if(!list.hidden){e.stopPropagation();hide()}}})}
const q0=new URLSearchParams(location.search).get('m');if(q0&&D.mun[q0]){open(q0);
 const c=document.getElementById('mapa-estado');if(c)setTimeout(()=>c.scrollIntoView({block:'center'}),50)}
})();
