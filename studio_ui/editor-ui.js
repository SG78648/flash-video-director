/* editor-ui.js - the timeline: lanes, clips, selection, dragging, trimming, the inspector and the shortcuts. */

const EDUI = (() => {
  const LABEL_W = 92;
  const ROWS = {video: 52, narration: 34, sfx: 20, music: 34, text: 22, overlay: 26};
  const GAPY = 4;
  let inner, scroll, labels, head;
  const els = new Map();            // clip key -> element
  let lanes = null;                 // geometry of the lanes after the last layout
  let waves = {};                   // url -> Promise({peaks, per_sec, duration})
  const durOf = {};                 // audio duration by source (filled when peaks arrive / from the libraries)

  const X = t => LABEL_W + t * ED.pps;
  const T = x => (x - LABEL_W) / ED.pps;

  /* ------------------------------------------------------------ helpers */
  function srcUrl(src){
    if(src.type === 'narration') return '/stem?path=' + encodeURIComponent(src.path);
    if(src.type === 'builtin') return '/builtin/' + encodeURIComponent(src.name) + '.wav';
    if(src.type === 'sfx') return '/sfx/' + encodeURIComponent(src.name) + '.flac';
    return '/music/' + encodeURIComponent(src.name) + '.flac';
  }
  function waveUrl(src){
    if(src.type === 'narration') return '/api/waveform?kind=file&path=' + encodeURIComponent(src.path);
    return '/api/waveform?kind=' + src.type + '&name=' + encodeURIComponent(src.name);
  }
  function peaksFor(src){
    const u = waveUrl(src);
    if(!waves[u]) waves[u] = api(u).then(w => { durOf[srcUrl(src)] = w.duration; return w; });
    return waves[u];
  }
  function fileDur(src){
    if(src.type === 'text' || src.type === 'image') return 600;
    const u = srcUrl(src); if(durOf[u]) return durOf[u];
    const lists = (typeof LIB !== 'undefined') ? LIB : null;
    if(lists){
      const pool = src.type === 'music' ? lists.music.project : src.type === 'sfx' ? lists.sfx.project : src.type === 'builtin' ? lists.sfx.builtin : [];
      const f = pool.find(x => x.name === src.name); if(f) return f.duration;
    }
    return 600;
  }
  function drawWave(cv, peaks, per, t0, t1, color){
    const W = cv.width, H = cv.height, ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H); ctx.fillStyle = color;
    if(!peaks || !peaks.length || t1 <= t0) return;
    for(let x = 0; x < W; x++){
      const a = t0 + (x / W) * (t1 - t0), b = t0 + ((x + 1) / W) * (t1 - t0); let m = 0;
      for(let i = Math.floor(a * per); i <= Math.floor(b * per); i++){ const v = peaks[i] || 0; if(v > m) m = v; }
      const h = Math.max(1, m * H * 0.92); ctx.fillRect(x, (H - h) / 2, 1, h);
    }
  }

  /* ------------------------------------------------------------ thumbnails of the render */
  const Thumbs = {
    cache: new Map(), queue: [], busy: false, vid: null, src: null, h: 48,
    setSource(url){
      if(this.src === url) return; this.src = url; this.cache.clear(); this.queue = []; this.vid = null;
      if(!url) return;
      const v = document.createElement('video'); v.muted = true; v.preload = 'auto'; v.src = url; this.vid = v;
    },
    key: bt => Math.round(bt * 2) / 2,
    get(bt){ return this.cache.get(this.key(bt)); },
    want(bt, el){
      const k = this.key(bt); if(this.cache.has(k) || !this.vid) return;
      if(!this.queue.some(q => q.k === k)) this.queue.push({k, els: new Set()});
      this.queue.find(q => q.k === k).els.add(el); this.pump();
    },
    async pump(){
      if(this.busy) return; this.busy = true;
      const v = this.vid;
      while(this.queue.length && v === this.vid){
        const q = this.queue.shift();
        try{
          if(v.readyState < 1) await new Promise(r => v.addEventListener('loadedmetadata', r, {once: true}));
          await new Promise(res => { const done = () => { v.removeEventListener('seeked', done); res(); }; v.addEventListener('seeked', done); v.currentTime = Math.min(q.k, Math.max(0, (v.duration || q.k) - 0.05)); setTimeout(done, 1500); });
          const ar = (v.videoWidth || 9) / (v.videoHeight || 16), cv = document.createElement('canvas');
          cv.height = this.h; cv.width = Math.max(8, Math.round(this.h * ar)); cv.getContext('2d').drawImage(v, 0, 0, cv.width, cv.height);
          const url = cv.toDataURL('image/jpeg', 0.6); this.cache.set(q.k, url);
          q.els.forEach(el => { if(el.isConnected) el.style.backgroundImage = 'url(' + url + ')'; });
        }catch(e){}
      }
      this.busy = false;
    },
  };

  /* ------------------------------------------------------------ geometry */
  function assignRows(items){
    const sorted = items.slice().sort((a, b) => a.start - b.start), ends = [];
    for(const it of sorted){
      let r = ends.findIndex(e => e <= it.start + 0.01); if(r < 0){ r = ends.length; ends.push(0); }
      ends[r] = it.start + it.dur; it.row = r;
    }
    return Math.max(1, ends.length);
  }
  function layout(){
    const C = ED.C, out = {}, byBus = {narration: [], sfx: [], music: [], text: [], overlay: []};
    for(const p of C.pieces) byBus[p.bus].push(p);
    for(const f of C.free) (byBus[f.bus] || byBus.sfx).push(f);
    let y = 22 + GAPY;
    const trows = Math.max(1, Math.min(4, assignRows(byBus.text)));
    out.text = {top: y, rows: trows, h: trows * ROWS.text + (trows - 1) * 2}; y += out.text.h + GAPY;
    const orows = Math.max(1, Math.min(3, assignRows(byBus.overlay)));
    out.overlay = {top: y, rows: orows, h: orows * ROWS.overlay + (orows - 1) * 2}; y += out.overlay.h + GAPY;
    out.video = {top: y, rows: 1, h: ROWS.video}; y += ROWS.video + GAPY;
    for(const bus of ['narration', 'sfx', 'music']){
      const rows = Math.max(bus === 'narration' ? 1 : 2, Math.min(5, assignRows(byBus[bus])));
      out[bus] = {top: y, rows, h: rows * ROWS[bus] + (rows - 1) * 2}; y += out[bus].h + GAPY;
    }
    out.height = y + 6; out.items = byBus;
    return out;
  }

  /* ------------------------------------------------------------ build / reconcile */
  function build(){
    if(!ED.C) return;
    const C = ED.C; lanes = layout();
    inner.style.width = (LABEL_W + C.total * ED.pps + 160) + 'px'; inner.style.height = lanes.height + 'px';
    buildLabels(); buildRuler(); buildLaneBackgrounds();
    const alive = new Set();
    // video clips
    C.vid.forEach((c, i) => { const key = 'v:' + c.id; alive.add(key); placeVideo(key, c, i); });
    // audio
    for(const bus of ['narration', 'sfx', 'music']){
      for(const it of lanes.items[bus]){
        const key = it.ref === 'free' ? it.key : 'a:' + it.key; alive.add(key); placeAudio(key, it, bus);
      }
    }
    for(const it of lanes.items.text){ alive.add(it.key); placeText(it.key, it); }
    for(const it of lanes.items.overlay){ alive.add(it.key); placeOverlay(it.key, it); }
    for(const [key, el] of els) if(!alive.has(key)){ el.remove(); els.delete(key); }
    placeHead(); applySel();
  }

  const handleW = w => Math.max(3, Math.min(11, Math.round(w / 3)));
  function el(key, cls){
    let e = els.get(key);
    if(!e){
      e = mk('clip ' + cls); e.dataset.key = key; e.innerHTML = '<span class="lab"></span><i class="h l"></i><i class="h r"></i>'; inner.appendChild(e); els.set(key, e);
    }
    return e;
  }

  function placeVideo(key, c, i){
    const e = el(key, 'vclip'), top = lanes.video.top;
    e.style.left = X(c.start) + 'px'; e.style.width = Math.max(6, c.dur * ED.pps - 2) + 'px'; e.style.top = top + 'px'; e.style.height = lanes.video.h + 'px'; e.style.setProperty('--hw', handleW(c.dur * ED.pps) + 'px');
    e.classList.toggle('freeze', c.kind === 'freeze');
    e.querySelector('.lab').textContent = (c.kind === 'freeze' ? '❄ Freeze ' + c.dur.toFixed(1) + 's' : (c.label || '') + (c.sp !== 1 ? '  · ' + c.sp + '×' : ''));
    let strip = e.querySelector('.strip');
    if(!strip){ strip = mk('strip'); e.insertBefore(strip, e.firstChild); }
    const tileW = Math.max(24, Math.round(Thumbs.h * (ED.prog ? ED.prog.w / ED.prog.h : 9 / 16))), n = Math.max(1, Math.ceil((c.dur * ED.pps) / tileW));
    const sig = n + '|' + c.id + '|' + (c.kind === 'clip' ? c.in.toFixed(2) + c.sp : c.at) + '|' + tileW;
    if(strip.dataset.sig !== sig){
      strip.dataset.sig = sig; strip.innerHTML = '';
      for(let k = 0; k < n; k++){
        const t = mk('tile'); t.style.width = tileW + 'px';
        const bt = c.kind === 'freeze' ? c.at : c.in + ((k + 0.5) * tileW / ED.pps) * c.sp;
        const u = Thumbs.get(bt); if(u) t.style.backgroundImage = 'url(' + u + ')'; else Thumbs.want(Math.min(bt, ED.prog.total - 0.05), t);
        strip.appendChild(t);
      }
    }
    e.classList.remove('lock');
  }

  function placeText(key, it){
    const e = el(key, 'tclip'), L = lanes.text;
    e.style.left = X(it.start) + 'px'; e.style.width = Math.max(6, it.dur * ED.pps - 1) + 'px'; e.style.setProperty('--hw', handleW(it.dur * ED.pps) + 'px');
    e.style.top = (L.top + (it.row || 0) * (ROWS.text + 2)) + 'px'; e.style.height = ROWS.text + 'px';
    e.classList.toggle('auto', !!(ED.edit.free.find(f => f.id === it.free) || {}).auto);
    e.querySelector('.lab').textContent = (it.text || '').replace(/\n/g, ' ') || 'Text';
  }

  function placeOverlay(key, it){
    const e = el(key, 'oclip'), L = lanes.overlay;
    e.style.left = X(it.start) + 'px'; e.style.width = Math.max(6, it.dur * ED.pps - 1) + 'px'; e.style.setProperty('--hw', handleW(it.dur * ED.pps) + 'px');
    e.style.top = (L.top + (it.row || 0) * (ROWS.overlay + 2)) + 'px'; e.style.height = ROWS.overlay + 'px';
    e.style.backgroundImage = 'url(/asset/' + encodeURIComponent(it.name) + '.png)';
    e.querySelector('.lab').textContent = it.name;
  }

  const BUSCOLOR = {narration: '#5fe08f', sfx: '#ffc14d', music: '#d9aeff'};
  function placeAudio(key, it, bus){
    const e = el(key, 'aclip ' + bus), L = lanes[bus];
    e.classList.toggle('free', it.ref === 'free'); e.classList.toggle('mute', !!it.mute); e.classList.toggle('loop', !!it.loop);
    e.style.left = X(it.start) + 'px'; e.style.width = Math.max(5, it.dur * ED.pps - 1) + 'px'; e.style.setProperty('--hw', handleW(it.dur * ED.pps) + 'px');
    e.style.top = (L.top + (it.row || 0) * (ROWS[bus] + 2)) + 'px'; e.style.height = ROWS[bus] + 'px';
    const nm = it.name && it.name.includes('/') ? it.name.split('/').pop() : it.name;
    e.querySelector('.lab').textContent = (nm || '') + (it.gain_db && it.ref === 'free' ? '' : '');
    // fade shapes
    let fi = e.querySelector('.fi'), fo = e.querySelector('.fo');
    if(!fi){ fi = mk('fade fi'); fo = mk('fade fo'); e.appendChild(fi); e.appendChild(fo); }
    fi.style.width = Math.min(it.dur, it.fade_in || 0) * ED.pps + 'px'; fo.style.width = Math.min(it.dur, it.fade_out || 0) * ED.pps + 'px';
    // waveform
    let cv = e.querySelector('canvas');
    if(!cv){ cv = document.createElement('canvas'); e.insertBefore(cv, e.firstChild); }
    const w = Math.min(6000, Math.max(6, Math.ceil(it.dur * ED.pps))), h = ROWS[bus], sig = w + '|' + it.in.toFixed(3) + '|' + it.out.toFixed(3) + '|' + it.loop + '|' + (it.one || '');
    if(cv.dataset.sig !== sig){
      cv.dataset.sig = sig; cv.width = w; cv.height = h;
      peaksFor(it.src).then(pk => {
        if(cv.dataset.sig !== sig) return;
        if(it.loop){                       // repeat the source across the block
          const one = it.one * it.speed, ctx = cv.getContext('2d'); ctx.clearRect(0, 0, w, h);
          const tmp = document.createElement('canvas'); tmp.width = Math.max(1, Math.round(one / it.speed * ED.pps)); tmp.height = h;
          drawWave(tmp, pk.peaks, pk.per_sec, it.in, it.in + one, BUSCOLOR[bus]);
          for(let x = 0; x < w; x += tmp.width) ctx.drawImage(tmp, x, 0);
        } else drawWave(cv, pk.peaks, pk.per_sec, it.in, Math.min(it.out, pk.duration), BUSCOLOR[bus]);
      }).catch(() => {});
    }
  }

  function buildLabels(){
    labels.innerHTML = ''; labels.style.height = lanes.height + 'px';
    const add = (name, top, h, id, muteable) => {
      const d = mk('lab'); d.style.cssText = `top:${top}px;height:${h}px`;
      d.innerHTML = `<span></span>` + (muteable ? `<button class="mbtn" title="Mute / unmute this track"></button>` : '');
      d.firstChild.textContent = name;
      if(muteable){ const b = d.querySelector('button'); const m = ED.edit.tracks[id].mute; b.classList.toggle('on', m); b.innerHTML = m ? ICON_MUTE : ICON_SPK; b.onclick = () => mutate(e => { e.tracks[id].mute = !e.tracks[id].mute; }); }
      labels.appendChild(d);
    };
    add('Text', lanes.text.top, lanes.text.h, 'text', false);
    add('Overlay', lanes.overlay.top, lanes.overlay.h, 'overlay', false);
    add('Video', lanes.video.top, lanes.video.h, 'video', false);
    add('Voice', lanes.narration.top, lanes.narration.h, 'narration', true);
    add('Effects', lanes.sfx.top, lanes.sfx.h, 'sfx', true);
    add('Music', lanes.music.top, lanes.music.h, 'music', true);
  }

  function buildRuler(){
    inner.querySelectorAll('.tl-tick,.mark').forEach(n => n.remove());
    const steps = [0.5, 1, 2, 5, 10, 15, 30, 60], step = steps.find(s => s * ED.pps >= 70) || 60;
    for(let t = 0; t <= ED.C.total + 0.001; t += step){ const tk = mk('tl-tick'); tk.style.left = X(t) + 'px'; tk.innerHTML = '<span>' + fmtT(t) + '</span>'; inner.appendChild(tk); }
    for(const m of ED.edit.markers){
      const d = mk('mark' + (ED.sel.includes('m:' + m.id) ? ' sel' : '')); d.dataset.key = 'm:' + m.id; d.style.left = X(m.t) + 'px'; d.title = m.text || 'Marker'; d.innerHTML = '<i></i><span></span>'; d.querySelector('span').textContent = m.text || '';
      inner.appendChild(d);
    }
  }
  function buildLaneBackgrounds(){
    inner.querySelectorAll('.tl-lane').forEach(n => n.remove());
    for(const k of ['text', 'overlay', 'video', 'narration', 'sfx', 'music']){ const d = mk('tl-lane ' + k); d.style.cssText = `left:${LABEL_W}px;right:0;top:${lanes[k].top - 2}px;height:${lanes[k].h + 4}px`; inner.insertBefore(d, inner.firstChild.nextSibling); d.dataset.lane = k; }
  }
  function placeHead(){
    if(!head){ head = mk('tl-head'); inner.appendChild(head); }
    head.style.left = X(ED.t) + 'px'; if(head.parentNode !== inner) inner.appendChild(head);
    inner.appendChild(head);
  }

  /* ------------------------------------------------------------ selection */
  const keyOf = e => e && e.dataset && e.dataset.key;
  function applySel(){
    for(const [k, e] of els) e.classList.toggle('sel', ED.sel.includes(k));
    inner.querySelectorAll('.mark').forEach(m => m.classList.toggle('sel', ED.sel.includes(m.dataset.key)));
  }
  function select(keys, add){
    ED.sel = add ? Array.from(new Set(ED.sel.concat(keys))) : keys; applySel(); renderInspector(); if(typeof renderTextPane === 'function') renderTextPane();
  }
  function toggle(k){ ED.sel = ED.sel.includes(k) ? ED.sel.filter(x => x !== k) : ED.sel.concat([k]); applySel(); renderInspector(); }
  function resolve(k, edit, comp){
    const e = edit || ED.edit, C = comp || ED.C;
    if(k.startsWith('v:')){ const i = e.video.findIndex(c => 'v:' + c.id === k); return i < 0 ? null : {type: 'video', i, obj: e.video[i], view: C.vid[i]}; }
    if(k.startsWith('f:')){ const f = e.free.find(c => 'f:' + c.id === k.split('~')[0]); return f ? {type: 'free', obj: f, view: C.free.find(v => v.free === f.id)} : null; }
    if(k.startsWith('a:')){ const p = C.pieces.find(x => 'a:' + x.key === k); return p ? {type: 'piece', obj: (e.stems[p.stem] = e.stems[p.stem] || {}), view: p} : null; }
    if(k.startsWith('m:')){ const m = e.markers.find(c => 'm:' + c.id === k); return m ? {type: 'marker', obj: m} : null; }
    return null;
  }

  /* ------------------------------------------------------------ snapping */
  function snapPoints(skipKeys){
    const C = ED.C, pts = [0, C.total, ED.t];
    for(const c of C.vid){ pts.push(c.start, c.start + c.dur); }
    for(const m of ED.edit.markers) pts.push(m.t);
    for(const a of C.aud){ if(skipKeys && skipKeys.has(a.key)) continue; pts.push(a.start, a.start + a.dur); }
    if(ED.prog) for(const b of ED.prog.beats) pts.push(b[0]);
    return pts;
  }
  function snapT(t, skip){
    if(!ED.snap) return t; const th = 8 / ED.pps; let best = t, bd = th;
    for(const p of snapPoints(skip)){ const d = Math.abs(p - t); if(d < bd){ bd = d; best = p; } }
    return best;
  }

  /* ------------------------------------------------------------ pointer interactions */
  function timeAt(ev){ const r = inner.getBoundingClientRect(); return Math.max(0, T(ev.clientX - r.left)); }

  function onPointerDown(ev){
    if(ev.button !== 0) return;
    const clip = ev.target.closest('.clip'), mark = ev.target.closest('.mark');
    if(ev.target.closest('.lab .mbtn') || ev.target.closest('#tlLabels')) return;
    if(!clip && !mark){
      // ruler or empty space: seek (and scrub)
      select([]);
      const mv = e2 => EDP.seek(snapT(timeAt(e2)) === timeAt(e2) ? timeAt(e2) : timeAt(e2)), up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); };
      EDP.seek(timeAt(ev)); window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up); return;
    }
    ev.preventDefault();
    if(mark){ const k = keyOf(mark); select([k]); const m = ED.edit.markers.find(x => 'm:' + x.id === k); if(m) EDP.seek(m.t); return; }
    const key = keyOf(clip), handle = ev.target.classList.contains('h') ? (ev.target.classList.contains('l') ? 'l' : 'r') : null;
    if(ev.shiftKey || ev.ctrlKey || ev.metaKey) toggle(key); else if(!ED.sel.includes(key)) select([key]);
    const r = resolve(key); if(!r) return;
    beginDrag(ev, key, r, handle);
  }

  function beginDrag(ev, key, r, handle){
    const x0 = ev.clientX, before = JSON.stringify(ED.edit); let moved = false, mode = handle ? 'trim' : 'move', cur = {key, r}, y0 = ev.clientY;
    const baseEdit = JSON.parse(before), baseC = compile(baseEdit, ED.prog), rBase = resolve(key, baseEdit, baseC);
    const apply = ev2 => {
      const dt = (ev2.clientX - x0) / ED.pps;
      if(!moved && Math.abs(ev2.clientX - x0) < 4) return;
      if(!moved){ moved = true; document.body.classList.add('dragging'); }
      ED.edit = JSON.parse(before);
      if(mode === 'trim') trimOp(ED.edit, baseC, key, handle, dt, ev2, rBase);
      else moveOp(ED.edit, baseC, key, dt, ev2, cur, rBase);
      recompile(); build(); renderInspector(true);
    };
    const up = () => {
      window.removeEventListener('pointermove', apply); window.removeEventListener('pointerup', up); document.body.classList.remove('dragging');
      if(moved && JSON.stringify(ED.edit) !== before){ ED.undo.push(before); ED.redo = []; saveEdit(); }
      else if(moved) ED.edit = JSON.parse(before);
      recompile(); build(); renderInspector();
    };
    window.addEventListener('pointermove', apply); window.addEventListener('pointerup', up);
  }

  /* ---- trimming / expanding from either side ---- */
  const subtractRange = (list, a, b) => list.flatMap(([x0, x1]) => (b <= x0 || a >= x1) ? [[x0, x1]] : [].concat(a > x0 ? [[x0, a]] : [], b < x1 ? [[b, x1]] : []));
  function addRange(list, a, b){
    const all = list.concat([[a, b]]).sort((p, q) => p[0] - q[0]), out = [];
    for(const r of all){ if(out.length && r[0] <= out[out.length - 1][1] + 1e-6) out[out.length - 1][1] = Math.max(out[out.length - 1][1], r[1]); else out.push(r.slice()); }
    return out;
  }
  function trimOp(e, baseC, key, side, dt, ev, r){
    if(!r) return;                   // r: what was grabbed, resolved when the drag began (keys of pieces change while they are trimmed)
    const sp = (r.view && r.view.sp) || 1;
    if(r.type === 'video'){
      const c = baseC.vid.find(v => 'v:' + v.id === key), src = e.video.find(v => 'v:' + v.id === key);
      const total = ED.prog.total;
      if(src.type === 'freeze'){
        if(side === 'r'){
          const end = snapT(c.start + c.dur + dt, new Set()); src.dur = R3(Math.max(0.1, end - c.start));
          e.free = rippleFree(e.free, c.start + c.dur, src.dur - c.dur);
        }
        return;
      }
      if(side === 'l'){
        let nin = c.in + dt * c.sp; nin = Math.max(0, Math.min(c.out - 0.1 * c.sp, nin));
        document.body.classList.toggle('limit', nin <= 0);
        src.in = R3(nin);
        if(ED.ripple) e.free = rippleFree(e.free, c.start + c.dur, ((c.out - nin) / c.sp) - c.dur);
      } else {
        let nout = c.out + dt * c.sp; nout = Math.max(c.in + 0.1 * c.sp, Math.min(total, nout));
        document.body.classList.toggle('limit', nout >= total);
        src.out = R3(nout);
        if(ED.ripple) e.free = rippleFree(e.free, c.start + c.dur, ((nout - c.in) / c.sp) - c.dur);
      }
      return;
    }
    if(r.type === 'piece'){
      const p = baseC.pieces.find(x => 'a:' + x.key === key), s = ED.prog.stems.find(x => x.id === p.stem), o = e.stems[p.stem] = e.stems[p.stem] || {};
      const clipIn = baseC.vid.find(v => v.id === p.clipId);
      let gone = (o.gone || []).map(g => g.slice());
      if(side === 'l'){
        let x = p.b0 + dt * p.speed; x = Math.max(Math.max(clipIn.in, s.b0), Math.min(p.b1 - 0.05, x));
        gone = x > p.b0 ? addRange(gone, p.b0, x) : subtractRange(gone, x, p.b0);
      } else {
        let x = p.b1 + dt * p.speed; x = Math.min(Math.min(clipIn.out, s.b1), Math.max(p.b0 + 0.05, x));
        gone = x < p.b1 ? addRange(gone, x, p.b1) : subtractRange(gone, p.b1, x);
      }
      o.gone = gone.map(g => [R3(g[0]), R3(g[1])]); if(!o.gone.length) delete o.gone;
      return;
    }
    if(r.type === 'free'){
      const f = e.free.find(q => 'f:' + q.id === key), v = baseC.free.find(q => 'f:' + q.free === key), sp2 = f.speed || 1, dur = fileDur(v.src);
      if(side === 'l' && !f.loop){
        let d = dt; d = Math.max(-f.in / sp2, Math.min(((f.out - f.in) / sp2) - 0.05, d));
        let ns = snapT(f.start + d, new Set(['f:' + f.id])); d = ns - f.start; d = Math.max(-f.in / sp2, Math.min(((f.out - f.in) / sp2) - 0.05, d));
        f.start = R3(f.start + d); f.in = R3(f.in + d * sp2);
      } else if(side === 'r'){
        if(f.loop){ const end = snapT(f.start + v.dur + dt, new Set(['f:' + f.id])); f.span = R3(Math.max(v.one, end - f.start)); }
        else {
          let end = snapT(f.start + v.dur + dt, new Set(['f:' + f.id])); let nout = f.in + (end - f.start) * sp2;
          nout = Math.max(f.in + 0.05, Math.min(dur, nout)); document.body.classList.toggle('limit', nout >= dur - 1e-6); f.out = R3(nout);
        }
      }
    }
  }

  /* ---- moving ---- */
  function moveOp(e, baseC, key, dt, ev, cur, r){
    if(!r) return;
    if(r.type === 'video'){
      // reorder: the clip takes the slot under its own centre; its sound comes with it
      const idx = baseC.vid.findIndex(v => 'v:' + v.id === key), me = baseC.vid[idx], centre = me.start + dt + me.dur / 2;
      let pos = 0, slot = 0;
      baseC.vid.forEach((v, i) => { if(i === idx) return; if(pos + v.dur / 2 < centre) slot++; pos += v.dur; });
      const src = e.video.splice(idx, 1)[0]; e.video.splice(slot, 0, src);
      return;
    }
    if(r.type === 'piece'){
      if(Math.abs(dt) * ED.pps < 6) return;
      // moving a piece of the render's sound detaches it into a free clip
      const f = opDetach(e, r.view); cur.key = 'f:' + f.id; ED.sel = [cur.key];
      cur.free = f; cur.baseStart = f.start;
    }
    const f = cur.free || e.free.find(q => 'f:' + q.id === key), base0 = cur.baseStart != null ? cur.baseStart : f.start;
    if(cur.baseStart == null) cur.baseStart = f.start;
    if(r.type === 'free' || cur.free){
      const dur = (r.view || {}).dur || (f.out - f.in) / (f.speed || 1);
      let s = base0 + dt; const ids = new Set(['f:' + f.id]);
      const sn = snapT(s, ids), sn2 = snapT(s + dur, ids);
      if(ED.snap){ if(Math.abs(sn - s) <= Math.abs(sn2 - (s + dur))) s = sn; else s = sn2 - dur; }
      f.start = R3(Math.max(0, s));
    }
  }

  /* ------------------------------------------------------------ drops from the libraries */
  function onDrop(ev){
    ev.preventDefault(); const raw = ev.dataTransfer.getData('application/x-flash-media'); if(!raw) return;
    const m = JSON.parse(raw); Editor.addMedia(m, snapT(timeAt(ev)));
  }

  /* ------------------------------------------------------------ inspector */
  function field(label, node){ const r = mk('ifield'); const l = mk('', 'label'); l.textContent = label; r.append(l, node); return r; }
  function rangeCtl(min, max, step, value, fmt, apply, zero){
    const wrap = mk('rng'), inp = Object.assign(mk('', 'input'), {type: 'range', min, max, step, value}), val = mk('val', 'span');
    const show = v => (+v === 0 && zero) ? zero : fmt(+v);
    val.textContent = show(value); paintRange(inp);
    let before = null;
    inp.oninput = () => { if(before === null) before = JSON.stringify(ED.edit); val.textContent = show(inp.value); paintRange(inp); apply(ED.edit, parseFloat(inp.value)); recompile(); build(); };
    inp.onchange = () => { if(before !== null && JSON.stringify(ED.edit) !== before){ ED.undo.push(before); ED.redo = []; saveEdit(); } before = null; };
    wrap.append(inp, val); return wrap;
  }
  function btn(label, fn, cls){ const b = mk('btn small ' + (cls || ''), 'button'); b.textContent = label; b.onclick = fn; return b; }
  function toggleCtl(on, fn){ const t = mk('toggle' + (on ? ' on' : ''), 'button'); t.onclick = () => { t.classList.toggle('on'); fn(t.classList.contains('on')); }; return t; }

  function renderInspector(light){
    const box = $('#inspector'); if(!box || !ED.edit) return;
    if(light && box.dataset.sig === ED.sel.join('|') && box.dataset.light) { /* keep the controls while dragging */ return; }
    box.dataset.sig = ED.sel.join('|'); box.dataset.light = light ? '1' : ''; box.innerHTML = '';
    const sel = ED.sel.map(k => resolve(k)).filter(Boolean);
    const title = mk('ititle');
    if(!sel.length){
      title.textContent = 'Project'; box.appendChild(title);
      const b = btn('Project settings', e => { e.stopPropagation(); toggleProjectPanel(); }, ED.projOpen ? 'on' : ''); b.id = 'projSetBtn'; box.appendChild(b);
      const hint = mk('ihint'); hint.textContent = ED.C.vid.length + ' clip' + (ED.C.vid.length === 1 ? '' : 's') + ' \u00b7 ' + fmtT(ED.C.total) + ' \u00b7 select a clip to edit it'; box.appendChild(hint);
      renderProjectPanel(); return;
    }
    closeProjectPanel(true);
    if(sel.length > 1){
      title.textContent = sel.length + ' clips selected'; box.appendChild(title);
      const audio = sel.filter(s => s.type === 'piece' || s.type === 'free');
      if(audio.length){
        box.appendChild(field('Volume', rangeCtl(-40, 12, 0.5, 0, v => (v > 0 ? '+' : '') + v.toFixed(1) + ' dB', (e, v) => { ED.sel.map(k => resolve(k)).forEach(s => { if(s && (s.type === 'free' || s.type === 'piece')) s.obj.gain = (s.obj._g0 = s.obj._g0 ?? (s.obj.gain || 0)) + v; }); })));
        box.appendChild(btn('Mute', () => mutate(e => { ED.sel.map(k => resolve(k)).forEach(s => { if(s && (s.type === 'free' || s.type === 'piece')) s.obj.mute = true; }); })));
      }
      box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger'));
      return;
    }
    const s = sel[0], o = s.obj, v = s.view;
    if(s.type === 'marker'){
      title.textContent = 'Marker'; box.appendChild(title);
      const inp = Object.assign(mk('', 'input'), {type: 'text', value: o.text || '', placeholder: 'Note'}); inp.className = 'itext';
      inp.onchange = () => mutate(e => { const m = e.markers.find(x => x.id === o.id); if(m) m.text = inp.value; });
      box.appendChild(field('Note', inp)); box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger')); return;
    }
    if(s.type === 'video'){
      title.textContent = v.kind === 'freeze' ? 'Freeze frame' : 'Video · ' + (v.label || 'clip'); box.appendChild(title);
      if(v.kind === 'clip'){
        box.appendChild(field('Speed', rangeCtl(0.25, 4, 0.05, o.speed || 1, x => x.toFixed(2) + '×', (e, x) => { const c = e.video.find(q => q.id === o.id); if(c) c.speed = x; })));
        box.appendChild(field('Fade in', rangeCtl(0, 3, 0.1, o.fi || 0, x => x.toFixed(1) + ' s', (e, x) => { const c = e.video.find(q => q.id === o.id); if(c) c.fi = x; }, 'Off')));
        box.appendChild(field('Fade out', rangeCtl(0, 3, 0.1, o.fo || 0, x => x.toFixed(1) + ' s', (e, x) => { const c = e.video.find(q => q.id === o.id); if(c) c.fo = x; }, 'Off')));
      } else {
        box.appendChild(field('Hold for', rangeCtl(0.2, 10, 0.1, o.dur, x => x.toFixed(1) + ' s', (e, x) => { const c = e.video.find(q => q.id === o.id); if(c) c.dur = x; })));
      }
      box.appendChild(btn('Split', () => Editor.split())); box.appendChild(btn('Duplicate', () => Editor.duplicate())); box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger'));
      const info = mk('ihint'); info.textContent = fmtT(v.start) + ' → ' + fmtT(v.start + v.dur) + '  ·  drag the edges to trim or restore'; box.appendChild(info);
      return;
    }
    if(s.type === 'free' && v && v.bus === 'overlay'){
      title.textContent = 'Picture \u00b7 ' + (v.name || ''); box.appendChild(title);
      const set = (key, val) => (e, x) => { const f = e.free.find(q => q.id === o.id); if(f){ f.st = f.st || {}; f.st[key] = x; } };
      const st0 = o.st || {};
      box.appendChild(field('Size', rangeCtl(0.03, 1, 0.01, st0.w || 0.25, x => Math.round(x * 100) + '%', set('w'))));
      box.appendChild(field('Opacity', rangeCtl(0.1, 1, 0.05, st0.op == null ? 1 : st0.op, x => Math.round(x * 100) + '%', set('op'))));
      box.appendChild(field('Across', rangeCtl(0, 1, 0.01, st0.x == null ? 0.5 : st0.x, x => Math.round(x * 100) + '%', set('x'))));
      box.appendChild(field('Down', rangeCtl(0, 1, 0.01, st0.y == null ? 0.5 : st0.y, x => Math.round(x * 100) + '%', set('y'))));
      box.appendChild(field('Fade in', rangeCtl(0, 2, 0.1, st0.fi || 0, x => x.toFixed(1) + ' s', set('fi'), 'Off')));
      box.appendChild(field('Fade out', rangeCtl(0, 2, 0.1, st0.fo || 0, x => x.toFixed(1) + ' s', set('fo'), 'Off')));
      box.appendChild(btn('Whole video', () => mutate(e => { const f = e.free.find(q => q.id === o.id); if(f){ f.start = 0; f.in = 0; f.out = R3(ED.C.total); } })));
      box.appendChild(btn('Split', () => Editor.split())); box.appendChild(btn('Duplicate', () => Editor.duplicate())); box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger'));
      return;
    }
    if(s.type === 'free' && v && v.bus === 'text'){
      title.textContent = 'Text'; box.appendChild(title);
      const inp = Object.assign(mk('', 'input'), {type: 'text', value: o.text || '', placeholder: 'Type the text'}); inp.className = 'itext'; inp.style.width = '260px';
      inp.onchange = () => mutate(e => { const f = e.free.find(q => q.id === o.id); if(f){ f.text = inp.value; f.words = null; f.auto = f.auto && false; } });
      box.appendChild(field('Text', inp));
      const st0 = o.st || {};
      box.appendChild(field('Size', rangeCtl(2, 16, 0.1, st0.size || 5.4, x => x.toFixed(1) + '%', (e, x) => { const f = e.free.find(q => q.id === o.id); if(f){ f.st = f.st || {}; f.st.size = x; } })));
      box.appendChild(field('Position', rangeCtl(0.05, 0.95, 0.01, st0.y == null ? 0.8 : st0.y, x => Math.round(x * 100) + '%', (e, x) => { const f = e.free.find(q => q.id === o.id); if(f){ f.st = f.st || {}; f.st.y = x; } })));
      box.appendChild(btn('Split', () => Editor.split())); box.appendChild(btn('Duplicate', () => Editor.duplicate())); box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger'));
      const hint = mk('ihint'); hint.textContent = 'more styles in the Text tab'; box.appendChild(hint);
      return;
    }
    // audio: a piece of the render's sound, or a clip you added
    const isPiece = s.type === 'piece';
    title.textContent = (isPiece ? (v.bus === 'narration' ? 'Voice' : 'Effect') : (v.bus === 'music' ? 'Music' : 'Effect')) + ' · ' + (v.name || '').split('/').pop(); box.appendChild(title);
    const gv = isPiece ? (o.gain || 0) : (o.gain || 0);
    box.appendChild(field('Volume', rangeCtl(-40, 12, 0.5, gv, x => (x > 0 ? '+' : '') + x.toFixed(1) + ' dB', (e, x) => { const t = isPiece ? (e.stems[v.stem] = e.stems[v.stem] || {}) : e.free.find(q => q.id === v.free); if(t) t.gain = x; })));
    box.appendChild(field('Fade in', rangeCtl(0, 5, 0.1, isPiece ? (o.fi || 0) : (o.fi || 0), x => x.toFixed(1) + ' s', (e, x) => { const t = isPiece ? (e.stems[v.stem] = e.stems[v.stem] || {}) : e.free.find(q => q.id === v.free); if(t) t.fi = x; }, 'Off')));
    box.appendChild(field('Fade out', rangeCtl(0, 8, 0.1, isPiece ? (o.fo || 0) : (o.fo || 0), x => x.toFixed(1) + ' s', (e, x) => { const t = isPiece ? (e.stems[v.stem] = e.stems[v.stem] || {}) : e.free.find(q => q.id === v.free); if(t) t.fo = x; }, 'Off')));
    if(!isPiece){
      box.appendChild(field('Speed', rangeCtl(0.5, 2, 0.05, o.speed || 1, x => x.toFixed(2) + '×', (e, x) => { const t = e.free.find(q => q.id === v.free); if(t) t.speed = x; })));
      if(v.bus === 'music') box.appendChild(field('Loop to fill', toggleCtl(!!o.loop, on => mutate(e => { const t = e.free.find(q => q.id === v.free); if(t){ t.loop = on; if(on) t.span = Math.max(v.one || 1, t.span || 0, ED.C.total - t.start); } }))));
    }
    box.appendChild(field('Mute', toggleCtl(!!o.mute, on => mutate(e => { const t = isPiece ? (e.stems[v.stem] = e.stems[v.stem] || {}) : e.free.find(q => q.id === v.free); if(t) t.mute = on; }))));
    box.appendChild(btn('Split', () => Editor.split())); box.appendChild(btn('Duplicate', () => Editor.duplicate())); box.appendChild(btn('Delete', () => Editor.deleteSel(), 'danger'));
  }


  /* the project-wide settings live in a small panel above the dock, in two columns, so nothing needs to scroll */
  function renderProjectPanel(){
    let pop = $('#projPop');
    if(!pop){ pop = mk('popover'); pop.id = 'projPop'; $('#dock').appendChild(pop); pop.addEventListener('pointerdown', e => e.stopPropagation()); }
    pop.hidden = !ED.projOpen; if(!ED.projOpen) return;
    if(pop.contains(document.activeElement) && document.activeElement.type === 'range') return;       // do not rebuild a slider that is being dragged
    pop.innerHTML = '';
    const head = (t) => { const h = mk('phead'); h.textContent = t; pop.appendChild(h); };
    const tg = (name, label) => pop.appendChild(field(label, rangeCtl(-24, 6, 0.5, (ED.edit.tracks[name] || {}).gain || 0, v => (v > 0 ? '+' : '') + v.toFixed(1) + ' dB', (e, v) => { e.tracks[name].gain = v; })));
    head('Sound');
    pop.appendChild(field('Music dips under speech', rangeCtl(0, 20, 0.5, ED.edit.duck_db || 0, v => v.toFixed(1) + ' dB', (e, v) => { e.duck_db = v; }, 'Off')));
    tg('narration', 'Voice level'); tg('sfx', 'Effects level'); tg('music', 'Music level');
    pop.appendChild(field('Even out loudness (-14 LUFS)', toggleCtl(!!ED.edit.loudnorm, on => mutate(e => { e.loudnorm = on; }))));
    head('Picture');
    pop.appendChild(field('Brightness', rangeCtl(-0.3, 0.3, 0.01, ED.edit.adjust.brightness, v => v.toFixed(2), (e, v) => { e.adjust.brightness = v; })));
    pop.appendChild(field('Contrast', rangeCtl(0.6, 1.6, 0.01, ED.edit.adjust.contrast, v => v.toFixed(2), (e, v) => { e.adjust.contrast = v; })));
    pop.appendChild(field('Saturation', rangeCtl(0, 2, 0.01, ED.edit.adjust.saturation, v => v.toFixed(2), (e, v) => { e.adjust.saturation = v; })));
    pop.appendChild(field('Fade out at the end', rangeCtl(0, 3, 0.1, ED.edit.fade_out_video || 0, v => v.toFixed(1) + ' s', (e, v) => { e.fade_out_video = v; }, 'Off')));
    const foot = mk('pfoot');
    foot.append(btn('Reset edit', async () => { if(await sheet({title: 'Reset the whole edit?', text: 'Every cut, trim, added sound and text goes back to how the render made it. You can undo this.', ok: 'Reset', danger: true})) mutate(e => { const d = defaultEdit(ED.prog); Object.keys(e).forEach(k => delete e[k]); Object.assign(e, d); }); }, 'danger'),
                btn('Done', () => closeProjectPanel(), 'primary'));
    pop.appendChild(foot);
  }
  function toggleProjectPanel(){ ED.projOpen = !ED.projOpen; renderInspector(); }
  function closeProjectPanel(quiet){ if(!ED.projOpen) return; ED.projOpen = false; const pop = $('#projPop'); if(pop) pop.hidden = true; if(!quiet) renderInspector(); }
  document.addEventListener('pointerdown', e => { if(ED.projOpen && !e.target.closest('#projPop') && !e.target.closest('#projSetBtn')) closeProjectPanel(); });

  /* ------------------------------------------------------------ public */
  const ICON_SPK = '<svg class="i" viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M4 9v6h4l5 4V5L8 9zM16 8a5 5 0 0 1 0 8"/></svg>';
  const ICON_MUTE = '<svg class="i" viewBox="0 0 24 24" style="width:13px;height:13px"><path d="M4 9v6h4l5 4V5L8 9zM17 9l5 6M22 9l-5 6"/></svg>';
  window.ICON_SPK = ICON_SPK; window.ICON_MUTE = ICON_MUTE;

  function init(){
    inner = $('#tlInner'); scroll = $('#tlScroll');
    labels = mk(); labels.id = 'tlLabels'; labels.className = 'tl-labels';
    inner.addEventListener('pointerdown', onPointerDown);
    inner.addEventListener('dragover', e => { if(e.dataTransfer.types.includes('application/x-flash-media')) e.preventDefault(); });
    inner.addEventListener('drop', onDrop);
    scroll.addEventListener('wheel', e => { if(e.ctrlKey){ e.preventDefault(); Editor.zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX); } }, {passive: false});
    new ResizeObserver(debounce(() => { const w = scroll.clientWidth; if(w > 0 && ED.autoFit && ED.C && Math.abs(w - (init._w || 0)) > 2){ init._w = w; Editor.fit(); } }, 150)).observe(scroll);
  }
  function refresh(opts){
    opts = opts || {};
    if(!opts.keepSel) ED.sel = ED.sel.filter(k => els.has(k) || k.startsWith('m:'));
    inner.innerHTML = ''; els.clear(); head = null; inner.appendChild(labels);
    build(); $('#tlTime').textContent = fmtT(ED.t) + ' / ' + fmtT(ED.C.total); renderInspector();
    if(typeof renderCaptions === 'function'){ renderCaptions(); renderTextPane(); }
    $('#edUndo').disabled = !ED.undo.length; $('#edRedo').disabled = !ED.redo.length;
  }
  return {init, build, refresh, select, resolve, renderInspector, closeProjectPanel, snapT, timeAt, srcUrl, peaksFor, fileDur, Thumbs, X, field, rangeCtl, btn, toggleCtl, setHead: placeHead, get els(){ return els; }, get scrollEl(){ return scroll; }};
})();
