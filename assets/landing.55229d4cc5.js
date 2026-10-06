(function(){
const M=window.__MAN;if(!M)return;
const q=s=>document.querySelector(s),norm=t=>String(t).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const sa=q('#fa'),su=q('#fu'),sc=q('#fc'),nm=q('#fn'),out=q('#lista'),info=q('#linfo');
function opt(sel,vals,lab){const cur=sel.value;sel.replaceChildren();vals.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=lab?lab(v):v;sel.appendChild(o)});if(vals.includes(cur))sel.value=cur}
const uniq=a=>[...new Set(a)];
function grupos(){return M.grupos.filter(g=>(!sa.value||String(g.ano)===sa.value)&&(!su.value||g.uf===su.value)&&(!sc.value||String(g.cargo)===sc.value))}
let cache={};
function carregar(g){const k=g.ano+'_'+g.uf+'_'+g.cargo;if(cache[k])return Promise.resolve(cache[k]);
 return new Promise((ok,err)=>{window.__IDX=window.__IDX||{};const s=document.createElement('script');s.src='data/idx/'+k+'.js';
  s.onload=()=>{cache[k]=window.__IDX[k]||[];ok(cache[k])};s.onerror=()=>err(new Error(k));document.head.appendChild(s)})}
async function render(){const gs=grupos();let rows=[];
 for(const g of gs){try{(await carregar(g)).forEach(r=>rows.push(Object.assign({g},{r})))}catch(_){}}
 const t=norm(nm.value.trim());if(t)rows=rows.filter(x=>norm(x.r[1]).includes(t)||String(x.r[0]).startsWith(t));
 rows.sort((a,b)=>b.r[2]-a.r[2]);info.textContent=rows.length+' candidato(s)';out.replaceChildren();
 rows.slice(0,200).forEach(x=>{const li=document.createElement('li'),a=document.createElement('a');
  a.href=x.g.ano+'/'+x.g.uf.toLowerCase()+'/'+x.g.cargo+'/'+x.r[0]+'/';a.textContent=x.r[1];
  const m=document.createElement('span');m.textContent=x.g.cargo_nome+' · '+x.g.uf+' · '+x.g.ano+' · nº '+x.r[0]+' · '+x.r[2].toLocaleString('pt-BR')+' votos';
  li.append(a,m);out.appendChild(li)});
 if(rows.length>200){const li=document.createElement('li');li.className='mais';li.textContent='Mostrando 200 de '+rows.length+'. Refine a busca.';out.appendChild(li)}}
function filtros(){opt(sa,uniq(M.grupos.map(g=>String(g.ano))).sort().reverse());
 const a=M.grupos.filter(g=>String(g.ano)===sa.value);opt(su,uniq(a.map(g=>g.uf)).sort());
 const u=a.filter(g=>g.uf===su.value);opt(sc,uniq(u.map(g=>String(g.cargo))).sort(),v=>(u.find(g=>String(g.cargo)===v)||{}).cargo_nome)}
sa.addEventListener('change',()=>{filtros();render()});su.addEventListener('change',()=>{filtros();render()});
sc.addEventListener('change',render);nm.addEventListener('input',render);filtros();render();
})();
