const $=id=>document.getElementById(id);let tab='items',items=[],alerts=[];
const API_BASE=(window.APP_CONFIG?.API_BASE_URL||'').replace(/\/$/,'');
const AUTH_KEY='monitor_promocoes_access_token';const LOCAL_DEV=['localhost','127.0.0.1'].includes(location.hostname);let authToken=localStorage.getItem(AUTH_KEY)||(LOCAL_DEV?'local-development-session':'');
function showLogin(show){$('loginGate').hidden=!show;$('logout').classList.toggle('hidden',LOCAL_DEV||show||!authToken);if(show)setTimeout(()=>$('loginPassword').focus(),50)}
$('loginForm').addEventListener('submit',async event=>{event.preventDefault();$('loginError').textContent='';const button=$('loginForm').querySelector('button');button.disabled=true;try{const result=await api('/api/auth/login',{method:'POST',body:JSON.stringify({password:$('loginPassword').value})});authToken=result.access_token;localStorage.setItem(AUTH_KEY,authToken);$('loginPassword').value='';showLogin(false);await load()}catch(error){$('loginError').textContent=error.message}finally{button.disabled=false}});
$('logout').addEventListener('click',()=>{if(LOCAL_DEV)return;authToken='';localStorage.removeItem(AUTH_KEY);items=[];alerts=[];render();showLogin(true)});
async function api(path,opts={}){
 const controller=new AbortController();
 const timeout=setTimeout(()=>controller.abort(),30000);
 try {
  const response=await fetch(`${API_BASE}${path}`,{
   ...opts,signal:controller.signal,
   headers:{'Accept':'application/json','Content-Type':'application/json',...(path!='/api/auth/login'&&authToken?{'Authorization':`Bearer ${authToken}`}:{ }),...(opts.headers||{})}
  });
  const type=response.headers.get('content-type')||'';
  const data=type.includes('application/json')?await response.json():{};
  if(!response.ok){if(response.status===401&&path!='/api/auth/login'){authToken='';localStorage.removeItem(AUTH_KEY);showLogin(true)}throw Error(data.error||`Falha na solicitação (${response.status})`)}
  return data;
 } catch(error) {
  if(error.name==='AbortError') throw Error('A solicitação excedeu o tempo limite.');
  throw error;
 } finally { clearTimeout(timeout); }
}
function money(v,c){return (c==='BRL'?'R$':c)+' '+Number(v).toFixed(2).replace('.',',')}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function load(){
 if(!navigator.onLine){$('health').textContent='Sem conexão';$('health').className='status';return}
 if(!authToken){$('health').textContent='Aguardando autenticação';showLogin(true);return}
 try{
  items=await api('/api/items');alerts=await api('/api/alerts');
  $('health').textContent='Backend conectado';$('health').className='status success';showLogin(false);
  render();
 }catch(e){
  $('health').textContent='Backend indisponível';$('health').className='status';
  $('message').textContent=e.message;
 }
}
function render(){$('itemsCount').textContent=items.length;$('alertsCount').textContent=alerts.length;const root=$('content');if(tab==='items'){if(!items.length){root.innerHTML='<div class="empty">Nenhum item monitorado. Cadastre um produto ao lado.</div>';return}root.innerHTML=items.map(i=>`<div class="item ${i.active?'':'paused'}"><div style="min-width:0;flex:1"><div class="name">${esc(i.name)} <span class="muted">· ${esc(i.category)}</span></div><div>${i.target_price?`<span class="price">até R$ ${Number(i.target_price).toFixed(2).replace('.',',')}</span>`:''}${i.min_discount!==null?`<span class="price">−${i.min_discount}%</span>`:''}</div><div class="muted">Fontes: ${esc(i.sources.join(', '))} · ${esc(i.frequency)} · ${i.active?'ativo':'pausado'}</div><div class="muted">Última pesquisa: ${i.last_checked?new Date(i.last_checked).toLocaleString('pt-BR'):'ainda não pesquisado'}</div><div id="offers-${i.id}" class="muted">Carregando histórico...</div></div><div class="actions-small"><button class="btn secondary" data-toggle="${i.id}" data-active="${!i.active}">${i.active?'Pausar':'Ativar'}</button><button class="btn danger" data-delete="${i.id}">Remover</button></div></div>`).join('');items.forEach(async i=>{try{const os=await api('/api/offers/'+i.id);const el=$('offers-'+i.id);if(el)el.innerHTML=os.length?os.slice(0,5).map(o=>`<div class="offer"><b>${esc(o.store)}</b> · ${money(o.price,o.currency)} · ${Number(o.discount).toFixed(0)}% de desconto<br><a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">Ver oferta</a> <span class="muted">${new Date(o.checked_at).toLocaleString('pt-BR')}</span></div>`).join(''):'Nenhuma oferta encontrada ainda.'}catch{}})}else{root.innerHTML=alerts.length?alerts.map(a=>`<div class="alert"><b>${esc(a.name)}</b> <span class="pill">${esc(a.store)}</span><div>Preço: <b>${money(a.price,a.currency)}</b> · Desconto: ${Number(a.discount).toFixed(0)}%</div><div class="muted">${new Date(a.created_at).toLocaleString('pt-BR')} · ${a.notified?'Notificado: '+esc(a.notified):'Alerta registrado; confira a configuração do canal'}</div><a href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">Abrir oferta</a></div>`).join(''):'<div class="empty">Nenhum alerta gerado até agora.</div>'}}
$('form').addEventListener('submit',async e=>{e.preventDefault();$('formError').textContent='';const channels=[...document.querySelectorAll('#channels input:checked')].map(x=>x.value);const data={name:$('name').value.trim(),category:$('category').value,target_price:$('target').value||null,min_discount:$('discount').value||null,sources:[...new Set([...document.querySelectorAll('#sources input:checked')].map(x=>x.value))],channels,destinations:{'E-mail':$('destinationEmail').value.trim(),'Telegram':$('destinationTelegram').value.trim(),'WhatsApp':$('destinationWhatsapp').value.trim()},frequency:$('frequency').value};try{await api('/api/items',{method:'POST',body:JSON.stringify(data)});$('form').reset();$('message').textContent='Monitoramento salvo.';await load()}catch(err){$('formError').textContent=err.message}});
$('content').addEventListener('click',async e=>{const t=e.target.closest('[data-toggle],[data-delete]');if(!t)return;try{if(t.dataset.toggle)await api('/api/items/'+t.dataset.toggle,{method:'PATCH',body:JSON.stringify({active:t.dataset.active==='true'})});else if(t.dataset.delete&&confirm('Remover este monitoramento e seu histórico?'))await api('/api/items/'+t.dataset.delete,{method:'DELETE'});await load()}catch(err){$('message').textContent=err.message}});
$('tabItems').onclick=()=>{tab='items';$('tabItems').classList.add('active');$('tabAlerts').classList.remove('active');render()};$('tabAlerts').onclick=()=>{tab='alerts';$('tabAlerts').classList.add('active');$('tabItems').classList.remove('active');render()};
$('scan').onclick=async()=>{const b=$('scan');b.disabled=true;b.textContent='Pesquisando...';$('message').textContent='Consultando fontes reais. Isso pode levar alguns segundos.';try{const r=await api('/api/scan',{method:'POST',body:'{}'});$('message').textContent=r.results.map(x=>`${x.item}: ${x.offers_found} oferta(s), ${x.alerts_created} alerta(s)${x.errors.length?' · '+x.errors.join(' | '):''}`).join(' | ')||'Nenhum item ativo.';await load()}catch(e){$('message').textContent=e.message}finally{b.disabled=false;b.textContent='Pesquisar agora'}};
$('export').onclick=async()=>{try{const data=await api('/api/alerts');const cols=['name','store','currency','price','discount','url','created_at'];const csv=[cols.join(';'),...data.map(x=>cols.map(k=>'"'+String(x[k]??'').replace(/"/g,'""')+'"').join(';'))].join('\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));a.download='alertas-promocoes.csv';a.click();URL.revokeObjectURL(a.href)}catch(e){$('message').textContent=e.message}};
if(authToken)showLogin(false);else showLogin(true);load();setInterval(()=>{if(document.visibilityState==='visible')load()},30000);window.addEventListener('online',load);
