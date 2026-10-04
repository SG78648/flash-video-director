/* editor-play.js - playback of the edit (video from the render + every audio clip scheduled in WebAudio),
   the editing commands and the keyboard shortcuts. */

const EDP = (() => {
  let ac = null, nodes = [], T0 = 0, wall0 = 0, playing = false, timer = 0, raf = 0, curVid = null, duckG = null;
  const bufs = new Map();
  const vEl = () => $('#tlVideo');

  const lin = db => Math.pow(10, db / 20);
  function ctx(){ if(!ac) ac = new (window.AudioContext || window.webkitAudioContext)(); if(ac.state === 'suspended') ac.resume(); return ac; }
  function buffer(src){
    const url = EDUI.srcUrl(src);
    if(!bufs.has(url)) bufs.set(url, fetch(url).then(r => r.arrayBuffer()).then(b => ctx().decodeAudioData(b)).catch(() => null));
    return bufs.get(url);
  }
  function preload(){ const seen = new Set(); for(const a of ED.C.aud){ const u = EDUI.srcUrl(a.src); if(!seen.has(u)){ seen.add(u); buffer(a.src); } } }

  function stopAudio(){
    for(const n of nodes){ try{ n.stop && n.stop(); }catch(e){} try{ n.disconnect(); }catch(e){} }
    nodes = [];
  }
  async function startAudio(from, t0){
    const c = ctx(); stopAudio();
    const bus = {}; const master = c.createGain(); master.connect(c.destination); nodes.push(master);
    for(const b of ['narration', 'sfx', 'music']){ bus[b] = c.createGain(); nodes.push(bus[b]); }
    bus.narration.connect(master); bus.sfx.connect(master);
    duckG = c.createGain(); nodes.push(duckG); bus.music.connect(duckG); duckG.connect(master);
    const items = ED.C.aud.filter(a => !a.mute && a.start + a.dur > from + 0.001);
    // ducking: the music bus dips while a voice clip plays
    const dl = lin(-(ED.edit.duck_db || 0));
    duckG.gain.setValueAtTime(1, t0);
    if(dl < 0.999){
      const voices = ED.C.aud.filter(a => a.bus === 'narration' && !a.mute && a.start + a.dur > from).sort((p, q) => p.start - q.start);
      for(const v of voices){
        const on = t0 + Math.max(0, v.start - from) - 0.05, off = t0 + (v.start + v.dur - from) + 0.15;
        duckG.gain.setTargetAtTime(dl, Math.max(t0, on), 0.04); duckG.gain.setTargetAtTime(1, Math.max(t0, off), 0.3);
      }
    }
    await Promise.all(items.map(async a => {
      const buf = await buffer(a.src); if(!buf || !playing) return;
      const el = Math.max(0, from - a.start), when = t0 + Math.max(0, a.start - from);
      const g = c.createGain(), base = lin(a.gain_db);
      let v0 = base;
      if(a.fade_in > 0 && el < a.fade_in) v0 = base * (el / a.fade_in);
      g.gain.setValueAtTime(v0, when);
      if(a.fade_in > 0 && el < a.fade_in) g.gain.linearRampToValueAtTime(base, when + (a.fade_in - el));
      if(a.fade_out > 0){
        const fs = when + (a.dur - el) - a.fade_out; if(fs > when - 0.001){ g.gain.setValueAtTime(base, Math.max(when, fs)); g.gain.linearRampToValueAtTime(0, when + (a.dur - el)); }
      }
      const s = c.createBufferSource(); s.buffer = buf; s.playbackRate.value = a.speed || 1;
      s.connect(g); g.connect(bus[a.bus] || bus.sfx);
      const off = a.in + el * (a.speed || 1), len = Math.max(0.01, a.out - off);
      try{ s.start(when, Math.min(off, buf.duration - 0.001), len); }catch(e){ return; }
      nodes.push(s, g);
    }));
  }

  /* ---- the picture: the render, played clip by clip ---- */
  function showFrame(t, force){
    const v = vEl(); if(!ED.prog || !ED.prog.video || !v) return;
    const c = clipAt(t); if(!c) return;
    const want = c.kind === 'freeze' ? c.at : c.in + (t - c.start) * c.sp;
    $('#phone').classList.add('vid-on');
    if(!playing){ if(force || Math.abs(v.currentTime - want) > 0.02){ try{ v.currentTime = want; }catch(e){} } v.pause(); return; }
    if(c.kind === 'freeze'){ if(curVid !== c.id){ v.pause(); try{ v.currentTime = c.at; }catch(e){} } curVid = c.id; return; }
    const rate = c.sp;
    if(curVid !== c.id || Math.abs(v.currentTime - want) > 0.25){
      try{ v.currentTime = want; }catch(e){} curVid = c.id;
    }
    if(v.playbackRate !== rate) v.playbackRate = rate;
    if(v.paused) v.play().catch(() => {});
  }
  function clipAt(t){ const C = ED.C; return C.vid.find(v => t >= v.start && t < v.start + v.dur) || C.vid[C.vid.length - 1]; }

  const nowT = () => T0 + (performance.now() - wall0) / 1000;
  function setHead(t){
    ED.t = Math.max(0, Math.min(ED.C.total, t));
    EDUI.setHead(); $('#tlTime').textContent = fmtT(ED.t) + ' / ' + fmtT(ED.C.total);
    if(typeof renderCaptions === 'function') renderCaptions();
    if(typeof updateCaption === 'function') updateCaption();
  }
  function tick(){
    if(!playing) return;
    const t = nowT();
    if(t >= ED.C.total){ setHead(ED.C.total); pause(); return; }
    setHead(t);
    if(ED.prog.video) showFrame(t, false); else if(typeof requestPreview === 'function') requestPreview();
    const sc = EDUI.scrollEl, hx = EDUI.X(t);
    if(hx > sc.scrollLeft + sc.clientWidth - 60 || hx < sc.scrollLeft + 92) sc.scrollLeft = Math.max(0, hx - 160);
  }
  function loop(){ if(!playing) return; tick(); raf = requestAnimationFrame(loop); }

  async function play(){
    if(playing || !ED.C) return;
    if(ED.t >= ED.C.total - 0.05) setHead(0);
    const c = ctx(); playing = true; curVid = null;
    $('#tlPlay').innerHTML = ICON.pause; $('#phone').classList.toggle('vid-on', !!ED.prog.video); updateChip();
    T0 = ED.t; wall0 = performance.now() + 60;
    startAudio(T0, c.currentTime + 0.06);
    raf = requestAnimationFrame(loop); timer = setInterval(tick, 60);     // the timer keeps going when the pane is hidden
  }
  function pause(){
    if(!playing) return; playing = false; clearInterval(timer); cancelAnimationFrame(raf); stopAudio();
    const v = vEl(); if(v) v.pause();
    $('#tlPlay').innerHTML = ICON.play; updateChip(); showFrame(ED.t, true);
  }
  function seek(t){
    t = Math.max(0, Math.min(ED.C.total, t)); setHead(t);
    if(playing){ T0 = t; wall0 = performance.now() + 30; curVid = null; startAudio(t, ctx().currentTime + 0.03); showFrame(t, true); }
    else if(ED.prog && ED.prog.video) showFrame(t, true);
    else if(typeof requestPreview === 'function') requestPreview();
  }
  function updateChip(){
    const chip = $('#modeChip'); if(!chip) return;
    chip.classList.toggle('render', playing && !!ED.prog.video);
    chip.querySelector('span').textContent = !playing ? 'Live preview' : ED.prog.video ? 'Edit · last render' : 'Draft playback';
  }
  return {play, pause, seek, preload, showFrame, setHead, get playing(){ return playing; }, updateChip, ctx};
})();

