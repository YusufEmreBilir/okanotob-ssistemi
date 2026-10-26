const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state=null, selected=null, detailDay=null, loading=false;
const istParts = () => Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Istanbul',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).map(p=>[p.type,p.value]));
const today = () => ({Sat:'C',Sun:'P'}[istParts().weekday] || 'I');
const nowMinutes = () => Number(istParts().hour)*60+Number(istParts().minute);
const todaySelected = day => day===today();
const dayNames = {I:'Hafta içi',C:'Cumartesi',P:'Pazar'};
$('#day').value=today();
function clock(){ $('#clock').textContent=`${istParts().hour}:${istParts().minute}`; }
function noticesUnknown(){return !state || !!state.noticesState.error || state.noticesState.stale;}
function status(line){
 if(noticesUnknown())return '<span class="pill error">Duyurular alınamadı</span>';
 const cancellations=line.notices.filter(n=>/yap[iı]lama|iptal/i.test(n.message));
 if(cancellations.length)return `<span class="pill warn">${cancellations.length} iptal duyurusu</span>`;
 if(line.notices.length)return `<span class="pill warn">${line.notices.length} hat duyurusu</span>`;
 return '<span class="pill">İptal duyurusu yok</span>';
}
function possibleNotice(line,time){return line.notices.some(n=>/yap[iı]lama|iptal/i.test(n.message) && [...n.message.matchAll(/\b(\d{1,2})[:.](\d{2})\b/g)].some(m=>`${m[1].padStart(2,'0')}:${m[2]}`===time.padStart(5,'0')));}
function rowsFor(line,day,direction='all'){return line.schedule.filter(s=>s.day===day&&(direction==='all'||s.direction===direction));}
function nextFor(line){const day=$('#day').value;return rowsFor(line,day,$('#direction').value).filter(s=>!todaySelected(day)||s.minutes>=nowMinutes()).sort((a,b)=>a.minutes-b.minutes)[0];}
function render(){
 if(!state)return;
 const q=$('#search').value.toLocaleUpperCase('tr-TR').trim();
 const lines=state.lines.filter(l=>(l.code+' '+l.name).toLocaleUpperCase('tr-TR').includes(q));
 $('#count').textContent=String(lines.length).padStart(2,'0');
 $('#lines').innerHTML=lines.length?lines.map(l=>{const n=nextFor(l),err=l.scheduleState.error;return `<button class="line-card" data-code="${esc(l.code)}" aria-label="${esc(l.code)} tüm saatler ve duyurular"><span class="line-main"><span class="badge">${esc(l.code)}</span><span><span class="route-name">${esc(l.name.toLocaleLowerCase('tr-TR'))}</span><span class="route-sub">Okan Üniversitesi · ${l.routeCodes.length?'Kampüsten geçen seferler':'Durak servisiyle doğrulandı'}</span></span></span><span class="next-time">${err&&!l.scheduleState.stale?'—':n?esc(n.time):'—'}<small>${err?(l.scheduleState.stale?'Eski veri · doğrulanamadı':'Saatler alınamadı'):n?`${n.direction==='D'?'Gidiş':'Dönüş'} · ${todaySelected($('#day').value)?'bugün':dayNames[$('#day').value]}${possibleNotice(l,n.time)?' · iptal uyarısı':''}`:rowsFor(l,$('#day').value,$('#direction').value).length?'Bugünkü kalkışlar bitti':'Bu seçimde sefer yok'}</small></span><span class="status-wrap">${status(l)}</span><span class="chevron">›</span></button>`}).join(''):'<div class="empty">Aradığın hat bulunamadı. Başka bir hat veya güzergâh dene.</div>';
 const errors=state.lines.some(l=>l.scheduleState.error)||noticesUnknown();
 $('#connection').innerHTML=errors?'<div class="status-error">Bazı İETT verileri güncellenemedi. Eksik bilgi, seferin olmadığı veya iptal edilmediği anlamına gelmez.</div>':'';
 const stamps=state.lines.map(l=>l.scheduleState.updatedAt).filter(Boolean);if(state.noticesState.updatedAt)stamps.push(state.noticesState.updatedAt);
 $('#updated').textContent=stamps.length?`En eski veri: ${new Date(stamps.sort()[0]).toLocaleString('tr-TR',{timeZone:'Europe/Istanbul',hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'})} · 60 sn’de yenilenir`:'Güncel veri alınamadı';
 if(selected)renderDetail();
}
async function refresh(){
 if(loading)return;loading=true;$('#refresh').disabled=true;
 try{const r=await fetch('/api/dashboard',{signal:AbortSignal.timeout(55000)});if(!r.ok)throw Error();const data=await r.json();if(!Array.isArray(data.lines))throw Error();state=data;render();}
 catch{ $('#connection').innerHTML='<div class="status-error">Bağlantı kurulamadı. Yenile ile tekrar deneyebilirsin. Ekrandaki önceki bilgiler güncel olmayabilir.</div>';if(!state)$('#lines').innerHTML='<div class="empty">Seferler yüklenemedi.</div>';else{state.noticesState={...state.noticesState,stale:true,error:'Bağlantı kesildi'};state.lines.forEach(l=>l.scheduleState={...l.scheduleState,stale:true,error:'Bağlantı kesildi'});render();$('#connection').innerHTML='<div class="status-error">Bağlantı kurulamadı. Son alınan bilgiler gösteriliyor; güncellik doğrulanamadı.</div>';$('#updated').textContent='Bağlantı kesildi · son alınan bilgiler gösteriliyor';}}
 finally{loading=false;$('#refresh').disabled=false;}
}
function renderDetail(){
 const line=state.lines.find(l=>l.code===selected);if(!line)return;
 $('#detail-title').textContent=line.code;
 const direction=$('#direction').value;
 const notices=line.notices.map(n=>`<article class="notice"><strong>${esc(n.type||'Duyuru')}</strong> · ${esc(n.message)}<small>${esc(n.recordedAt)} · API’de duyuru tarihi belirtilmiyor.</small></article>`).join('');
 $('#detail-body').innerHTML=`<p class="detail-name">${esc(line.name)}</p><div class="info"><span>ⓘ</span><p>İlk duraktan planlanan kalkış saatleri. Kampüse varış saati değildir. Gidiş / dönüş, İETT’nin D / G kodlarıdır.</p></div><div class="detail-tabs">${Object.entries(dayNames).map(([v,n])=>`<button data-day="${v}" class="${detailDay===v?'active':''}" aria-pressed="${detailDay===v}">${n}</button>`).join('')}</div>${line.scheduleState.error?`<div class="notice">${line.scheduleState.stale?'Son alınan saatler gösteriliyor; güncellik doğrulanamadı.':'Sefer saatleri alınamadı. Yenileyerek tekrar deneyin.'}</div>`:''}${['D','G'].filter(d=>direction==='all'||direction===d).map(d=>{const rows=rowsFor(line,detailDay,d);return `<section class="schedule-group"><h3>${d==='D'?'Gidiş':'Dönüş'} <span class="muted">(${d}) · ${rows.length} sefer</span></h3><div class="time-grid">${rows.map(s=>`<div class="time-cell ${todaySelected(detailDay)&&s.minutes<nowMinutes()?'past':''} ${possibleNotice(line,s.time)?'warning':''}">${esc(s.time)}<small>${possibleNotice(line,s.time)?'İptal duyurusu var*':noticesUnknown()?'İptal bilgisi alınamadı':'Planlanan kalkış'}${s.marker?' · '+esc(s.marker):''}</small></div>`).join('')||'<p class="detail-note">Bu gün ve yönde kampüsten geçtiği doğrulanan sefer bulunamadı.</p>'}</div></section>`}).join('')}<p class="detail-note">* Saat eşleşmesi kesin iptal doğrulaması değildir. Duyurunun kalkış yerini ve yönünü kontrol et. Tarihi belirsiz duyurular nedeniyle seferler listeden çıkarılmaz.</p><h3 class="notice-title">İptaller ve hat duyuruları</h3>${noticesUnknown()?'<div class="notice">Duyuruların güncelliği doğrulanamadı. İptal durumu bilinmiyor.</div>':''}${notices||(!noticesUnknown()?'<p class="detail-note">Bu hat için API yanıtında iptal veya güzergâh duyurusu bulunmuyor.</p>':'')}<p class="detail-note">Hat tespiti: ${esc(line.source)} · ${esc(line.checkedAt)}. Kaynaklar arasında isim ve güzergâh farklılıkları olabilir; İETT’nin güncel bilgilerini kontrol edin.</p>`;
}
$('#lines').addEventListener('click',e=>{const button=e.target.closest('[data-code]');if(!button)return;selected=button.dataset.code;detailDay=$('#day').value;renderDetail();$('#detail').showModal();});
$('#detail-body').addEventListener('click',e=>{const b=e.target.closest('[data-day]');if(b){detailDay=b.dataset.day;renderDetail();}});
$('#close').onclick=()=>$('#detail').close();$('#detail').addEventListener('close',()=>selected=null);
$('#detail').addEventListener('click',e=>{if(e.target===$('#detail')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
['day','direction','search'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',render));$('#refresh').onclick=refresh;
clock();refresh();setInterval(clock,1000);setInterval(refresh,60000);setInterval(()=>{if(state&&!loading)render();},30000);
