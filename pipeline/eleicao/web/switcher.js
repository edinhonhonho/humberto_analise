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
const su=mk('select'),sc=mk('select'),q=mk('input');q.type='search';q.placeholder='Nome ou número';q.autocomplete='off';
const wrap=(l,e)=>{const w=mk('label',null,l);w.appendChild(e);return w};
const ttl=mk('h2','swt','Trocar candidato');
const aviso=mk('p','swa','Análises geradas apenas para candidatos de partidos de esquerda, além dos destaques. Os demais candidatos aparecem na lista, sem análise.');
const fl=mk('div','swf');fl.append(wrap('Estado',su),wrap('Cargo',sc),wrap('Buscar candidato',q));
const sem=mk('label','swchk');const ck=mk('input');ck.type='checkbox';sem.append(ck,document.createTextNode(' Mostrar também candidatos sem análise'));
const info=mk('p','mhint'),ul=mk('ul','swl');pan.append(ttl,aviso,fl,sem,info,ul);
const LOCAL=/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
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
 const hd=document.querySelector('header.hd');if(hd)hd.before(sec)}
load(root+'data/manifest.js').then(()=>{M=window.__MAN;cards()}).catch(()=>{});
function opt(sel,vals,lab,def){sel.replaceChildren();vals.forEach(v=>{const o=mk('option',null,lab?lab(v):v);o.value=v;sel.appendChild(o)});if(vals.includes(def))sel.value=def}
const ANO=String(cur.ano);
const GR=()=>M.grupos.filter(g=>String(g.ano)===ANO&&g.cargo!==1);
function filtros(first){const u0=GR();opt(su,uniq(u0.map(g=>g.uf)).sort(),null,first?cur.uf:su.value);
 const u=u0.filter(g=>g.uf===su.value);opt(sc,uniq(u.map(g=>String(g.cargo))).sort((x,y)=>x-y),v=>(u.find(g=>String(g.cargo)===v)||{}).cargo_nome,first?String(cur.cargo):sc.value)}
async function lista(){const g=GR().find(g=>g.uf===su.value&&String(g.cargo)===sc.value);ul.replaceChildren();
 if(!g){info.textContent='';return}
 const k=g.ano+'_'+g.uf+'_'+g.cargo_slug;
 if(!cache[k]){try{await load(root+'data/idx/'+k+'.js?'+Date.now());cache[k]=(window.__IDX||{})[k]||[]}catch(_){cache[k]=[]}}
 const t=norm(q.value.trim());const todos=ck.checked;
 const rows=cache[k].filter(r=>(todos||r[3])&&(!t||norm(r[1]).includes(t)||String(r[0]).startsWith(t)));
 const prontos=cache[k].filter(r=>r[3]).length;
 info.textContent=prontos+' com análise de '+cache[k].length+' candidatos';
 if(!rows.length){ul.appendChild(mk('li','vazio','Nenhum candidato encontrado.'));return}
 rows.slice(0,150).forEach(r=>{const li=mk('li'),ok=!!r[3];let a;
  if(ok||LOCAL){a=mk('a',null,r[1]);a.href=ok?pagina(g.ano,g.uf,g.cargo_slug,r[0]):gerar(g.ano,g.uf,g.cargo_slug,r[0],r[1])}
  else{a=mk('span','nm off',r[1])}
  if(g.ano===cur.ano&&g.uf===cur.uf&&g.cargo===cur.cargo&&r[0]===cur.numero)a.setAttribute('aria-current','page');
  li.append(a,mk('span',ok?null:'gera',(ok?'':(LOCAL?'gerar análise · ':'sem análise · '))+'nº '+r[0]+' · '+r[2].toLocaleString('pt-BR')+' votos'));ul.appendChild(li)})}
let fi=false;async function abrir(){if(!M){try{await load(root+'data/manifest.js');M=window.__MAN}catch(_){info.textContent='Não consegui carregar a lista de candidatos.';return}}if(!fi){filtros(true);fi=true}lista()}
btn.addEventListener('click',e=>{e.stopPropagation();const o=pan.hidden;pan.hidden=!o;btn.setAttribute('aria-expanded',o);
 const ip=document.getElementById('idxp');if(o&&ip)ip.hidden=true;if(o)abrir()});
document.addEventListener('click',e=>{if(!pan.hidden&&!pan.contains(e.target)&&e.target!==btn){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
addEventListener('keydown',e=>{if(e.key==='Escape'&&!pan.hidden){pan.hidden=true;btn.setAttribute('aria-expanded','false')}});
su.addEventListener('change',()=>{filtros(false);lista()});sc.addEventListener('change',lista);q.addEventListener('input',lista);ck.addEventListener('change',lista);
})();
