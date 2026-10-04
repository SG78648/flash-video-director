/* editor-text.js - text clips: captions and titles. Styles, the live overlay on the stage, the Text tab and the
   auto-captions that are built from the narration's word timings (so they follow every cut, move and speed change). */

const TEXT_FONTS = ['Arial', 'Segoe UI', 'Impact', 'Ink Free', 'Consolas'];
const TEXT_PRESETS = {
  Classic: {font: 'Arial', size: 5.4, color: '#ffffff', outline: '#000000', ow: 0.09, box: false, bold: true, upper: false, x: 0.5, y: 0.8, hl: '', fi: 0.08, fo: 0.08},
  Box:     {font: 'Segoe UI', size: 4.8, color: '#ffffff', outline: '#000000', ow: 0.0, box: true, boxColor: '#000000', boxOp: 0.62, bold: true, upper: false, x: 0.5, y: 0.8, hl: '', fi: 0.08, fo: 0.08},
  Pop:     {font: 'Arial', size: 6.2, color: '#ffffff', outline: '#000000', ow: 0.1, box: false, bold: true, upper: true, x: 0.5, y: 0.78, hl: '#FFD400', fi: 0.05, fo: 0.05},
  Title:   {font: 'Impact', size: 11, color: '#ffffff', outline: '#000000', ow: 0.06, box: false, bold: true, upper: false, x: 0.5, y: 0.22, hl: '', fi: 0.25, fo: 0.25},
  Hand:    {font: 'Ink Free', size: 7.5, color: '#F6611B', outline: '#ffffff', ow: 0.07, box: false, bold: true, upper: false, x: 0.5, y: 0.8, hl: '', fi: 0.1, fo: 0.1},
};
const TXT = {words: 5, preset: 'Pop'};
try{ Object.assign(TXT, JSON.parse(localStorage.getItem('flash.txt') || '{}')); }catch(e){}
const saveTxt = () => { try{ localStorage.setItem('flash.txt', JSON.stringify(TXT)); }catch(e){} };

