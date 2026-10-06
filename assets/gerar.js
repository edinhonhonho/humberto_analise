(function(){
const q=new URLSearchParams(location.search),t=document.getElementById('gt'),s=document.getElementById('gs');
const nome=q.get('nome')||'o candidato';t.textContent='Gerando a análise de '+nome+'…';
const u=['ano','uf','cargo','numero'].map(k=>k+'='+encodeURIComponent(q.get(k)||'')).join('&');
function falha(m){t.textContent='Esta análise ainda não foi gerada';s.textContent=m}
fetch('api/gerar?'+u).then(r=>r.json()).then(j=>{
 if(j.ok){location.replace(j.url)}else{falha(j.erro||'Não foi possível gerar a análise.')}
}).catch(()=>falha('Para gerar na hora, abra o site pelo servidor local: python servir.py, no computador onde estão os dados. '
 +'Ou rode python rodar.py --lote para gerar todas de uma vez.'));
})();