/* ------------------------------------------------------------------ commands */
const Editor = (() => {
  function selResolved(){ return ED.sel.map(k => EDUI.resolve(k)).filter(Boolean); }

  async function load(){
    const st = style, asp = curAspect();
    let P;
    try{ P = await api('/api/program?style=' + st + '&aspect=' + encodeURIComponent(asp)); }
    catch(e){ if(st === style) $('#tlInner').innerHTML = '<div class="hint" style="padding:16px">Timeline unavailable: ' + (e.message || e) + '</div>'; return; }
    if(st !== style || asp !== curAspect()) return;
    let saved = null; try{ saved = (await api('/api/edit?style=' + st)).edit; }catch(e){}
    if(saved && saved.sig && saved.sig !== sigOf(P)){
      const fresh = await sheet({title: 'The video changed since this edit was made', text: 'The narration or its timing is different now, so your cuts may not line up with the picture. Start over, or keep the edit and fix it by hand.', ok: 'Start over', danger: true});
      if(fresh) saved = null;
    }
    ED.prog = P; if(typeof TL !== 'undefined') TL.prog = P;
    const legacy = !saved && cfg.music && cfg.music.file && cfg.music.enabled;
    ED.edit = normalizeEdit(saved, P);
    if(!saved && !legacy) ED.edit = defaultEdit(P);
    if(legacy){ ED.edit = defaultEdit(P, cfg.music); cfg.music.file = ''; saveState(); saveEdit(); }
    ED.sel = []; ED.undo = []; ED.redo = [];
    recompile();
    const v = $('#tlVideo');
    if(P.video && v.getAttribute('data-src') !== P.video){ v.setAttribute('data-src', P.video); v.src = P.video; v.muted = true; }
    if(!P.video){ v.removeAttribute('src'); v.removeAttribute('data-src'); }
    EDUI.Thumbs.setSource(P.video);
    if(!ED.inited){ const s = P.segments[1] || P.segments[0]; ED.t = Math.min(s.start + 1.5, s.end - 0.1); ED.inited = true; }
    ED.t = Math.min(ED.t, ED.C.total);
    fit(true); EDUI.refresh(); EDP.setHead(ED.t); EDP.preload();
    requestAnimationFrame(() => { if(ED.autoFit && ED.C){ fit(); } });     // once the layout has settled
    $('#phone').classList.toggle('vid-on', !!P.video); EDP.showFrame(ED.t, true);
    if(typeof requestPreview === 'function' && !P.video) requestPreview();
  }

  function fit(silent){
    const w = Math.max(400, EDUI.scrollEl.clientWidth) - 92 - 40;
    ED.pps = Math.max(3, Math.min(120, w / Math.max(5, ED.C.total))); ED.autoFit = true; $('#tlZoom').value = ED.pps; paintRange($('#tlZoom'));
    if(!silent) EDUI.refresh({keepSel: true});
  }
  function zoomBy(f, clientX){
    const sc = EDUI.scrollEl, rect = sc.getBoundingClientRect(), ax = (clientX ?? (rect.left + rect.width / 2)) - rect.left;
    const tAnchor = (sc.scrollLeft + ax - 92) / ED.pps;
    ED.pps = Math.max(3, Math.min(120, ED.pps * f)); ED.autoFit = false; $('#tlZoom').value = ED.pps; paintRange($('#tlZoom'));
    EDUI.refresh({keepSel: true}); sc.scrollLeft = Math.max(0, tAnchor * ED.pps + 92 - ax);
  }
  function setZoom(v){ ED.pps = v; ED.autoFit = false; EDUI.refresh({keepSel: true}); }

  function split(){
    const t = ED.t, sel = selResolved();
    const did = mutate(e => {
      const C = ED.C; let any = false;
      const picks = sel.length ? sel : null;
      if(!picks || picks.some(s => s.type === 'video')){ any = opSplitVideo(e, C, t) || any; }
      if(!picks){ any = opSplitFree(e, t, null) || any; }
      else {
        const ids = picks.filter(s => s.type === 'free').map(s => s.obj.id); if(ids.length) any = opSplitFree(e, t, ids) || any;
        for(const s of picks.filter(s => s.type === 'piece')){
          const p = s.view, base = p.b0 + (t - p.start) * p.speed;
          if(t > p.start + 0.02 && t < p.start + p.dur - 0.02){ const o = (e.stems[p.stem] = e.stems[p.stem] || {}); o.cuts = (o.cuts || []).concat([R3(base)]); any = true; }
        }
      }
      return any;
    });
    if(!did) toast('Nothing to split at the playhead');
  }

  function deleteSel(){
    const sel = selResolved(); if(!sel.length) return;
    const vids = sel.filter(s => s.type === 'video').map(s => s.obj.id);
    if(vids.length >= ED.edit.video.length){ toast('Keep at least one video clip'); return; }
    mutate(e => {
      for(const id of vids){ const C = compile(e, ED.prog), i = e.video.findIndex(c => c.id === id); if(i >= 0) opDeleteVideo(e, C, i, ED.ripple); }
      for(const s of sel){
        if(s.type === 'piece'){ const o = (e.stems[s.view.stem] = e.stems[s.view.stem] || {}); o.gone = (o.gone || []).concat([[R3(s.view.b0), R3(s.view.b1)]]); }
        else if(s.type === 'free') e.free = e.free.filter(f => f.id !== s.obj.id);
        else if(s.type === 'marker') e.markers = e.markers.filter(m => m.id !== s.obj.id);
      }
    });
    ED.sel = []; EDUI.refresh();
  }

  function duplicate(){
    const sel = selResolved(); if(!sel.length) return; const made = [];
    mutate(e => {
      for(const s of sel){
        if(s.type === 'video'){
          const C = compile(e, ED.prog), i = e.video.findIndex(c => c.id === s.obj.id); if(i < 0) continue;
          const copy = Object.assign({}, e.video[i], {id: newId('v')}); e.video.splice(i + 1, 0, copy); made.push('v:' + copy.id);
          const c = C.vid[i]; if(ED.ripple) e.free = rippleFree(e.free, c.start + c.dur, c.dur);
        } else if(s.type === 'free'){
          const f = Object.assign({}, s.obj, {id: newId('f'), start: R3(s.obj.start + s.view.dur)}); e.free.push(f); made.push('f:' + f.id);
        } else if(s.type === 'piece'){
          const tmp = clone(e); const f = opDetach(tmp, s.view); const keep = tmp.free[tmp.free.length - 1];
          const cp = Object.assign({}, keep, {id: newId('f'), start: R3(s.view.start + s.view.dur + 0.05)}); e.free.push(cp); made.push('f:' + cp.id);
        }
      }
    });
    EDUI.select(made);
  }

  function freeze(){
    mutate(e => {
      const C = ED.C, t = ED.t, at = tlToBase(t); let i = vidIndexAt(C, t);
      if(i >= 0){ opSplitVideo(e, C, t); i += 1; }
      else { i = C.vid.findIndex(c => c.start >= t - 0.02); if(i < 0) i = e.video.length; }
      e.video.splice(i, 0, {id: newId('v'), type: 'freeze', at: R3(at), dur: 1.0});
      if(ED.ripple) e.free = rippleFree(e.free, t, 1.0);
    });
  }

  function marker(){ mutate(e => opAddMarker(e, ED.t)); }

  async function addMedia(m, t){
    t = t == null ? ED.t : t;
    try{
      if(m.kind === 'music' && !LIB.music.project.some(x => x.name === m.name)){ const r = await api('/api/music/import', {name: m.name}); LIB.music.project = r.project; LIB.music.library = r.library; renderLibraries(); }
      if(m.kind === 'sfx' && !LIB.sfx.project.some(x => x.name === m.name)){ const r = await api('/api/sfx/import', {name: m.name}); LIB.sfx = r; renderLibraries(); }
    }catch(e){ toast(e.message); return; }
    const dur = m.dur || EDUI.fileDur({type: m.kind, name: m.name});
    const f = {id: newId('f'), track: m.kind === 'music' ? 'music' : 'sfx', kind: m.kind, name: m.name, start: R3(Math.max(0, t)), in: 0, out: R3(dur),
               gain: m.kind === 'music' ? -12 : m.kind === 'builtin' ? -12 : -10, fi: m.kind === 'music' ? 1 : 0, fo: m.kind === 'music' ? 2 : 0, mute: false, speed: 1, loop: false, span: 0};
    mutate(e => { e.free.push(f); });
    EDUI.select(['f:' + f.id]); EDP.preload();
  }

  async function exportEdit(){
    const b = $('#edExport'); b.disabled = true;
    try{ await api('/api/edit/export', {style, config: cfg, compiled: exportPayload()}); toast('Exporting your edit…'); pollRender(); }
    catch(e){ toast(e.message); }
    b.disabled = false;
  }

  return {load, fit, zoomBy, setZoom, split, deleteSel, duplicate, freeze, marker, addMedia, exportEdit};
})();
window.loadProgram = Editor.load;                    // the app calls it whenever the style, format, project or render changes