/* ------------------------------------------------------------------ the overlay on the stage */
function renderCaptions(){
  const layer = $('#capLayer'); if(!layer || !ED.C) return;
  const phone = $('#phone'), base = Math.min(phone.clientWidth, phone.clientHeight);
  const active = ED.C.texts.filter(t => ED.t >= t.start - 1e-6 && ED.t < t.start + t.dur);
  layer.innerHTML = '';
  for(const t of active){
    const st = Object.assign({}, TEXT_PRESETS.Classic, t.st || {}), px = st.size / 100 * base;
    const d = mk('cap'); d.style.cssText = `left:${st.x * 100}%;top:${st.y * 100}%;font-family:'${st.font}',sans-serif;font-weight:${st.bold ? 800 : 400};font-size:${px}px;color:${st.color}`;
    const w = px * (st.ow || 0);
    if(st.box){ d.style.background = hexA(st.boxColor || '#000000', st.boxOp == null ? 0.6 : st.boxOp); d.style.padding = '0.18em 0.5em'; d.style.borderRadius = '0.2em'; }
    else if(w > 0){ const o = st.outline, sh = []; for(let a = 0; a < 16; a++){ const r = a / 16 * Math.PI * 2; sh.push(`${(Math.cos(r) * w).toFixed(1)}px ${(Math.sin(r) * w).toFixed(1)}px 0 ${o}`); } d.style.textShadow = sh.join(','); }
    const txt = st.upper ? (t.text || '').toUpperCase() : (t.text || '');
    if(st.hl && t.words.length){
      t.words.forEach((wd, i) => { const sp = document.createElement('span'); sp.textContent = (st.upper ? String(wd[0]).toUpperCase() : wd[0]) + (i < t.words.length - 1 ? ' ' : ''); if(ED.t >= wd[1] && ED.t < wd[2] + 0.02) sp.style.color = st.hl; d.appendChild(sp); });
    } else d.textContent = txt;
    const into = ED.t - t.start, left = t.start + t.dur - ED.t; let op = 1;
    if(st.fi > 0 && into < st.fi) op = Math.min(op, into / st.fi);
    if(st.fo > 0 && left < st.fo) op = Math.min(op, left / st.fo);
    d.style.opacity = Math.max(0, op); layer.appendChild(d);
  }
}
function hexA(hex, a){ const h = hex.replace('#', ''); return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`; }

/* ------------------------------------------------------------------ creating text */
function addText(){
  const f = {id: newId('f'), track: 'text', kind: 'text', text: 'Your text', start: R3(ED.t), in: 0, out: 3, speed: 1, gain: 0, fi: 0, fo: 0, mute: false, loop: false, span: 0,
             st: Object.assign({}, TEXT_PRESETS.Title, {y: 0.3})};
  mutate(e => { e.free.push(f); }); EDUI.select(['f:' + f.id]);
}

function autoCaptions(){
  const pieces = ED.C.pieces.filter(p => p.bus === 'narration' && !p.mute).sort((a, b) => a.start - b.start);
  const preset = TEXT_PRESETS[TXT.preset] || TEXT_PRESETS.Pop, maxW = TXT.words, caps = [];
  for(const p of pieces){
    const stem = ED.prog.stems.find(s => s.id === p.stem); if(!stem || !stem.words || !stem.words.length) continue;
    const words = stem.words.filter(w => w[1] >= p.b0 - 0.02 && w[1] < p.b1 - 0.02);
    const tl = bt => p.start + (bt - p.b0) / p.speed;
    let cur = [];
    const flush = () => {
      if(!cur.length) return;
      const s0 = tl(cur[0][1]), e0 = tl(cur[cur.length - 1][2]);
      const next = null, dur = Math.max(0.3, e0 - s0 + 0.12);
      caps.push({id: newId('f'), track: 'text', kind: 'text', text: cur.map(w => w[0]).join(' '), start: R3(Math.max(0, s0 - 0.04)), in: 0, out: R3(dur + 0.04), speed: 1, gain: 0, fi: 0, fo: 0,
                 mute: false, loop: false, span: 0, auto: true, st: Object.assign({}, preset),
                 words: cur.map(w => [w[0], R3(tl(w[1]) - Math.max(0, s0 - 0.04)), R3(tl(w[2]) - Math.max(0, s0 - 0.04))])});
      cur = [];
    };
    words.forEach((w, i) => {
      cur.push(w);
      const last = /[.?!]$/.test(w[0]), soft = /[,;:]$/.test(w[0]), nextGap = i + 1 < words.length ? words[i + 1][1] - w[2] : 1;
      if(cur.length >= maxW || last || (soft && cur.length >= 3) || nextGap > 0.5 || (cur.length >= 3 && w[2] - cur[0][1] > 2.4)) flush();
    });
    flush();
  }
  if(!caps.length){ toast('There is no narration on the timeline to caption'); return; }
  mutate(e => { e.free = e.free.filter(f => !f.auto).concat(caps); });
  toast(caps.length + ' captions added');
}

/* ------------------------------------------------------------------ the Text tab */
function selectedTexts(){ return ED.sel.map(k => EDUI.resolve(k)).filter(s => s && s.type === 'free' && s.view && s.view.bus === 'text'); }
function setTextStyle(key, val){ const ids = selectedTexts().map(s => s.obj.id); mutate(e => { e.free.forEach(f => { if(ids.includes(f.id)){ f.st = f.st || {}; f.st[key] = val; } }); }); }
function applyTextPreset(name){ const ids = selectedTexts().map(s => s.obj.id); mutate(e => { e.free.forEach(f => { if(ids.includes(f.id)) f.st = Object.assign({}, TEXT_PRESETS[name]); }); }); }
function applyToAllCaptions(){ const src = selectedTexts()[0]; if(!src) return; const st = Object.assign({}, src.obj.st); mutate(e => { e.free.forEach(f => { if(f.auto) f.st = Object.assign({}, st); }); }); toast('Look applied to every caption'); }

function colorCtl(value, onChange){ const i = Object.assign(mk('', 'input'), {type: 'color', value}); i.onchange = () => onChange(i.value); return i; }
function selectCtl(options, value, onChange){ const s = mk('', 'select'); options.forEach(o => { const op = mk('', 'option'); op.value = op.textContent = o; s.appendChild(op); }); s.value = value; s.onchange = () => onChange(s.value); return s; }

function renderTextPane(){
  const box = $('#textPane'); if(!box || !ED.edit) return;
  if(box.contains(document.activeElement) && /TEXTAREA|INPUT/.test(document.activeElement.tagName) && document.activeElement.type !== 'range' && document.activeElement.type !== 'color') return;
  box.innerHTML = '';
  const row = mk('btnrow'); row.append(EDUI.btn('Add text', addText, 'primary'), EDUI.btn('Auto-captions', autoCaptions)); box.appendChild(row);
  const opts = mk('gcard'); opts.style.padding = '4px 0';
  const r1 = mk('crow'); r1.append(EDUI.field('Words per caption', EDUI.rangeCtl(2, 9, 1, TXT.words, v => String(v), (e, v) => { TXT.words = v; saveTxt(); })));
  const r2 = mk('crow'); r2.append(EDUI.field('Caption look', selectCtl(Object.keys(TEXT_PRESETS), TXT.preset, v => { TXT.preset = v; saveTxt(); })));
  opts.append(r1, r2); box.appendChild(opts);
  const hint = mk('hint'); hint.textContent = 'Auto-captions are made from the voice on the timeline, so they follow your cuts. Making them again replaces the earlier ones.'; box.appendChild(hint);

  const sel = selectedTexts();
  const h = mk('', 'h3'); h.textContent = sel.length ? (sel.length > 1 ? sel.length + ' texts selected' : 'Selected text') : 'Text style'; box.appendChild(h);
  if(!sel.length){ const t = mk('hint'); t.textContent = 'Select a text clip on the timeline to change how it looks.'; box.appendChild(t); return; }
  const o = sel[0].obj, st = Object.assign({}, TEXT_PRESETS.Classic, o.st || {});
  if(sel.length === 1){
    const ta = mk('', 'textarea'); ta.value = o.text || ''; ta.rows = 3; ta.className = 'txarea'; ta.placeholder = 'Type the text';
    ta.onchange = () => mutate(e => { const f = e.free.find(q => q.id === o.id); if(f){ f.text = ta.value; f.words = null; } });
    box.appendChild(ta);
  }
  const pr = mk('btnrow'); Object.keys(TEXT_PRESETS).forEach(n => pr.appendChild(EDUI.btn(n, () => applyTextPreset(n)))); box.appendChild(pr);
  const g = mk('gcard');
  const add = n => g.appendChild(mk('crow')).append(n);
  add(EDUI.field('Font', selectCtl(TEXT_FONTS, st.font, v => setTextStyle('font', v))));
  add(EDUI.field('Size', EDUI.rangeCtl(2, 16, 0.1, st.size, v => v.toFixed(1) + '%', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.size = v; } }))));
  add(EDUI.field('Colour', colorCtl(st.color, v => setTextStyle('color', v))));
  add(EDUI.field('Outline', EDUI.rangeCtl(0, 0.2, 0.01, st.ow || 0, v => v.toFixed(2), (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.ow = v; } }), 'None')));
  add(EDUI.field('Outline colour', colorCtl(st.outline || '#000000', v => setTextStyle('outline', v))));
  add(EDUI.field('Background box', EDUI.toggleCtl(!!st.box, on => setTextStyle('box', on))));
  add(EDUI.field('Box opacity', EDUI.rangeCtl(0.1, 1, 0.05, st.boxOp == null ? 0.6 : st.boxOp, v => Math.round(v * 100) + '%', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.boxOp = v; } }))));
  add(EDUI.field('Capitals', EDUI.toggleCtl(!!st.upper, on => setTextStyle('upper', on))));
  add(EDUI.field('Highlight spoken word', EDUI.toggleCtl(!!st.hl, on => setTextStyle('hl', on ? '#FFD400' : ''))));
  if(st.hl) add(EDUI.field('Highlight colour', colorCtl(st.hl, v => setTextStyle('hl', v))));
  add(EDUI.field('Horizontal', EDUI.rangeCtl(0.1, 0.9, 0.01, st.x == null ? 0.5 : st.x, v => Math.round(v * 100) + '%', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.x = v; } }))));
  add(EDUI.field('Vertical', EDUI.rangeCtl(0.05, 0.95, 0.01, st.y == null ? 0.8 : st.y, v => Math.round(v * 100) + '%', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.y = v; } }))));
  add(EDUI.field('Fade in', EDUI.rangeCtl(0, 1, 0.05, st.fi || 0, v => v.toFixed(2) + ' s', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.fi = v; } }), 'Off')));
  add(EDUI.field('Fade out', EDUI.rangeCtl(0, 1, 0.05, st.fo || 0, v => v.toFixed(2) + ' s', (e, v) => sel.forEach(s => { const f = e.free.find(q => q.id === s.obj.id); if(f){ f.st = f.st || {}; f.st.fo = v; } }), 'Off')));
  box.appendChild(g);
  if(sel.length === 1 && o.auto) box.appendChild(EDUI.btn('Use this look for every caption', applyToAllCaptions));
}

/* the commands the toolbar and the Text tab share */
Editor.addText = addText; Editor.autoCaptions = autoCaptions;
