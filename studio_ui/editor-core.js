/* editor-core.js - the post-production edit: its model, its compilation to plain time ranges, and the operations.

   The edit is non-destructive. It sits next to the project and is only applied when you Export.

   ED.edit = {
     video:  [ {id, type:'clip', in, out, speed, fi, fo, label} | {id, type:'freeze', at, dur} ]   // magnetic: placed back to back
     stems:  { <stemId>: {gain, fi, fo, mute, gone:[[a,b]], cuts:[t]} }   // changes to the narration / effects the render made
     free:   [ {id, track:'sfx'|'music', kind:'builtin'|'sfx'|'music', name, start, in, out, gain, fi, fo, mute, speed, loop, span} ]
     tracks: { narration:{mute,gain}, sfx:{...}, music:{...} },  markers:[{id,t,text}],
     duck_db, adjust:{brightness,contrast,saturation}, fade_out_video }

   Times in `video` (in/out/at) and in stems (gone/cuts) are seconds of the ORIGINAL render ("base time"), so
   they stay valid whatever is cut or reordered; everything on the timeline is derived from them (compile()).
   Narration and effects of the render follow the video clip they belong to - cut, move or restore a clip and
   its sound comes with it - while effects / music you add are free and keep their own place on the timeline. */

const ED = {
  prog: null, edit: null, C: null, sel: [], undo: [], redo: [],
  t: 0, pps: 12, snap: true, ripple: true, autoFit: true,
};

const R3 = x => Math.round(x * 1000) / 1000;
let _uid = 0;
const newId = p => p + Date.now().toString(36) + (++_uid).toString(36);
const clone = o => JSON.parse(JSON.stringify(o));
const fmtT = s => { s = Math.max(0, s); return Math.floor(s / 60) + ':' + (s % 60).toFixed(1).padStart(4, '0'); };

const sigOf = prog => prog.segments.map(s => Math.round(s.end * 10)).join(',');     // identifies the timing the edit was made on

function defaultEdit(prog, legacyMusic){
  const e = {
    v: 1, sig: sigOf(prog),
    video: prog.segments.map(s => ({id: 'v-' + s.name, type: 'clip', in: s.start, out: s.end, speed: 1, fi: 0, fo: 0, label: s.name === 'intro' ? 'Hook' : s.name === 'outro' ? 'Close' : s.name.replace('clip', '') + ' · ' + (s.title || '')})),
    stems: {}, free: [], markers: [],
    tracks: {narration: {mute: false, gain: 0}, sfx: {mute: false, gain: 0}, music: {mute: false, gain: 0}},
    duck_db: 8, adjust: {brightness: 0, contrast: 1, saturation: 1}, fade_out_video: 0,
  };
  if(legacyMusic && legacyMusic.file && legacyMusic.enabled){       // the single music block of the earlier timeline
    const m = legacyMusic;
    e.free.push({id: newId('f'), track: 'music', kind: 'music', name: m.file, start: m.start || 0, in: m.in_point || 0,
                 out: (m.in_point || 0) + (m.length > 0 ? m.length : 600), gain: m.volume_db + 0, fi: m.fade_in || 0, fo: m.fade_out || 0,
                 mute: false, speed: 1, loop: !!m.loop, span: m.length > 0 ? m.length : 0, _fit: true});
    e.duck_db = m.duck_db || 0;
  }
  return e;
}

function normalizeEdit(e, prog){
  const d = defaultEdit(prog);
  const out = Object.assign({}, d, e || {});
  out.tracks = Object.assign({}, d.tracks, (e && e.tracks) || {});
  out.adjust = Object.assign({}, d.adjust, (e && e.adjust) || {});
  out.stems = out.stems || {}; out.free = out.free || []; out.markers = out.markers || [];
  if(!out.video || !out.video.length) out.video = d.video;
  return out;
}

/* ------------------------------------------------------------------ compile */
function srcOfFree(f){ return f.kind === 'narration' ? {type: 'narration', path: f.name} : {type: f.kind, name: f.name}; }