/* ------------------------------------------------------------------ wiring */
function initEditorUI(){
  EDUI.init();
  const on = (id, fn) => { const e = $(id); if(e) e.onclick = fn; };
  on('#tlPlay', () => EDP.playing ? EDP.pause() : EDP.play());
  on('#tlStart', () => { EDP.seek(0); EDUI.scrollEl.scrollLeft = 0; });
  on('#edUndo', undo); on('#edRedo', redo); on('#edSplit', Editor.split); on('#edDelete', Editor.deleteSel); on('#edDup', Editor.duplicate);
  on('#edFreeze', Editor.freeze); on('#edMarker', Editor.marker); on('#edExport', Editor.exportEdit); on('#tlFit', () => Editor.fit());
  on('#edRipple', () => { ED.ripple = !ED.ripple; $('#edRipple').classList.toggle('on', ED.ripple); });
  $('#edRipple').classList.toggle('on', ED.ripple);
  $('#tlSnap').onchange = e => { ED.snap = e.target.checked; };
  $('#tlZoom').oninput = e => { Editor.setZoom(parseFloat(e.target.value)); paintRange(e.target); };
  on('#dockToggle', () => setDock(!$('#app').classList.contains('collapsed')));
  // resizable dock
  const grip = $('#dockGrip');
  grip.addEventListener('pointerdown', e => {
    e.preventDefault(); const startY = e.clientY, startH = $('#dock').getBoundingClientRect().height;
    const mv = ev => { const h = Math.max(210, Math.min(window.innerHeight * 0.72, startH + (startY - ev.clientY))); document.documentElement.style.setProperty('--dock', h + 'px'); store.set('dockh', Math.round(h)); };
    const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); if(ED.autoFit) Editor.fit(); };
    window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
  });
  const h = parseInt(store.get('dockh')); if(h) document.documentElement.style.setProperty('--dock', h + 'px');
}

