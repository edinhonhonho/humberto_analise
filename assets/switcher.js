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
const sa=mk('select'),su=mk('select'),sc=mk('select'),q=mk('input');q.type='search';q.placeholder='Nome ou número';q.autocomplete='off';
const wrap=(l,e)=>{const w=mk('label',null,l);w.appendChild(e);return w};
const fl=mk('div','swf');fl.append(wrap('Ano',sa),wrap('UF',su),wrap('Cargo',sc),wrap('Candidato',q));
const info=mk('p','mhint'),ul=mk('ul','swl');pan.append(fl,info,ul);
let M=null;const cache={};
const uniq=a=>[...new Set(a)];
function cards(){const D=(M.destaques||[]);if(!D.length||document.querySelector('.dest'))return;
 const sec=mk('section','dest');sec.setAttribute('aria-label','Candidatos em destaque');
 D.forEach(d=>{const here=d.ano===cur.ano&&d.uf===cur.uf&&d.cargo===cur.cargo&&d.numero===cur.numero;
  const el=mk(here?'span':'a','dcard'+(d.ok?'':' off'));if(here)el.setAttribute('aria-current','page');
  else el.href=d.ok?pagina(d.ano,d.uf,d.cargo_slug,d.numero):gerar(d.ano,d.uf,d.cargo_slug,d.numero,d.nome);
  const ph=mk('span','ph');if(d.foto){const im=mk('img');im.src=root+'assets/'+d.foto;im.alt=d.nome;ph.appendChild(im)}
  const tx=mk('span','tx');tx.append(mk('b',null,d.nome),mk('small',null,d.cargo_nome+' · '+d.uf+' · nº '+d.numero));
  el.append(ph,tx);if(here)el.appendChild(mk('em',null,'em análise'));sec.appendChild(el)});
 const hd=document.querySelector('header.hd');if(hd)hd.after(sec)}
load(root+'data/manifest.js').then(()=>{M=window.__MAN;cards()}).catch(()=>{});
function opt(sel,vals,lab,def){sel.replaceChildren();vals.forEach(v=>{const o=mk('option',null,lab?lab(v):v);o.value=v;sel.appendChild(o)});if(vals.includes(def))sel.value=def}
function filtros(first){const G=M.grupos;
 opt(sa,uniq(G.map(g=>String(g.ano))).sort().reverse(),null,first?String(cur.ano):sa.value);
 const a=G.filter(g=>String(g.ano)===sa.value);opt(su,uniq(a.map(g=>g.uf)).sort(),null,first?cur.uf:su.value);
 const u=a.filter(g=>g.uf===su.value);opt(sc,uniq(u.map(g=>String(g.cargo))).sort((x,y)=>x-y),v=>(u.find(g=>String(g.cargo)===v)||{}).cargo_nome,first?String(cur.cargo):sc.value)}
async function lista(){const g=M.grupos.find(g=>String(g.ano)===sa.value&&g.uf===su.value&&String(g.cargo)===sc.value);ul.replaceChildren();
 if(!g){info.textContent='';return}
 const k=g.ano+'_'+g.uf+'_'+g.cargo_slug;
 if(!cache[k]){try{await load(root+'data/idx/'+k+'.js?'+Date.now());cache[k]=(window.__IDX||{})[k]||[]}catch(_){cache[k]=[]}}
 const t=norm(q.value.trim());const rows=cache[k].filter(r=>!t||norm(r[1]).includes(t)||String(r[0]).startsWith(t));
 const prontos=cache[k].filter(r=>r[3]).length;
 info.textContent=rows.length+' candidato(s) · '+prontos+' com análise pronta; os demais são gerados na hora pelo servir.py';
 rows.slice(0,100).forEach(r=>{const li=mk('li'),ok=!!r[3],a=mk('a',null,r[1]);
  a.href=ok?pagina(g.ano,g.uf,g.cargo_slug,r[0]):gerar(g.ano,g.uf,g.cargo_slug,r[0],r[1]);
  if(g.ano===cur.ano&&g.uf===cur.uf&&g.cargo===cur.cargo&&r[0]===cur.numero)a.setAttribute('aria-current','page');
  li.append(a,mk('span',ok?null:'gera',(ok?'':'gerar análise · ')+'nº '+r[0]+' · '+r[2].toLocaleString('pt-BR')+' votos'));ul.appendChild(li)})}
let fi=false;async function abrir(){if(!M){try{await load(root+'data/manifest.js');M=window.__MAN}catch(_){info.textContent='Não consegui carregar a lista de candidatos.';return}}if(!fi){filtros(true);fi=true}lista()}
btn.addEventListener('click',e=>{e.stopPropagation();const o=pan.hidden;pan.hidden=!o;btn.setAttribute('aria-expanded',o);
 const ip=document.getElementById('idxp');if(o&&ip)ip.hidden=true;if(o)abrir()});
document.addEventListener('click',e=>{if(!pan.hidden&&!pan.contains(e.target)&&e.target!==btn){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
addEventListener('keydown',e=>{if(e.key==='Escape'&&!pan.hidden){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
sa.addEventListener('change',()=>{filtros(false);lista()});su.addEventListener('change',()=>{filtros(false);lista()});sc.addEventListener('change',lista);q.addEventListener('input',lista);
})();
