'use strict';
const $=id=>document.getElementById(id);
let csrf='',state=null,draft=null,capStamp=null,pollTimer=null;
const nativeControls=new Map();
function notice(message,error=false){$('notice').textContent=message;$('notice').classList.toggle('error',error);$('notice').hidden=false;}
async function api(path,data){
  const response=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
  const value=await response.json();
  if(!response.ok){if(response.status===401&&path!=='login')showLogin();throw new Error(value.error||'Verbindung fehlgeschlagen.');}
  return value;
}
function showLogin(){clearTimeout(pollTimer);$('login').hidden=false;$('workspace').hidden=true;$('logout').hidden=true;}
function markDirty(){$('dirty').hidden=false;}
function fill(profile){
  draft=structuredClone(profile);
  for(const key of ['source','mode','dpi','width_mm','height_mm','jpeg_quality','blank_percent','blank_gray_threshold'])$(key).value=profile[key];
  $('paper').value=profile.width_mm===210&&profile.height_mm===297?'a4':profile.width_mm===216&&profile.height_mm===356?'legal':'custom';
  $('auto-help').hidden=profile.source!=='Auto';
  $('blank_percent').min=profile.source==='Auto'?'0.01':'0';
  $('dirty').hidden=true;renderOptions();
}
function profile(){
  const p=structuredClone(draft);
  for(const key of ['source','mode'])p[key]=$(key).value;
  for(const key of ['dpi','width_mm','height_mm','jpeg_quality','blank_percent','blank_gray_threshold'])p[key]=Number($(key).value);
  for(const [name,control] of nativeControls){
    if(!control.enabled.checked){delete p.sane_options[name];continue;}
    const input=control.input,option=control.option;
    if(option.kind==='boolean')p.sane_options[name]=input.checked;
    else if(option.kind==='vector')p.sane_options[name]=JSON.parse(input.value);
    else if(['integer','number'].includes(option.kind))p.sane_options[name]=Number(input.value);
    else p.sane_options[name]=input.value;
  }
  return p;
}
function renderOptions(){
  nativeControls.clear();$('native-options').replaceChildren();$('image-options').replaceChildren();
  if(!state?.capabilities?.options){$('cap-note').textContent='Noch keine Geräteoptionen. Scanner aufklappen und aktualisieren.';return;}
  const caps=state.capabilities;
  const same=caps.profile.source===$('source').value&&caps.profile.mode===$('mode').value;
  $('cap-note').textContent=same?'Optionen vom Scanner geladen. Bereiche gelten für den abgefragten Modus.':'Modus geändert: Geräteoptionen bitte aktualisieren.';
  for(const option of caps.options){
    if(['source','mode','resolution','page-width','page-height','tl-x','tl-y','br-x','br-y','swskip','batch-scan','side'].includes(option.name))continue;
    const row=document.createElement('div');row.className='option';
    row.dataset.search=(option.name+' '+option.title+' '+option.description).toLowerCase();
    const head=document.createElement('div');head.className='option-head';
    const label=document.createElement('label');label.textContent=option.title||option.name;
    const name=document.createElement('span');name.className='native-name';name.textContent=option.name;label.append(name);head.append(label);
    const enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=Object.hasOwn(draft.sane_options,option.name);
    const toggle=document.createElement('label');toggle.className='toggle';toggle.append(enabled,document.createTextNode('Anpassen'));head.append(toggle);row.append(head);
    const current=enabled.checked?draft.sane_options[option.name]:option.value;
    let input;
    if(option.choices&&option.kind!=='vector'){
      input=document.createElement('select');for(const value of option.choices){const item=document.createElement('option');item.value=value;item.textContent=value;input.append(item);}input.value=current;
    }else if(option.kind==='boolean'){input=document.createElement('input');input.type='checkbox';input.checked=Boolean(current);}
    else if(option.kind==='vector'){input=document.createElement('textarea');input.value=JSON.stringify(current||[]);}
    else{input=document.createElement('input');input.type=['integer','number'].includes(option.kind)?'number':'text';input.value=current??'';if(input.type==='number'){input.step=option.range?.[2]||'any';if(option.range){input.min=option.range[0];input.max=option.range[1];}}}
    input.id='native-'+option.name;input.className='value';label.htmlFor=input.id;
    enabled.setAttribute('aria-label',(option.title||option.name)+' anpassen');
    const available=option.editable&&option.active;
    enabled.disabled=!available;input.disabled=!available||!enabled.checked;
    if(!available){row.classList.add('unavailable');toggle.replaceChildren(document.createTextNode(option.active?'Nur Anzeige':'Im Modus nicht verfügbar'));}
    else{enabled.addEventListener('change',()=>{input.disabled=!enabled.checked;markDirty();});input.addEventListener('input',markDirty);nativeControls.set(option.name,{enabled,input,option});}
    row.append(input);const description=document.createElement('p');description.className='description';description.textContent=option.description||'';row.append(description);
    (['brightness','contrast','gamma'].includes(option.name)?$('image-options'):$('native-options')).append(row);
  }
  filterOptions();
}
function filterOptions(){const query=$('option-search').value.toLowerCase();for(const row of $('native-options').children)row.hidden=!row.dataset.search.includes(query);}
async function refreshState(){
  state=await api('state');const worker=state.worker;
  const titles={ready:'Scanner bereit',scanning:'Dein Stapel wird gescannt',checking:'Einstellungen werden geprüft',offline:'Scanner nicht bereit'};
  $('status-title').textContent=titles[worker.state]||worker.state;$('status-message').textContent=worker.message;
  $('status-dot').className='dot '+worker.state;
  $('scan').disabled=worker.state!=='ready'||state.queued;$('scan').firstChild.textContent=state.queued?'Start wird übernommen … ':worker.state==='scanning'?'Scan läuft … ':'Scan starten ';
  $('free-space').textContent=(state.free_mb/1024).toFixed(1)+' GB frei';
  for(const key of ['pending','submitted','sent'])$('count-'+key).textContent=state.jobs[key]||0;
  $('count-review').textContent=['failed','uncertain','interrupted'].reduce((sum,key)=>sum+(state.jobs[key]||0),0);
  const selected=$('profiles').value;const names=Object.keys(state.settings.profiles);
  if(JSON.stringify(Array.from($('profiles').options,o=>o.value))!==JSON.stringify(names)){
    $('profiles').replaceChildren();for(const name of names){const item=document.createElement('option');item.value=name;item.textContent=name;$('profiles').append(item);}
    $('profiles').value=names.includes(selected)?selected:state.settings.active;
  }
  $('active-profile').textContent='Blaue Taste: '+state.settings.active;
  if(!draft){$('profiles').value=state.settings.active;$('profile-name').value=state.settings.active;fill(state.settings.profiles[state.settings.active]);}
  if(capStamp!==state.capabilities.updated){capStamp=state.capabilities.updated;const current=profile();draft=current;renderOptions();}
}
async function poll(){try{await refreshState();}catch(error){notice(error.message,true);}finally{if(!$('workspace').hidden)pollTimer=setTimeout(poll,2500);}}
async function loggedIn(){$('login').hidden=true;$('workspace').hidden=false;$('logout').hidden=false;draft=null;await poll();}
async function perform(action){try{await action();}catch(error){notice(error.message,true);}}
$('login-form').addEventListener('submit',event=>{event.preventDefault();perform(async()=>{const result=await api('login',{password:$('password').value});csrf=result.csrf;$('password').value='';$('notice').hidden=true;await loggedIn();});});
$('logout').addEventListener('click',()=>perform(async()=>{await api('logout',{});showLogin();const session=await api('session');csrf=session.csrf;}));
$('settings-form').addEventListener('input',event=>{if(event.target.id!=='option-search')markDirty();});
$('settings-form').addEventListener('submit',event=>{event.preventDefault();perform(async()=>{const p=profile();await api('profile',{name:$('profile-name').value,profile:p});draft=p;$('dirty').hidden=true;notice('Profil gespeichert. Die blaue Taste nutzt jetzt diese Einstellungen.');await refreshState();$('profiles').value=$('profile-name').value;});});
$('profiles').addEventListener('change',()=>{$('profile-name').value=$('profiles').value;fill(state.settings.profiles[$('profiles').value]);});
$('activate').addEventListener('click',()=>perform(async()=>{await api('activate',{name:$('profiles').value});notice('Profil für die blaue Taste aktiviert.');await refreshState();}));
$('paper').addEventListener('change',()=>{const size={a4:[210,297],legal:[216,356]}[$('paper').value];if(size){$('width_mm').value=size[0];$('height_mm').value=size[1];}});
for(const id of ['source','mode'])$(id).addEventListener('change',()=>{
  $('cap-note').textContent='Modus geändert. Geräteoptionen bitte aktualisieren.';
  const auto=$('source').value==='Auto';$('auto-help').hidden=!auto;$('blank_percent').min=auto?'0.01':'0';
  if(auto&&Number($('blank_percent').value)<=0)$('blank_percent').value='0.1';
});
for(const id of ['width_mm','height_mm'])$(id).addEventListener('input',()=>{$('paper').value='custom';});
$('scan').addEventListener('click',()=>perform(async()=>{if(!$('settings-form').reportValidity())return;$('scan').disabled=true;await api('scan',{profile:profile()});notice('Scanstart angefordert. Papierdurchlauf abwarten; der Upload folgt automatisch.');await refreshState();}));
$('refresh').addEventListener('click',()=>perform(async()=>{await api('refresh',{profile:profile()});notice('Geräteoptionen werden neu abgefragt. Einen Moment bitte.');}));
$('reset-options').addEventListener('click',()=>{draft=profile();draft.sane_options={};renderOptions();markDirty();notice('Zusatzoptionen zurückgesetzt. Speichern oder Geräteoptionen neu abfragen.');});
$('option-search').addEventListener('input',filterOptions);
perform(async()=>{const session=await api('session');csrf=session.csrf;if(session.authenticated)await loggedIn();else showLogin();});