function setDock(collapsed){
  $('#app').classList.toggle('collapsed', collapsed); store.set('dock', collapsed ? '1' : '0');
  $('#dockIcon').innerHTML = collapsed ? '<path d="M6 9l6 6 6-6"/>' : '<path d="M6 15l6-6 6 6"/>';
  if(!collapsed && ED.C) setTimeout(() => { if(ED.autoFit) Editor.fit(); }, 30);
}

document.addEventListener('keydown', e => {
  if(e.altKey) return;
  if(e.key === 'Escape'){ if($('#viewerVeil').classList.contains('on')) closeViewer(); else if(ED.projOpen) EDUI.closeProjectPanel(); else if(ED.sel.length) EDUI.select([]); return; }
  if($('.veil.on')) return;
  const tag = document.activeElement.tagName, typing = /INPUT|SELECT|TEXTAREA/.test(tag) && document.activeElement.type !== 'range';
  if(typing) return;
  const mod = e.ctrlKey || e.metaKey;
  if(mod && !e.shiftKey && e.key.toLowerCase() === 'z'){ e.preventDefault(); undo(); return; }
  if(mod && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))){ e.preventDefault(); redo(); return; }
  if(mod && e.key.toLowerCase() === 'd'){ e.preventDefault(); Editor.duplicate(); return; }
  if(mod && e.key.toLowerCase() === 'a'){ e.preventDefault(); EDUI.select(Array.from(EDUI.els.keys())); return; }
  if(mod) return;
  if(e.code === 'Space' && tag !== 'BUTTON'){ e.preventDefault(); $('#tlPlay').click(); return; }
  const k = e.key.toLowerCase();
  if(e.key === 'Delete' || e.key === 'Backspace'){ e.preventDefault(); Editor.deleteSel(); }
  else if(k === 's'){ e.preventDefault(); Editor.split(); }
  else if(k === 'f'){ e.preventDefault(); Editor.freeze(); }
  else if(k === 'm'){ e.preventDefault(); Editor.marker(); }
  else if(e.key === 'ArrowRight'){ e.preventDefault(); EDP.seek(ED.t + (e.shiftKey ? 5 : 1 / 24 * 4)); }
  else if(e.key === 'ArrowLeft'){ e.preventDefault(); EDP.seek(ED.t - (e.shiftKey ? 5 : 1 / 24 * 4)); }
  else if(e.key === 'Home'){ e.preventDefault(); $('#tlStart').click(); }
  else if(k === 't'){ $('#dockToggle').click(); }
  else if(k === 'r'){ $('#renderBtn').click(); }
});
