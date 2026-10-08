// Temporary look-dev helpers (not part of the page): contact sheets of
// autopilot views, rendered synchronously and drawn onto an overlay canvas.
window.innerWidth = 1280; window.innerHeight = 720;
window._pilotUpdate = fc.pilot.update;
window._rand = Math.random;
fc.S.flow = false; fc.S.quality = 1; fc.S.autoQ = false;
document.getElementById('panel').classList.add('hidden');

window.shoot = (configs, cols = 4) => {
  const W = 1280, H = 720, rows = Math.ceil(configs.length / cols), tw = W / cols, th = H / rows;
  let ov = document.getElementById('sheet');
  if (!ov) {
    ov = document.createElement('canvas');
    ov.id = 'sheet';
    ov.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:10';
    document.body.append(ov);
  }
  ov.style.display = 'block'; ov.width = W; ov.height = H;
  const c2 = ov.getContext('2d');
  c2.fillStyle = '#000'; c2.fillRect(0, 0, W, H);
  fc.pilot.update = () => {};
  const out = [];
  configs.forEach((cfg, i) => {
    Object.assign(fc.SCENES[cfg.scene], cfg.set || {});
    Object.assign(fc.S, cfg.S || {});
    const sc = fc.SCENES[cfg.scene];
    fc.director.cur = fc.director.form(cfg.scene); fc.director.next = fc.director.form((cfg.scene + 1) % 3); fc.director.x = 0; fc.director.w = 0; fc.director.sc = null; fc.director.applyFractal(0);
    if (cfg.seed !== undefined) { let s = cfg.seed; Math.random = () => (s = (s * 16807) % 2147483647) / 2147483647; }
    fc.pilot.reset(sc); fc.flies.list = [];
    for (let k = 0; k < (cfg.fly ?? 5) * 30; k++) {
      fc.director.applyFractal(1 / 30);
      window._pilotUpdate.call(fc.pilot, 1 / 30, 1, sc);
      fc.flies.update(1 / 30);
      if (k % 45 === 0) fc.flies.spawn([1, 0.6, 0.3], 1);
    }
    Math.random = window._rand;
    fc.renderer.histOk = false;
    const now = performance.now() / 1000;
    const R = fc.director.update(0, now, fc.analysis.f, fc.clock.update(now));
    R.veil = 0;
    Object.assign(R, cfg.R || {});
    for (let k = 0; k < 16; k++) fc.renderer.render(R, now + k / 60);
    c2.drawImage(fc.renderer.gl.canvas, (i % cols) * tw, Math.floor(i / cols) * th, tw, th);
    c2.fillStyle = '#fff'; c2.font = '15px sans-serif';
    c2.fillText(i + ' ' + (cfg.label || ''), (i % cols) * tw + 6, Math.floor(i / cols) * th + 18);
    out.push(i + ':' + fc.pilot.d0.toFixed(3) + '/' + fc.pilot.focus.toFixed(2));
  });
  fc.pilot.update = window._pilotUpdate;
  return out.join(' ');
};

// the standard sheet: four views of each scene
window.std = (extra = {}) => {
  const cfgs = [];
  for (let sc = 0; sc < 3; sc++) {
    for (let k = 0; k < 4; k++) cfgs.push({ scene: sc, label: fc.SCENES[sc].name, fly: 4 + k * 2, seed: 11 + sc * 10 + k, ...extra });
  }
  return shoot(cfgs);
};
window.hideSheet = () => { const ov = document.getElementById('sheet'); if (ov) ov.style.display = 'none'; };

// a strip through one growth: form `from` with `to` growing out of it
window.growStrip = (from, to, n = 8, seed = 22, fly = 6, k = 1.5) => {
  const W = 1280, H = 720, cols = 4, rows = Math.ceil(n / cols), tw = W / cols, th = H / rows;
  let ov = document.getElementById('sheet');
  if (!ov) { ov = document.createElement('canvas'); ov.id = 'sheet'; ov.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:10'; document.body.append(ov); }
  ov.style.display = 'block'; ov.width = W; ov.height = H;
  const c2 = ov.getContext('2d'); c2.fillStyle = '#000'; c2.fillRect(0, 0, W, H);
  const D = fc.director;
  D.cur = D.form(from); D.next = D.form(to); D.x = 0; D.w = 0; D.sc = null; D.applyFractal(0);
  let s = seed; Math.random = () => (s = (s * 16807) % 2147483647) / 2147483647;
  fc.pilot.reset(fc.SCENES[from]); fc.flies.list = [];
  for (let j = 0; j < fly * 30; j++) { D.applyFractal(1 / 30); window._pilotUpdate.call(fc.pilot, 1 / 30, 1, fc.SCENES[from]); }
  Math.random = window._rand;
  // the same form: a copy scaled by k about the camera grows in
  if (from === to) { const c = fc.pilot.pos; D.next = D.form(from, 1 / k, c.map(v => v * (1 - 1 / k))); }
  fc.pilot.update = () => {};
  const out = [];
  for (let i = 0; i < n; i++) {
    D.x = i / (n - 1) * 0.999;
    D.w = D.x - 0.6 * Math.sin(2 * Math.PI * D.x) / (2 * Math.PI);
    D.sc = blendScene(D.cur.sc, D.next.sc, D.w);
    D.applyFractal(0.5);
    for (let k = 0; k < 20; k++) window._pilotUpdate.call(fc.pilot, 0.05, 1, D.sc);
    fc.renderer.histOk = false;
    const now = performance.now() / 1000, sc = D.sc;
    for (let k = 0; k < 16; k++) fc.renderer.render({ speedK: 0, core: sc.core, key: sc.keyCol, fog: sc.fog * 1.3, flies: 1, exposure: 1, fov: 58 * Math.PI / 180, roll: 0 }, now + k / 60);
    c2.drawImage(fc.renderer.gl.canvas, (i % cols) * tw, Math.floor(i / cols) * th, tw, th);
    c2.fillStyle = '#fff'; c2.font = '15px sans-serif';
    c2.fillText(`${fc.SCENES[from].name}→${from === to ? 'itself x' + k : fc.SCENES[to].name} ${(D.w * 100).toFixed(0)}%`, (i % cols) * tw + 6, Math.floor(i / cols) * th + 18);
    out.push(`${i}: d0=${fc.pilot.d0.toFixed(3)} vis=${fc.de(fc.pilot.pos).toFixed(3)}`);
  }
  fc.pilot.update = window._pilotUpdate;
  return out.join(' | ');
};
