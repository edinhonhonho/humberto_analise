(function(){
const B=document.body,root=B.dataset.root;if(!root)return;
const cur=JSON.parse(B.dataset.cur),nav=document.querySelector('nav.top'),bar=nav&&nav.querySelector('.in');if(!bar)return;
const norm=t=>String(t).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const mk=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
function load(src){return new Promise((ok,err)=>{const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=()=>err(src);document.head.appendChild(s)})}
const pagina=(ano,uf,slug,num)=>root+ano+'/'+uf.toLowerCase()+'/'+slug+'/'+num+'/index.html';
const gerar=(ano,uf,slug,num,nome)=>root+'gerar.html?ano='+ano+'&uf='+uf+'&cargo='+slug+'&numero='+num+'&nome='+encodeURIComponent(nome);
const btn=mk('button','idx swbtn','Trocar candidato');btn.type='button';btn.setAttribute('aria-expanded','false');
const pan=mk('div','swp');pan.hidden=true;bar.appendChild(btn);nav.appendChild(pan);
const ANO=String(cur.ano);
let uf=cur.uf,cargo=cur.cargo,M=null,mostrar=10;const cache={};
const uniq=a=>[...new Set(a)];
const ttl=mk('h2','swt','Trocar candidato');
const aviso=mk('p','swa','Análises geradas apenas para candidatos de partidos de esquerda, além dos destaques. Os demais candidatos ficam fora da lista, a menos que você peça para mostrá-los.');
const gu=mk('div','swgrp'),gc=mk('div','swgrp');
const qw=mk('div','swq'),q=mk('input');q.type='search';q.placeholder='Buscar por nome ou número';q.autocomplete='off';q.setAttribute('aria-label','Buscar candidato');qw.appendChild(q);
const sem=mk('label','swchk');const ck=mk('input');ck.type='checkbox';sem.append(ck,document.createTextNode(' Mostrar também candidatos sem análise'));
const info=mk('p','mhint'),ul=mk('ul','swl'),mais=mk('button','swmais','Mostrar mais');mais.type='button';mais.hidden=true;
pan.append(ttl,aviso,gu,gc,qw,sem,info,ul,mais);
const LOCAL=/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
const GR=()=>M.grupos.filter(g=>String(g.ano)===ANO&&g.cargo!==1);
// ---- ir para outra página: aviso de carregamento + pré-carga
let barra=null;
function indo(){document.body.classList.add('indo');if(!barra){barra=mk('div');barra.id='progresso';document.body.appendChild(barra)}requestAnimationFrame(()=>barra.classList.add('on'))}
addEventListener('pageshow',e=>{if(e.persisted){document.body.classList.remove('indo');if(barra)barra.classList.remove('on')}});
const pre=new Set();
function prefetch(href){if(!href||pre.has(href))return;pre.add(href);try{const l=document.createElement('link');l.rel='prefetch';l.href=href;document.head.appendChild(l);
 const d=href.replace(/index\.html.*$/,'data.js');if(d!==href){const s=document.createElement('link');s.rel='prefetch';s.as='script';s.href=d;document.head.appendChild(s)}}catch(_){}}
function liga(el){if(!el||!el.href||!/index\.html/.test(el.href))return;
 ['pointerenter','focus','touchstart'].forEach(ev=>el.addEventListener(ev,()=>prefetch(el.href),{passive:true,once:true}));
 el.addEventListener('click',e=>{if(e.metaKey||e.ctrlKey||e.shiftKey||e.button)return;indo()})}
// ---- cards de destaque (antes do nome do candidato)
function cards(){const D=(M.destaques||[]);if(!D.length||document.querySelector('.dest'))return;
 const sec=mk('section','dest');sec.setAttribute('aria-label','Candidatos em destaque');
 D.forEach(d=>{const here=d.ano===cur.ano&&d.uf===cur.uf&&d.cargo===cur.cargo&&d.numero===cur.numero;
  const el=mk(here?'span':'a','dcard'+(d.ok?'':' off'));if(here)el.setAttribute('aria-current','page');
  else{el.href=d.ok?pagina(d.ano,d.uf,d.cargo_slug,d.numero):gerar(d.ano,d.uf,d.cargo_slug,d.numero,d.nome);liga(el)}
  const ph=mk('span','ph');if(d.foto){const im=mk('img');im.src=root+'assets/'+d.foto;im.alt=d.nome;ph.appendChild(im)}
  const tx=mk('span','tx');tx.append(mk('b',null,d.nome),mk('small',null,d.cargo_nome+' · '+d.uf+' · nº '+d.numero));
  el.append(ph,tx);if(here)el.appendChild(mk('em',null,'em análise'));sec.appendChild(el)});
 const hd=document.querySelector('header.hd');if(hd)hd.before(sec)}
load(root+'data/manifest.js').then(()=>{M=window.__MAN;cards()}).catch(()=>{});
// ---- painel
function chips(box,rotulo,itens,atual,fn){box.replaceChildren(mk('span','lab',rotulo));
 itens.forEach(([v,t])=>{const b=mk('button',null,t);b.type='button';b.setAttribute('aria-pressed',String(v)===String(atual));b.addEventListener('click',()=>fn(v));box.appendChild(b)})}
function montar(){const g0=GR();const ufs=uniq(g0.map(g=>g.uf)).sort();if(!ufs.includes(uf))uf=ufs[0];
 chips(gu,'Estado',ufs.map(u=>[u,u]),uf,v=>{uf=v;mostrar=10;montar();lista()});
 const cs=g0.filter(g=>g.uf===uf).sort((x,y)=>x.cargo-y.cargo);if(!cs.some(g=>g.cargo===cargo))cargo=cs[0]?cs[0].cargo:cargo;
 chips(gc,'Cargo',cs.map(g=>[g.cargo,g.cargo_nome]),cargo,v=>{cargo=Number(v);mostrar=10;montar();lista()})}
async function lista(){const g=GR().find(g=>g.uf===uf&&g.cargo===cargo);ul.replaceChildren();mais.hidden=true;
 if(!g){info.textContent='';return}
 const k=g.ano+'_'+g.uf+'_'+g.cargo_slug;
 if(!cache[k]){try{await load(root+'data/idx/'+k+'.js?'+Date.now());cache[k]=(window.__IDX||{})[k]||[]}catch(_){cache[k]=[]}}
 const t=norm(q.value.trim()),todos=ck.checked,P=(M.partidos||{});
 const sig=n=>{let s=String(n);const d=s.length;const p=d>=2?s.slice(0,2):s;return P[p]||''};
 const rows=cache[k].filter(r=>(todos||r[3])&&(!t||norm(r[1]).includes(t)||String(r[0]).startsWith(t)));
 const prontos=cache[k].filter(r=>r[3]).length;
 info.textContent=t?rows.length+' resultado(s)':prontos+' candidatos com análise'+(todos?' · '+cache[k].length+' na lista completa':'');
 if(!rows.length){ul.appendChild(mk('li','vazio','Nenhum candidato encontrado.'));return}
 rows.slice(0,mostrar).forEach(r=>{const li=mk('li'),ok=!!r[3];let a;
  if(ok||LOCAL){a=mk('a','row');a.href=ok?pagina(g.ano,g.uf,g.cargo_slug,r[0]):gerar(g.ano,g.uf,g.cargo_slug,r[0],r[1]);if(ok)liga(a)}
  else{a=mk('div','row off')}
  if(g.ano===cur.ano&&g.uf===cur.uf&&g.cargo===cur.cargo&&r[0]===cur.numero)a.setAttribute('aria-current','page');
  const who=mk('span','who');who.append(mk('b','nm',r[1]),mk('small',null,(sig(r[0])?sig(r[0])+' · ':'')+'nº '+r[0]));
  a.append(who,mk('span','vt'+(ok?'':' gera'),(ok?'':(LOCAL?'gerar análise · ':'sem análise · '))+r[2].toLocaleString('pt-BR')+' votos'));li.appendChild(a);ul.appendChild(li)});
 if(rows.length>mostrar){mais.hidden=false;mais.textContent='Mostrar mais ('+(rows.length-mostrar)+')'}}
let fi=false;async function abrir(){if(!M){try{await load(root+'data/manifest.js');M=window.__MAN}catch(_){info.textContent='Não consegui carregar a lista de candidatos.';return}}if(!fi){fi=true;montar()}lista();setTimeout(()=>q.focus({preventScroll:true}),60)}
btn.addEventListener('click',e=>{e.stopPropagation();const o=pan.hidden;pan.hidden=!o;btn.setAttribute('aria-expanded',o);
 const ip=document.getElementById('idxp');if(o&&ip)ip.hidden=true;if(o)abrir()});
pan.addEventListener('click',e=>e.stopPropagation());
document.addEventListener('click',e=>{if(!pan.hidden&&!pan.contains(e.target)&&e.target!==btn){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
addEventListener('keydown',e=>{if(e.key==='Escape'&&!pan.hidden){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
q.addEventListener('input',()=>{mostrar=10;lista()});ck.addEventListener('change',()=>{mostrar=10;lista()});mais.addEventListener('click',()=>{mostrar+=15;lista()});
})();
