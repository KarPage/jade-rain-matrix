const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
let mode = STATE.mode, savedMode = mode, activeProfile = STATE.profile, busy = false;
let drafts = clone(STATE.forms), saved = clone(drafts);
const preview = new RainPreview($('preview'));
let previewTimer = 0, previewGeneration = 0, previewAbort;
const fields = {phrases:'phrases',mix:'mix',glyph_set:'glyph',glyphs:'glyphs',color_preset:'preset',
  primary:'primary',highlight:'highlight',background:'background',logo:'logo',logo_style:'logo-style',
  logo_size:'logo-size',logo_opacity:'logo-opacity',density:'density',speed:'speed',text_mode:'text-mode'};
const numeric = new Set(['mix','logo_size','logo_opacity','density','speed']);
function readForm() {
  const form = Object.assign({}, drafts[mode]);
  for (const [key,id] of Object.entries(fields)) form[key] = numeric.has(key) ? Number($(id).value) : $(id).value;
  return form;
}
function writeForm(form) {
  for (const [key,id] of Object.entries(fields)) $(id).value = form[key] ?? '';
  updateColors(); updateLogo();
  for (const button of document.querySelectorAll('[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  for (const [id,key] of [['mix','mix'],['logo-size','logo_size'],['logo-opacity','logo_opacity'],['density','density'],['speed','speed']]) {
    // Don't display raw numbers; native keyboard/assistive controls still work.
    const el = $(id), low = Number(el.min), high = Number(el.max), value = Number(form[key]);
    const ends = {mix:['Rarely','Often'],logo_size:['Small','Large'],logo_opacity:['Faint','Bold'],density:['Calm','Busy'],speed:['Slow','Fast']}[key];
    el.setAttribute('aria-valuetext', value <= low ? ends[0] : value >= high ? ends[1] : 'Between ' + ends[0].toLowerCase() + ' and ' + ends[1].toLowerCase());
  }
}
function dirtyModes() { return Object.keys(drafts).filter(m => JSON.stringify(drafts[m]) !== JSON.stringify(saved[m])); }
function hasChanges() { return dirtyModes().length > 0 || mode !== savedMode || $('new-profile').value.trim() !== ''; }
function say(message, error=false) { $('status').textContent = message; $('status').dataset.error = String(error); }
function changed() {
  drafts[mode] = readForm();
  say(hasChanges() ? 'Unsaved changes' : 'No unsaved changes');
  updateColors(); updateLogo(); schedulePreview();
}
function colorHex(value) {
  let hex = value.trim().replace(/^#/, '');
  if (/^[\da-f]{3}$/i.test(hex)) hex = [...hex].map(c=>c+c).join('');
  return /^[\da-f]{6}$/i.test(hex) ? '#' + hex : null;
}
function validColors() {
  let valid = true;
  for (const id of ['primary','highlight','background']) {
    const ok = !$(id).value.trim() || colorHex($(id).value);
    $(id).setCustomValidity(ok ? '' : 'Use a hex color such as #3fe0a4, or leave blank for automatic.');
    valid &&= Boolean(ok);
  }
  return valid;
}
function updateColors(scene = preview.scene?.mode === mode ? preview.scene : null) {
  const custom = $('preset').value !== 'theme' || ['primary','highlight','background'].some(id=>$(id).value.trim());
  $('theme-colors').setAttribute('aria-pressed', String(!custom));
  $('custom-colors').setAttribute('aria-pressed', String(custom));
  for (const [id,index,fallback] of [['primary',2,'#3fe0a4'],['highlight',0,'#e9fff6']]) {
    const resolved = scene ? '#' + scene.ramp[index].map(v=>Math.min(255,Math.max(0,Math.round(v))).toString(16).padStart(2,'0')).join('') : fallback;
    $(id+'-pick').value = colorHex($(id).value) || resolved;
  }
}
function updateLogo(scene) {
  const hasLogo = Boolean($('logo').value.trim());
  $('remove-logo').hidden = !hasLogo;
  $('logo-caption').textContent = hasLogo ? 'Change your logo' : 'Choose a logo or drop it here';
  if (!hasLogo) { $('logo-empty').hidden = false; $('logo-thumb').hidden = true; $('logo-message').textContent = ''; }
  if (hasLogo && scene && (scene.logos.length || scene.logoSprite)) {
    const mark = scene.logos[0] || scene.logoSprite, [sx,sy,w,h] = scene.boxes[mark.id];
    const canvas = document.createElement('canvas'); canvas.width=w; canvas.height=h;
    const ctx = canvas.getContext('2d'); ctx.drawImage(preview.atlas,sx,sy,w,h,0,0,w,h);
    ctx.globalCompositeOperation='source-in'; ctx.fillStyle='#3fe0a4'; ctx.fillRect(0,0,w,h);
    $('logo-thumb').src = canvas.toDataURL(); $('logo-thumb').hidden=false; $('logo-empty').hidden=true;
  }
}
function payload(extra={}) { return Object.assign({token:STATE.token,profile:$('profile').value,
  new_profile:$('new-profile').value.trim(),mode,form:readForm()},extra); }
async function post(path, extra={}, signal) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(payload(extra)),signal});
  let body;
  try { body = await response.json(); } catch { throw new Error('The editor did not respond. Reopen settings and try again.'); }
  if (!response.ok || body.ok === false) throw new Error(body.error || 'That did not work. Please try again.');
  return body;
}
function schedulePreview() {
  const generation = ++previewGeneration;
  clearTimeout(previewTimer); previewAbort?.abort();
  if (!validColors()) { $('preview-status').textContent='Finish your color to update the preview.'; return; }
  $('preview-status').textContent = 'Updating preview…';
  previewTimer = setTimeout(()=>drawPreview(generation),120);
}
async function drawPreview(generation) {
  previewAbort = new AbortController();
  try {
    const stage = document.querySelector('.preview-stage');
    const width = Math.min(840, Math.max(320,Math.round(stage.clientWidth)));
    const height = Math.max(120,Math.round(width * stage.clientHeight / Math.max(1,stage.clientWidth)));
    const scene = await post('/api/scene',{width,height},previewAbort.signal);
    if (generation !== previewGeneration) return;
    await preview.setScene(scene, () => generation === previewGeneration);
    if (generation !== previewGeneration) return;
    updateColors(scene); updateLogo(scene);
    $('preview-status').dataset.error='false';
    $('preview-status').textContent = mode === 'still' ? 'Still preview · edits appear here' : preview.motion.matches ? 'Motion reduced · edits appear here' : 'Preview only · your desktop is unchanged';
  } catch (error) {
    if (error.name === 'AbortError' || generation !== previewGeneration) return;
    $('preview-status').dataset.error='true';
    $('preview-status').textContent='Preview unavailable: ' + error.message;
  }
}
function setBusy(value) {
  busy=value;
  document.querySelectorAll('#editor button,#editor input,#editor select,#editor textarea').forEach(el=>el.disabled=value);
  $('save').textContent=value ? 'Saving…' : 'Save changes';
}
async function save(event) {
  event?.preventDefault();
  if (busy || !validColors() || !$('editor').reportValidity()) return;
  drafts[mode]=readForm();
  const forms = {};
  const copyProfile = $('new-profile').value.trim();
  for(const name of copyProfile ? Object.keys(drafts) : dirtyModes()) forms[name]=drafts[name];
  forms[mode]=drafts[mode];
  setBusy(true); say('Saving…');
  try {
    const body=await post('/api/save',{forms});
    saved=clone(drafts); savedMode=mode;
    if (!$('profile').querySelector(`option[value="${CSS.escape(body.profile)}"]`)) {
      const option=new Option(body.profile,body.profile); $('profile').append(option);
    }
    $('profile').value=body.profile; activeProfile=body.profile; $('new-profile').value='';
    say('Saved on this computer');
  } catch(error) { say('Not saved: '+error.message+' Try Save changes again.',true); }
  finally { setBusy(false); }
}
function selectMode(next) {
  if (busy || mode === next) return;
  drafts[mode]=readForm(); mode=next; writeForm(drafts[mode]);
  say(hasChanges() ? 'Unsaved changes' : 'No unsaved changes'); schedulePreview();
}
$('profile').replaceChildren(...STATE.profiles.map(name=>new Option(name,name,false,name===STATE.profile)));
writeForm(drafts[mode]);
$('editor').addEventListener('submit',save);
$('editor').addEventListener('input', event=> {
  if (['logo-file','import-path','profile'].includes(event.target.id)) return;
  if (event.target.id.endsWith('-pick')) {
    const id=event.target.id.replace('-pick',''); $(id).value=event.target.value;
  }
  changed();
});
$('editor').addEventListener('change',event=> {
  if (['preset','logo-style','glyph','text-mode'].includes(event.target.id)) {
    if (event.target.id === 'preset') ['primary','highlight','background'].forEach(id=>$(id).value='');
    changed();
  }
});
$('mode-buttons').addEventListener('click',event=> { const button=event.target.closest('[data-mode]'); if(button) selectMode(button.dataset.mode); });
$('theme-colors').addEventListener('click',()=> { $('preset').value='theme'; ['primary','highlight','background'].forEach(id=>$(id).value=''); changed(); });
$('custom-colors').addEventListener('click',()=> {
  $('primary').value=$('primary-pick').value; $('highlight').value=$('highlight-pick').value;
  changed(); $('primary-pick').focus();
});
$('profile').addEventListener('change',()=> {
  const next=$('profile').value;
  if(hasChanges() && !confirm('Discard your unsaved changes and switch profile?')) { $('profile').value=activeProfile; return; }
  const url=new URL(location.href); url.searchParams.set('profile',next); url.searchParams.set('mode',mode); saved=clone(drafts); savedMode=mode; $('new-profile').value=''; location.assign(url);
});
$('reset').addEventListener('click',async()=> {
  if(busy || !confirm('Reset '+mode+' to its default settings? Your other modes and profiles will stay as they are.')) return;
  setBusy(true); say('Resetting…');
  try { const body=await post('/api/reset'); drafts[mode]=body.form; saved[mode]=clone(body.form); savedMode=mode;
    writeForm(body.form); say(hasChanges() ? 'Mode reset · other edits are unsaved' : 'Defaults restored and saved'); schedulePreview();
  } catch(error) { say('Could not reset: '+error.message,true); }
  finally { setBusy(false); }
});
let uploading=false;
async function uploadLogo(file) {
  if(!file || uploading || busy) return;
  if(file.size>2000000 || !/\.(png|svg)$/i.test(file.name)) { say('Choose a PNG or SVG smaller than 2 MB.',true); return; }
  uploading=true; $('logo-drop').disabled=true; $('logo-message').textContent='Adding logo…';
  try {
    const bytes=new Uint8Array(await file.arrayBuffer()); let binary='';
    for(const byte of bytes) binary+=String.fromCharCode(byte);
    const body=await post('/api/logo',{name:file.name,data:btoa(binary)});
    $('logo').value=body.logo; changed(); $('logo-message').textContent='Logo added · save to keep it';
  } catch(error) { say('Logo not added: '+error.message,true); $('logo-message').textContent='Choose the file again to retry.'; }
  finally { uploading=false; $('logo-drop').disabled=false; $('logo-file').value=''; }
}
$('logo-drop').addEventListener('click',()=> $('logo-file').click());
$('logo-file').addEventListener('change',()=>uploadLogo($('logo-file').files[0]));
for(const type of ['dragenter','dragover']) $('logo-drop').addEventListener(type,event=> { event.preventDefault(); $('logo-drop').classList.add('drag'); });
$('logo-drop').addEventListener('dragleave',()=> $('logo-drop').classList.remove('drag'));
$('logo-drop').addEventListener('drop',event=> { event.preventDefault(); $('logo-drop').classList.remove('drag'); uploadLogo(event.dataTransfer.files[0]); });
$('remove-logo').addEventListener('click',()=> { $('logo').value=''; changed(); });
$('import').addEventListener('click',async()=> {
  if(busy) return;
  $('import').disabled=true; $('import').textContent='Importing…';
  try { const body=await post('/api/import',{path:$('import-path').value}); $('text-mode').value='mix'; changed(); say('Imported '+body.phrases+' phrases · save to use them'); }
  catch(error) { say('Import failed: '+error.message,true); }
  finally { $('import').disabled=false; $('import').textContent='Import'; }
});
$('pause').addEventListener('click',()=> { preview.paused=!preview.paused; preview.wake(); $('pause').textContent=preview.paused?'Play':'Pause'; $('pause').setAttribute('aria-pressed',String(preview.paused)); });
$('expand').addEventListener('click',async()=> {
  try { if(document.fullscreenElement) await document.exitFullscreen(); else await $('preview-panel').requestFullscreen(); }
  catch { $('preview-status').textContent='Full-size preview is unavailable in this browser.'; }
});
document.addEventListener('fullscreenchange',()=> { $('expand').textContent=document.fullscreenElement?'Close full-size ↙':'Expand ↗'; schedulePreview(); });
$('credit').textContent=STATE.credit; $('source-url').textContent=STATE.sourceUrl; $('source-url').href=STATE.sourceUrl;
$('source-profile').href=STATE.sourceProfile; $('version').textContent=STATE.version;
$('about').addEventListener('click',()=> $('about-panel').showModal());
$('close-about').addEventListener('click',()=> $('about-panel').close());
document.addEventListener('keydown',event=> {
  if((event.ctrlKey||event.metaKey) && event.key.toLowerCase()==='s') { event.preventDefault(); save(); return; }
  if(event.ctrlKey||event.metaKey||event.altKey || event.target.closest('input,textarea,select,button,dialog')) return;
  const next={'1':'live','2':'still','3':'light','4':'screensaver'}[event.key];
  if(next) { event.preventDefault(); selectMode(next); }
});
window.addEventListener('beforeunload',event=> { if(hasChanges()) { event.preventDefault(); event.returnValue=''; } });
let resizeTimer;
window.addEventListener('resize',()=> { clearTimeout(resizeTimer); resizeTimer=setTimeout(schedulePreview,150); });
if(location.hash==='#about') $('about-panel').showModal();
schedulePreview();