function compile(edit, prog){
  edit = edit || ED.edit; prog = prog || ED.prog;
  const vid = []; let t = 0;
  for(const c of edit.video){
    if(c.type === 'freeze'){ vid.push({id: c.id, kind: 'freeze', at: c.at, start: t, dur: c.dur, label: 'Freeze frame'}); t += c.dur; }
    else { const sp = c.speed || 1, dur = (c.out - c.in) / sp; vid.push({id: c.id, kind: 'clip', in: c.in, out: c.out, sp, start: t, dur, fi: c.fi || 0, fo: c.fo || 0, label: c.label || ''}); t += dur; }
  }
  const total = t, aud = [], trk = n => edit.tracks[n] || {};
  const pieces = [];                      // narration / effects of the render, cut to the video clips
  for(const s of prog.stems){
    const o = edit.stems[s.id] || {};
    let ivs = [[s.b0, s.b1]];
    for(const [ga, gb] of (o.gone || [])){
      ivs = ivs.flatMap(([x0, x1]) => {
        if(gb <= x0 || ga >= x1) return [[x0, x1]];
        const r = []; if(ga > x0) r.push([x0, ga]); if(gb < x1) r.push([gb, x1]); return r;
      });
    }
    const cuts = (o.cuts || []).slice().sort((p, q) => p - q);
    const parts = ivs.flatMap(([x0, x1]) => {
      const pts = [x0, ...cuts.filter(c => c > x0 + 1e-3 && c < x1 - 1e-3), x1], res = [];
      for(let i = 0; i < pts.length - 1; i++) res.push([pts[i], pts[i + 1], i === 0, i === pts.length - 2, x0, x1]);
      return res;
    });
    for(const [x0, x1, first, last, ix0, ix1] of parts){
      for(const c of vid){
        if(c.kind !== 'clip') continue;
        const a = Math.max(x0, c.in), b = Math.min(x1, c.out);
        if(b - a < 0.01) continue;
        const p = {
          key: `${s.id}@${Math.round(a * 1000)}#${c.id}`, ref: 'stem', stem: s.id, bus: s.track, name: s.name || s.id,
          src: s.kind === 'narration' ? {type: 'narration', path: s.path} : {type: 'builtin', name: s.name},
          in: a - s.b0, out: b - s.b0, start: c.start + (a - c.in) / c.sp, dur: (b - a) / c.sp, speed: c.sp,
          gain_db: s.gain_db + (o.gain || 0) + (trk(s.track).gain || 0),
          fade_in: first && a <= x0 + 1e-6 ? (o.fi || 0) : 0, fade_out: last && b >= x1 - 1e-6 ? (o.fo || 0) : 0,
          mute: !!o.mute || !!trk(s.track).mute, b0: a, b1: b, clipId: c.id, ovr: !!o.mute || !!o.gain,
        };
        pieces.push(p); aud.push(p);
      }
    }
  }
  const free = [], texts = [], images = [];       // effects / music / text / pictures you added
  for(const f of edit.free){
    if(f.track === 'overlay'){
      const dur = Math.max(0.05, f.out - f.in);
      const view = {key: 'f:' + f.id, ref: 'free', free: f.id, bus: 'overlay', name: f.name, start: f.start, dur, st: f.st || {}, in: f.in, out: f.out, speed: 1, src: {type: 'image', name: f.name}};
      free.push(view); images.push(view); continue;
    }
    if(f.track === 'text'){
      const dur = Math.max(0.05, f.out - f.in), base = f.start - f.in;
      const view = {key: 'f:' + f.id, ref: 'free', free: f.id, bus: 'text', name: f.text || '', text: f.text || '', st: f.st || {}, start: f.start, dur,
                    words: (f.words || []).map(w => [w[0], base + w[1], base + w[2]]), speed: 1, in: f.in, out: f.out, src: {type: 'text'}};
      free.push(view); texts.push(view); continue;
    }
    const sp = f.speed || 1, one = Math.max(0.02, (f.out - f.in) / sp);
    const span = f.loop ? Math.max(one, f.span > 0 ? f.span : Math.max(one, total - f.start)) : one;
    const view = {key: 'f:' + f.id, ref: 'free', free: f.id, bus: f.track, name: f.name, src: srcOfFree(f), in: f.in, out: f.out,
                  start: f.start, dur: span, speed: sp, one, gain_db: f.gain || 0, fade_in: f.fi || 0, fade_out: f.fo || 0,
                  mute: !!f.mute || !!trk(f.track).mute, loop: !!f.loop};
    free.push(view);
    const n = f.loop ? Math.ceil(span / one - 1e-6) : 1;
    for(let k = 0; k < n; k++){
      const st = f.start + k * one, len = Math.min(one, f.start + span - st);
      if(len < 0.02) break;
      aud.push(Object.assign({}, view, {key: view.key + (k ? '~' + k : ''), start: st, dur: len, out: f.in + len * sp,
        gain_db: view.gain_db + (trk(f.track).gain || 0),
        fade_in: k === 0 ? view.fade_in : 0, fade_out: st + len >= f.start + span - 1e-6 ? view.fade_out : 0}));
    }
  }
  return {vid, total, aud, pieces, free, texts, images};
}

function recompile(){ ED.C = compile(); return ED.C; }

function tlToBase(t){
  const C = ED.C; if(!C || !C.vid.length) return 0;
  let c = C.vid.find(v => t >= v.start && t < v.start + v.dur) || C.vid[C.vid.length - 1];
  if(c.kind === 'freeze') return c.at;
  return Math.max(c.in, Math.min(c.out, c.in + (t - c.start) * c.sp));
}

function exportPayload(){
  const C = ED.C, e = ED.edit;
  return {
    total: R3(C.total), fps: 24, duck_db: e.duck_db || 0, loudnorm: !!e.loudnorm, fade_out_video: e.fade_out_video || 0,
    adjust: {brightness: e.adjust.brightness, contrast: e.adjust.contrast, saturation: e.adjust.saturation},
    video: C.vid.map(v => v.kind === 'freeze' ? {type: 'freeze', at: R3(v.at), dur: R3(v.dur)}
      : {type: 'clip', in: R3(v.in), out: R3(v.out), speed: v.sp, fade_in: v.fi, fade_out: v.fo}),
    w: ED.prog.w, h: ED.prog.h,
    images: C.images.map(i => ({name: i.name, start: R3(i.start), dur: R3(i.dur), x: i.st.x == null ? 0.5 : i.st.x, y: i.st.y == null ? 0.5 : i.st.y, w: i.st.w || 0.25, opacity: i.st.op == null ? 1 : i.st.op, fi: i.st.fi || 0, fo: i.st.fo || 0})),
    texts: C.texts.map(t => ({text: t.text, start: R3(t.start), dur: R3(t.dur), st: t.st, words: t.words.length ? t.words : null})),
    audio: C.aud.filter(a => !a.mute).map(a => ({bus: a.bus, src: a.src, in: R3(a.in), out: R3(a.out), start: R3(a.start),
      gain_db: R3(a.gain_db), fade_in: a.fade_in, fade_out: a.fade_out, speed: a.speed})),
  };
}

/* ------------------------------------------------------------------ history */
let _saveEditTimer = 0;
function saveEdit(){
  clearTimeout(_saveEditTimer);
  const proj = PROJ.active, st = style, body = JSON.stringify(ED.edit);
  _saveEditTimer = setTimeout(() => fetch('/api/edit?style=' + st + '&project=' + encodeURIComponent(proj),
    {method: 'POST', headers: {'Content-Type': 'application/json'}, body}).catch(() => {}), 500);
}

/* mutate(fn): run an operation on the edit with undo support. fn gets the edit and returns false to cancel. */
function mutate(fn, opts){
  const before = JSON.stringify(ED.edit);
  const r = fn(ED.edit);
  if(r === false) { ED.edit = JSON.parse(before); return false; }
  if(JSON.stringify(ED.edit) === before) return false;
  ED.undo.push(before); if(ED.undo.length > 150) ED.undo.shift(); ED.redo = [];
  afterChange(opts); return true;
}
function afterChange(opts){
  recompile(); saveEdit();
  if(typeof EDUI !== 'undefined') EDUI.refresh(opts);
}
function undo(){
  if(!ED.undo.length) return;
  ED.redo.push(JSON.stringify(ED.edit)); ED.edit = JSON.parse(ED.undo.pop()); afterChange({keepSel: true});
}
function redo(){
  if(!ED.redo.length) return;
  ED.undo.push(JSON.stringify(ED.edit)); ED.edit = JSON.parse(ED.redo.pop()); afterChange({keepSel: true});
}

/* ------------------------------------------------------------------ operations (all on the edit object) */
const vidIndexAt = (C, t) => C.vid.findIndex(c => c.start < t - 0.02 && t < c.start + c.dur - 0.02);

function opSplitVideo(e, C, t){
  const i = vidIndexAt(C, t); if(i < 0) return false;
  const c = C.vid[i], src = e.video[i];
  if(src.type === 'freeze'){
    const d1 = R3(t - c.start); e.video.splice(i + 1, 0, Object.assign({}, src, {id: newId('v'), dur: R3(src.dur - d1)})); src.dur = d1;
  } else {
    const m = R3(c.in + (t - c.start) * c.sp);
    e.video.splice(i + 1, 0, Object.assign({}, src, {id: newId('v'), in: m, fi: 0}));
    src.out = m; src.fo = 0;
  }
  return true;
}

function opSplitFree(e, t, ids){
  let did = false;
  for(const f of e.free.slice()){
    if(ids && !ids.includes(f.id)) continue;
    const sp = f.speed || 1, dur = f.loop ? 0 : (f.out - f.in) / sp;
    if(f.loop || !(f.start < t - 0.02 && t < f.start + dur - 0.02)) continue;
    const cut = R3(f.in + (t - f.start) * sp);
    const second = Object.assign({}, f, {id: newId('f'), start: R3(t), in: cut, fi: 0});
    if(f.track === 'text'){ f.words = null; second.words = null; }
    f.out = cut; f.fo = 0; e.free.splice(e.free.indexOf(f) + 1, 0, second); did = true;
  }
  return did;
}

/* shift / crop the free items when time is removed (delta<0) from, or inserted (delta>0) at `pos` */
function rippleFree(free, pos, delta){
  if(!delta) return free;
  const out = [];
  for(const f of free){
    const sp = f.speed || 1, dur = f.loop ? Math.max(0.02, f.span || 1) : (f.out - f.in) / sp, s = f.start, en = s + dur;
    if(delta > 0){ out.push(s >= pos - 1e-6 ? Object.assign({}, f, {start: R3(s + delta)}) : f); continue; }
    const a = pos + delta, b = pos;                     // removed range [a,b)
    if(en <= a + 1e-6){ out.push(f); continue; }
    if(s >= b - 1e-6){ out.push(Object.assign({}, f, {start: R3(s + delta)})); continue; }
    if(s >= a && en <= b) continue;                     // swallowed
    const g = Object.assign({}, f);
    if(s < a && en > b){ g.out = R3(f.in + (dur + delta) * sp); if(f.loop) g.span = R3(dur + delta); }       // shortened
    else if(s < a){ g.out = R3(f.in + (a - s) * sp); if(f.loop) g.span = R3(a - s); }                          // tail cut
    else { g.in = R3(f.in + (b - s) * sp); g.start = R3(a); if(f.loop) g.span = R3(en - b); }                  // head cut
    out.push(g);
  }
  return out;
}

function opDeleteVideo(e, C, i, ripple){
  const c = C.vid[i];
  e.video.splice(i, 1);
  if(ripple) e.free = rippleFree(e.free, c.start + c.dur, -c.dur);
  return e.video.length > 0;
}

function opAddMarker(e, t){ e.markers.push({id: newId('m'), t: R3(t), text: ''}); return true; }

function opDetach(e, piece){                 // turn a piece of the render's sound into a free clip (so it can be moved)
  const s = ED.prog.stems.find(x => x.id === piece.stem), o = (e.stems[piece.stem] = e.stems[piece.stem] || {});
  o.gone = (o.gone || []).concat([[R3(piece.b0), R3(piece.b1)]]);
  const f = {id: newId('f'), track: piece.bus, kind: s.kind === 'narration' ? 'narration' : 'builtin',
             name: s.kind === 'narration' ? s.path : s.name, start: R3(piece.start), in: R3(piece.in), out: R3(piece.out), gain: R3(piece.gain_db),
             fi: 0, fo: 0, mute: false, speed: piece.speed, loop: false, span: 0, label: s.name};
  e.free.push(f);
  return f;
}

const clipSource = (e, key) => null;
