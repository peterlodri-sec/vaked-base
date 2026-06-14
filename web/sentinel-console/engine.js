/* ============================================================
   vaked · sentinel console — engine (plain JS → window.VakedConsole)
   The graph IS the thesis: a swe_af swarm self-iterating on bare
   metal, CI agents (trigger + cron) + the ralph dogfooding loop,
   epochs jumping, the agent count racing 1M+ → singularity.
   ============================================================ */
(function () {
  const TAU = Math.PI * 2;
  const rand = (a, b) => a + Math.random() * (b - a);
  const pick = a => a[(Math.random() * a.length) | 0];

  // kind → [base, glow, glyph]   (Vaked node-kind system)
  const KIND = {
    runtime:    ['#7c3aed', '#a78bfa', '\u26a1'],
    fiber:      ['#ea580c', '#fb923c', '\ud83d\udd27'],
    index:      ['#0d9488', '#2dd4bf', '\ud83d\udcda'],
    stream:     ['#2563eb', '#60a5fa', '\u3030'],
    surface:    ['#16a34a', '#4ade80', '\ud83d\udda5'],
    mesh:       ['#dc2626', '#f87171', '\ud83d\udd78'],
    workflow:   ['#ca8a04', '#fbbf24', '\ud83d\udd00'],
    parallel:   ['#d97706', '#f59e0b', '\u29d6'],
    capability: ['#db2777', '#f472b6', '\ud83d\udd11'],
    memory:     ['#4f46e5', '#818cf8', '\ud83e\udde0'],
  };

  const VTYPE = { runtime: 'Runtime', fiber: 'Fiber<I,O>', index: 'Index<T>', stream: 'Stream<T>', surface: 'Surface', mesh: 'Membrane', workflow: 'Workflow', parallel: 'Parallel<DAG>', capability: 'Cap<R>', memory: 'Ledger' };
  const ETYPE = { runtime: 'Init', fiber: 'Frame', index: 'Hash', stream: 'Chunk', surface: 'Reveal', mesh: 'Egress', workflow: 'Spawn', parallel: 'Tick', capability: 'Grant', memory: 'Decision' };

  function fmt(n) {
    if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T';
    if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
    return String(Math.floor(n));
  }
  const comma = n => Math.floor(n).toLocaleString('en-US');

  function create(opts) {
    const gc = opts.graph, mc = opts.mesh;
    const gctx = gc.getContext('2d'), mctx = mc.getContext('2d');
    let W = 0, H = 0, cx = 0, cy = 0, dpr = Math.min(2, window.devicePixelRatio || 1);
    let accent = '#6366f1';

    const nodes = [], edges = [];
    let nid = 0, selected = null, running = false, raf = 0;

    // ---- persistent named nodes (the "team") ----
    function add(kind, label, file, x, y, r, fixed) {
      const n = { id: ++nid, kind, label, file, x, y, vx: 0, vy: 0, r: r || 6, born: performance.now(), grow: fixed ? 1 : 0, act: 0, pulse: 0, fixed: !!fixed, children: 0, nbrs: [] };
      nodes.push(n); return n;
    }
    function link(a, b, strong) { edges.push({ a, b, fresh: strong ? 1 : 0.0, flow: 0, strong: !!strong }); }

    // ---- hyper-opt animation state (baked sprites + traveling subagent sparks) ----
    let accentBright = '#a5b4fc', sparkColors = ['#6366f1', '#a5b4fc', '#818cf8'];
    let mediaReduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    let reduceMotion = mediaReduce;
    let glowCache = Object.create(null), edgeMap = Object.create(null), sparks = [], t = 0, last = 0;
    let simTarget = 0, simState = 'idle', simHold = 0, staticMode = false;
    function mixHex(h1, h2, a) { const p = x => [parseInt(x.slice(1, 3), 16), parseInt(x.slice(3, 5), 16), parseInt(x.slice(5, 7), 16)]; const c1 = p(h1), c2 = p(h2), m = i => Math.round(c1[i] + (c2[i] - c1[i]) * a), h = n => n.toString(16).padStart(2, '0'); return '#' + h(m(0)) + h(m(1)) + h(m(2)); }
    // bake each color's soft halo ONCE to an offscreen canvas → drawImage per frame (no per-frame gradients)
    function glowSprite(color) {
      let s = glowCache[color]; if (s) return s;
      const size = 96, mid = size / 2, c = document.createElement('canvas'); c.width = c.height = size;
      const gg = c.getContext('2d'), rg = gg.createRadialGradient(mid, mid, 0, mid, mid, mid);
      rg.addColorStop(0, hexA(color, 0.6)); rg.addColorStop(0.5, hexA(color, 0.12)); rg.addColorStop(1, hexA(color, 0));
      gg.fillStyle = rg; gg.fillRect(0, 0, size, size); glowCache[color] = c; return c;
    }
    function rebuildAdj() {
      for (const n of nodes) { if (!n.nbrs) n.nbrs = []; n.nbrs.length = 0; }
      edgeMap = Object.create(null);
      for (const e of edges) { e.a.nbrs.push(e.b); e.b.nbrs.push(e.a); edgeMap[e.a.id + '\u0001' + e.b.id] = e; edgeMap[e.b.id + '\u0001' + e.a.id] = e; }
    }
    function pickNbr(n) { const a = n.nbrs; return a && a.length ? a[(Math.random() * a.length) | 0] : n; }
    function spawnSpark() { const n = nodes[(Math.random() * nodes.length) | 0]; return { from: n, to: pickNbr(n), p: 0, speed: 0.5 + Math.random() * 1.0, col: sparkColors[(Math.random() * sparkColors.length) | 0] }; }
    function setSparkCount(k) { while (sparks.length < k) sparks.push(spawnSpark()); if (sparks.length > k) sparks.length = k; }
    function sparkStep(dt) {
      for (let i = 0; i < sparks.length; i++) {
        let s = sparks[i];
        if (!s.from || !s.to || s.from.dead || s.to.dead) { sparks[i] = s = spawnSpark(); }
        s.p += dt * s.speed;
        const e = edgeMap[s.from.id + '\u0001' + s.to.id]; if (e) e.flow = t + 0.6;
        if (s.p >= 1) { s.to.act = 1; s.from = s.to; s.p = 0; s.to = pickNbr(s.from); s.speed = 0.5 + Math.random() * 1.0; if (Math.random() < 0.06) { const ns = spawnSpark(); s.from = ns.from; s.to = ns.to; s.col = ns.col; } }
      }
    }
    function drawSparks() {
      for (const s of sparks) {
        if (!s.from || !s.to) continue;
        const ax = s.from.x, ay = s.from.y, bx = s.to.x, by = s.to.y;
        const e2 = s.p * s.p * (3 - 2 * s.p), x = ax + (bx - ax) * e2, y = ay + (by - ay) * e2;
        const e3 = Math.max(0, e2 - 0.14), tx = ax + (bx - ax) * e3, ty = ay + (by - ay) * e3;
        gctx.globalAlpha = 0.45; gctx.strokeStyle = s.col; gctx.lineWidth = 1.8; gctx.lineCap = 'round';
        gctx.beginPath(); gctx.moveTo(tx, ty); gctx.lineTo(x, y); gctx.stroke();
        gctx.globalAlpha = 0.7; gctx.drawImage(glowSprite(s.col), x - 7, y - 7, 14, 14);
        gctx.globalAlpha = 1; gctx.fillStyle = '#fff'; gctx.beginPath(); gctx.arc(x, y, 1.7, 0, TAU); gctx.fill();
      }
    }

    let apex, ralph, ciTrig, ciCron, guardd, eventd, surface;
    function seed() {
      apex = add('runtime', 'vakefield', 'flake.nix', cx, cy, 13, true);
      ciTrig = add('workflow', 'ci\u00b7trigger', 'agents/ci', cx - 150, cy - 70, 8, true);
      ciCron = add('parallel', 'ci\u00b7cron', 'agents/cron', cx - 150, cy + 70, 8, true);
      ralph = add('memory', 'ralph', 'tools/ralph', cx + 160, cy - 78, 8, true);
      eventd = add('index', 'eventd', 'eventd/', cx + 168, cy + 70, 8, true);
      guardd = add('mesh', 'agent-guardd', 'agent_guardd/', cx + 10, cy + 150, 7, true);
      surface = add('surface', 'console', 'surfaces/', cx - 12, cy - 150, 7, true);
      [ciTrig, ciCron, ralph, eventd, guardd, surface].forEach(n => link(apex, n, false));
      link(ralph, apex, false); link(eventd, ralph, false);
    }

    // ---- swarm growth ----
    const CAP = 116;
    function nearestTo(n, maxd) {
      let best = null, bd = maxd * maxd;
      for (const m of nodes) { if (m === n || m === n.parent) continue; const dx = m.x - n.x, dy = m.y - n.y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = m; } }
      return best;
    }
    function spawn(parent, kind) {
      // bias direction OUTWARD from center so the swarm branches/chains instead of forming flat radial flowers
      const ob = Math.atan2(parent.y - cy, parent.x - cx);
      const ang = (Math.random() < 0.62 ? ob : rand(0, TAU)) + rand(-0.85, 0.85);
      const d = rand(40, 92);
      const n = add(kind, 'swe_af#' + (agents | 0 % 100000), null,
        parent.x + Math.cos(ang) * d, parent.y + Math.sin(ang) * d, rand(3.4, 5.4), false);
      n.parent = parent; parent.children++;
      link(parent, n, true);
      // occasional cross-link to a nearby node → mesh / lattice, not pure star
      if (Math.random() < 0.26) { const near = nearestTo(n, 124); if (near) link(n, near, true); }
      n.pulse = 1;
      // recycle oldest leaf if over cap
      if (nodes.length > CAP) {
        for (let i = 0; i < nodes.length; i++) {
          const m = nodes[i];
          if (!m.fixed && m.children === 0 && m !== n) {
            m.dead = true; if (m.parent) m.parent.children--;
            nodes.splice(i, 1);
            for (let j = edges.length - 1; j >= 0; j--) if (edges[j].a === m || edges[j].b === m) edges.splice(j, 1);
            if (selected === m) { selected = null; opts.onSelect && opts.onSelect(null); }
            break;
          }
        }
      }
      return n;
    }

    // ---- stats (racing to singularity) ----
    let agents = 1024, epoch = 0, eventH = 0, agentsPerSec = 0, singularity = 0, lastSpawnable = null, phase = 'scaleup', phaseT = 0;
    function stats() {
      singularity = Math.min(99.4, Math.max(0, (Math.log10(agents) - 3) / 9 * 100));
      const phaseLabel = phase === 'scaleup' ? '\u2191 scaling up \u00b7 fan-out' : phase === 'scaledown' ? '\u2193 winding down \u00b7 finishing' : '\u25cf base services only';
      const kinds = {}; for (const kn of nodes) kinds[kn.kind] = (kinds[kn.kind] || 0) + 1;
      opts.onStats && opts.onStats({
        agents, agentsFmt: fmt(agents), agentsFull: comma(agents),
        epoch, nodes: nodes.length, edges: edges.length,
        aps: fmt(agentsPerSec), eventH, singularity: singularity.toFixed(1),
        phase, phaseLabel, kinds, simTarget, simState, staticMode,
      });
    }

    // ---- activity feed ----
    function evt(kind, sym, note, node) {
      opts.onEvent && opts.onEvent({
        kind, glyph: KIND[kind][2], color: KIND[kind][1], sym, note,
        etype: ETYPE[kind] || 'Event', vtype: VTYPE[kind] || 'T',
        ms: (rand(0.2, 9)).toFixed(1) + 'ms', node: node || null, t: Date.now(),
      });
    }

    const SWE = ['plan', 'code', 'review', 'publish', 'lower', 'check', 'enforce', 'testify'];
    function spawnOne() {
      const roll = Math.random();
      let parent, kind = 'fiber';
      if (roll < 0.30) { parent = ciTrig; ciTrig.pulse = 1; evt('workflow', 'ci\u00b7trigger', 'label agent \u2192 ' + pick(SWE)); }
      else if (roll < 0.52) { parent = ciCron; ciCron.pulse = 1; evt('parallel', 'ci\u00b7cron', 'tick \u00b7 ' + pick(SWE) + ' round-robin'); }
      else if (roll < 0.66) { parent = ralph; ralph.pulse = 1; evt('memory', 'ralph', 'decision appended \u00b7 ' + pick(['parallel', 'immutable', 'control']) + ' track'); link(ralph, apex, true); }
      else { parent = lastSpawnable || apex; }
      const child = spawn(parent, kind);
      lastSpawnable = Math.random() < 0.6 ? child : (pick(nodes.filter(n => !n.fixed)) || apex);
      child.label = 'swe_af#' + comma(Math.floor(agents) % 1000000);
      const r2 = Math.random();
      if (r2 < 0.34) { eventd.pulse = 1; eventH++; evt('index', 'eventd', 'append \u00b7 ' + hash(), eventd); }
      else if (r2 < 0.56) { guardd.pulse = 1; evt('mesh', 'agent-guardd', 'egress ' + pick(['allow', 'deny', 'deny']) + ' \u00b7 cgroup/skb', guardd); }
      else if (r2 < 0.74) { surface.pulse = 1; evt('surface', 'pr-review', 'advisory \u00b7 ' + pick(['+1', 'nit', 'spec\u2713'])); }
      else evt('fiber', child.label, pick(SWE) + ' \u2192 ' + pick(SWE), child);
      return child;
    }
    function finishLeaf() {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const m = nodes[i];
        if (!m.fixed && m.children === 0) {
          m.dead = true; if (m.parent) m.parent.children--;
          nodes.splice(i, 1);
          for (let j = edges.length - 1; j >= 0; j--) if (edges[j].a === m || edges[j].b === m) edges.splice(j, 1);
          if (selected === m) { selected = null; opts.onSelect && opts.onSelect(null); }
          return m;
        }
      }
      return null;
    }
    function tick() {
      phaseT++;
      if (staticMode) { setSparkCount(0); stats(); return; }
      if (simState !== 'idle') { simTick(); return; }
      if (phase === 'scaleup') {
        // SCALE UP + FAN OUT — accelerating bursts as singularity nears
        const burst = 1 + (Math.random() < 0.5 ? 1 : 0) + (singularity > 55 && Math.random() < 0.45 ? 1 : 0);
        for (let k = 0; k < burst; k++) spawnOne();
        agents *= rand(1.06, 1.30);
        agentsPerSec = agents * rand(0.06, 0.16);
        if (Math.random() < 0.55) epoch += Math.ceil(rand(2, 60) * (1 + singularity / 24));
        if (singularity > 93 || nodes.length > CAP - 5 || phaseT > 24) {
          phase = 'scaledown'; phaseT = 0; apex.pulse = 1;
          evt('runtime', 'vakefield', 'singularity reached \u00b7 winding down the swarm');
        }
      } else if (phase === 'scaledown') {
        // SCALE DOWN — agents finish + get reaped back to base services
        let fin = null;
        for (let k = 0; k < 6; k++) { const f = finishLeaf(); if (f) { fin = f; if (k < 2) evt('surface', f.label || 'swe_af', 'finished \u2713 \u00b7 reaped'); } }
        agents *= rand(0.62, 0.82);
        agentsPerSec = agents * rand(0.03, 0.09);
        if (nodes.filter(n => !n.fixed).length === 0) {
          phase = 'idle'; phaseT = 0; agents = Math.max(640, agents);
          [apex, ciTrig, ciCron, ralph, eventd, guardd, surface].forEach(n => n.pulse = 0.6);
          evt('surface', 'sentinel', 'agents all finished \u00b7 sentinel + base services only');
        }
      } else {
        // IDLE — only the sentinel + base services remain
        if (Math.random() < 0.5) { eventd.pulse = 1; eventH++; evt('index', 'eventd', 'idle heartbeat \u00b7 ' + hash(), eventd); }
        if (phaseT > 4) { phase = 'scaleup'; phaseT = 0; ciTrig.pulse = 1; evt('workflow', 'ci\u00b7trigger', 'new epoch \u00b7 scaling up + fan-out'); }
      }
      const target = reduceMotion ? 0 : (phase === 'scaleup' ? Math.min(18, 5 + Math.round(singularity / 7)) : phase === 'scaledown' ? 3 : 1);
      setSparkCount(target);
      stats();
    }
    function hash() { return Array.from({ length: 7 }, () => '0123456789abcdef'[(Math.random() * 16) | 0]).join(''); }

    // ---- physics + render ----
    function step(ts) {
      const dt = last ? Math.min(0.05, (ts - last) / 1000) : 0.016; last = ts || performance.now(); t += dt;
      rebuildAdj();
      for (const gn of nodes) if (gn.grow < 1) gn.grow = Math.min(1, gn.grow + dt * 2.4);
      // forces: repulsion (light), spring to parent, pull to center
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]; if (a.fixed) continue;
        let fx = 0, fy = 0;
        for (let j = 0; j < nodes.length; j++) {
          if (i === j) continue; const b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01;
          if (d2 < 9000) { const f = 220 / d2; fx += dx * f; fy += dy * f; }
        }
        if (a.parent) { const dx = a.parent.x - a.x, dy = a.parent.y - a.y, d = Math.hypot(dx, dy) || 1, k = (d - 74) * 0.012; fx += dx / d * k * 60; fy += dy / d * k * 60; }
        fx += (cx - a.x) * 0.0016; fy += (cy - a.y) * 0.0016;
        a.vx = (a.vx + fx * 0.016) * 0.86; a.vy = (a.vy + fy * 0.016) * 0.86;
        a.x += a.vx; a.y += a.vy;
      }
      if (sparks.length) sparkStep(dt);
      draw();
      if (sparks.length) drawSparks();
      if (running) raf = requestAnimationFrame(step);
    }

    function draw() {
      gctx.globalAlpha = 1;
      gctx.clearRect(0, 0, W, H);
      // singularity core glow (baked sprite, scaled)
      const cr = 120 + singularity * 1.8;
      gctx.globalAlpha = 0.035 + singularity / 900;
      gctx.drawImage(glowSprite('#7c3aed'), cx - cr, cy - cr, cr * 2, cr * 2);
      gctx.globalAlpha = 1;
      // edges (slight bow + flow pulse where a spark is travelling)
      for (const e of edges) {
        if (e.fresh > 0) e.fresh *= 0.93;
        const ax = e.a.x, ay = e.a.y, bx = e.b.x, by = e.b.y;
        const mx = (ax + bx) / 2, my = (ay + by) / 2;
        let nx = -(by - ay), ny = (bx - ax); const nl = Math.hypot(nx, ny) || 1; nx /= nl; ny /= nl;
        const flowing = e.flow > t;
        gctx.beginPath(); gctx.moveTo(ax, ay); gctx.quadraticCurveTo(mx + nx * 9, my + ny * 9, bx, by);
        if (flowing) { gctx.strokeStyle = hexA(accent, 0.5); gctx.lineWidth = 1.4; }
        else if (e.fresh > 0.05) { gctx.strokeStyle = hexA(accent, 0.3 + e.fresh * 0.45); gctx.lineWidth = 1.3; }
        else { gctx.strokeStyle = 'rgba(120,134,170,0.16)'; gctx.lineWidth = 0.8; }
        gctx.stroke();
        if (flowing) { const fp = (t * 0.6 + e.a.id * 0.13) % 1; const px = ax + (bx - ax) * fp, py = ay + (by - ay) * fp; gctx.fillStyle = hexA(accentBright, 0.9); gctx.beginPath(); gctx.arc(px, py, 1.8, 0, TAU); gctx.fill(); }
      }
      // nodes
      for (const n of nodes) {
        if (n.pulse > 0.001) n.pulse *= 0.955; else n.pulse = 0;
        if (n.act > 0.001) n.act *= 0.93; else n.act = 0;
        const [b, g] = KIND[n.kind];
        const grow = n.grow < 1 ? n.grow : 1;
        const R = n.r * (1 + n.pulse * 0.08 + n.act * 0.28) * grow;
        if (R < 0.4) continue;
        if (n.act > 0.02) { gctx.strokeStyle = hexA(accent, n.act * 0.4); gctx.lineWidth = 1.2; gctx.beginPath(); gctx.arc(n.x, n.y, R + (1 - n.act) * 18, 0, TAU); gctx.stroke(); }
        const gr = R * 3.1 + n.act * 10;
        gctx.globalAlpha = Math.min(1, 0.18 + n.pulse * 0.14 + n.act * 0.28);
        gctx.drawImage(glowSprite(n.act > 0.05 ? accent : g), n.x - gr, n.y - gr, gr * 2, gr * 2);
        gctx.globalAlpha = 1;
        gctx.fillStyle = g; gctx.beginPath(); gctx.arc(n.x, n.y, R, 0, TAU); gctx.fill();
        gctx.fillStyle = b; gctx.beginPath(); gctx.arc(n.x, n.y, R * 0.45, 0, TAU); gctx.fill();
        if (n === selected) { gctx.strokeStyle = '#fff'; gctx.lineWidth = 1.5; gctx.beginPath(); gctx.arc(n.x, n.y, R + 5, 0, TAU); gctx.stroke(); }
        if (n.fixed) { gctx.fillStyle = 'rgba(226,232,240,0.85)'; gctx.font = '9px ' + mono(); gctx.textAlign = 'center'; gctx.fillText(n.label, n.x, n.y + R + 13); }
      }
    }
    function hexA(hex, a) { const h = hex.replace('#', ''); const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16); return `rgba(${r},${g},${b},${a})`; }
    function mono() { return getComputedStyle(document.body).getPropertyValue('--font-mono') || 'monospace'; }

    function drawMesh() {
      mctx.clearRect(0, 0, W, H); mctx.strokeStyle = 'rgba(124,140,200,0.06)'; mctx.lineWidth = 1;
      const s = 46;
      for (let y = 0; y < H + s; y += s) for (let x = 0; x < W + s; x += s) {
        const ox = (Math.floor(y / s) % 2) * s / 2;
        mctx.beginPath(); mctx.arc(x + ox, y, 1.1, 0, TAU); mctx.fillStyle = 'rgba(124,140,200,0.10)'; mctx.fill();
      }
    }

    function resize() {
      W = gc.clientWidth; H = gc.clientHeight; cx = W * 0.42; cy = H * 0.5;
      [gc, mc].forEach(c => { c.width = W * dpr; c.height = H * dpr; });
      gctx.setTransform(dpr, 0, 0, dpr, 0, 0); mctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (apex) { apex.x = cx; apex.y = cy; }
      drawMesh(); draw();
    }

    // ---- public ----
    let timer = 0;
    function start() {
      if (running) return; running = true; resize(); if (!apex) seed(); rebuildAdj(); setSparkCount(6); draw(); stats();
      raf = requestAnimationFrame(step);
      timer = setInterval(function () { tick(); if (running) draw(); }, 760);
      for (let i = 0; i < 14; i++) setTimeout(tick, i * 90);
    }
    function stop() { running = false; cancelAnimationFrame(raf); clearInterval(timer); }
    function setAccent(hex) { accent = hex; accentBright = mixHex(hex, '#ffffff', 0.42); sparkColors = [hex, accentBright, mixHex(hex, '#ffffff', 0.2)]; glowCache = Object.create(null); }
    function selectAt(clientX, clientY) {
      const r = gc.getBoundingClientRect();
      const mx = (clientX - r.left) / (r.width || 1) * W, my = (clientY - r.top) / (r.height || 1) * H;
      let best = null, bd = 26 * 26;
      for (const n of nodes) { const dx = n.x - mx, dy = n.y - my, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = n; } }
      selected = best; opts.onSelect && opts.onSelect(best ? snapshot(best) : null); return best;
    }
    function snapshot(n) {
      const ins = edges.filter(e => e.b === n).length, outs = edges.filter(e => e.a === n).length;
      return { id: n.id, kind: n.kind, label: n.label, file: n.file || (n.kind + '/' + n.label.replace(/[#\u00b7]/g, '-') + '.vaked'), fanIn: ins, fanOut: outs };
    }

    // ---- terminal ----
    const L = (...seg) => seg; // line = array of [cls,text]
    function command(raw) {
      const s = raw.trim(); const [cmd, ...args] = s.split(/\s+/);
      const out = [];
      const ok = (...l) => out.push(...l);
      switch ((cmd || '').toLowerCase()) {
        case '': break;
        case 'help':
          ok(L(['tk-dim', 'commands']),
            L(['tk-bin', 'swarm'], ['tk-dim', '            agent swarm + singularity readout']),
            L(['tk-bin', 'vaked'], ['tk-arg', ' graph'], ['tk-dim', '      capability graph stats']),
            L(['tk-bin', 'ralph'], ['tk-arg', ' status'], ['tk-dim', '    dogfooding decision loop']),
            L(['tk-bin', 'eventd'], ['tk-arg', ' tail'], ['tk-dim', '     recent hash-chain appends']),
            L(['tk-bin', 'vakedc'], ['tk-arg', ' check <file>'], ['tk-dim', '  run the front-end']),
            L(['tk-bin', 'clear'])); break;
        case 'clear': return { clear: true };
        case 'swarm': case 'scale':
          ok(L(['tk-acc', 'swe_af'], ['tk-dim', ' swarm \u00b7 bare-metal vakefield']),
            L(['tk-dim', '  agents     '], ['tk-bin', comma(agents)], ['tk-num', '  (\u2191 self-iterating)']),
            L(['tk-dim', '  epoch      '], ['tk-bin', comma(epoch)]),
            L(['tk-dim', '  singularity'], ['tk-acc', '  ' + singularity.toFixed(1) + '%']),
            L(['tk-ok', '  \u2192 to singularity'])); break;
        case 'vaked':
          if (args[0] === 'graph') ok(L(['tk-bin', comma(nodes.length)], ['tk-dim', ' nodes \u00b7 '], ['tk-bin', comma(edges.length)], ['tk-dim', ' edges']), L(['tk-dim', '  apex '], ['tk-kw', 'runtime'], ['tk-arg', ' vakefield']));
          else ok(L(['tk-err', 'usage: vaked graph'])); break;
        case 'ralph':
          ok(L(['tk-bin', 'ralph'], ['tk-dim', ' \u00b7 budget-capped decision loop']),
            L(['tk-kw', 'parallel'], ['tk-dim', '  round-robins tracks']),
            L(['tk-kw', 'immutable'], ['tk-dim', ' append-only ledger']),
            L(['tk-kw', 'control'], ['tk-dim', '   pause / slow / step'])); break;
        case 'eventd':
          if (args[0] === 'tail') { for (let i = 0; i < 4; i++) ok(L(['tk-num', comma(eventH - i)], ['tk-punct', '  '], ['tk-str', hash() + hash()], ['tk-dim', '  testified'])); }
          else ok(L(['tk-err', 'usage: eventd tail'])); break;
        case 'vakedc':
          if (args[0] === 'check') {
            const f = args[1] || 'agentfield-swe.vaked';
            ok(L(['tk-dollar', '$ '], ['tk-bin', 'vakedc'], ['tk-arg', ' check ' + f]),
              L(['tk-ok', '\u2713 clean'], ['tk-dim', '  \u00b7 0 errors \u00b7 0 warnings \u00b7 LPG ok']));
          } else ok(L(['tk-err', 'usage: vakedc check <file>'])); break;
        default: ok(L(['tk-err', 'unknown: ' + cmd], ['tk-dim', '  \u2014 try '], ['tk-arg', 'help']));
      }
      return { lines: out };
    }

    function simTick() {
      if (simState === 'ramp') {
        for (let k = 0; k < 3; k++) spawnOne();
        agents *= 1.6;
        if (agents >= simTarget) { agents = simTarget; simState = 'hold'; simHold = 0; apex.pulse = 1; evt('runtime', 'vakefield', 'fan-out target reached · holding at ' + fmt(simTarget)); }
      } else if (simState === 'hold') {
        simHold++; if (Math.random() < 0.55) spawnOne();
        agents = simTarget * (0.96 + Math.random() * 0.07);
        if (simHold > 8) { simState = 'descale'; evt('surface', 'sentinel', 'descaling the swarm → base services'); }
      } else {
        for (let k = 0; k < 6; k++) finishLeaf();
        agents *= 0.6;
        if (nodes.filter(n => !n.fixed).length === 0) { simState = 'idle'; simTarget = 0; agents = Math.max(640, agents); phase = 'scaleup'; phaseT = 0; }
      }
      agentsPerSec = agents * rand(0.06, 0.2);
      epoch += Math.ceil(rand(6, 90));
      setSparkCount(reduceMotion ? 0 : 16);
      stats();
    }
    function setReduceMotion(on) { reduceMotion = mediaReduce || !!on; if (reduceMotion) sparks.length = 0; }
    function setStatic(on) {
      staticMode = !!on;
      if (on) { let guard = 0; while (nodes.length < CAP && guard++ < 400) spawnOne(); sparks.length = 0; agents = Math.max(agents, 10000); }
      stats();
    }
    function simulateFanout(N) { simTarget = Math.max(1000, N | 0); simState = 'ramp'; simHold = 0; staticMode = false; phase = 'scaleup'; phaseT = 0; }
    function vakedFile() {
      const f = Math.max(1, Math.floor(agents));
      return `runtime vakefield {
  fiber swe_af {
    engine = claude
    input  = stream.issues
    output = artifacts.pr
  }
  parallel "swarm" {
    fibers     = swe_af × ${comma(f)}
    strategy   = "supervised-dag"
    supervisor = otp
    epoch      = ${comma(epoch)}
  }
  index   eventd       { source = hash-chain }
  mesh    agent-guardd { enforce = ebpf · "deny-default" }
  surface console      { reveal = graph }
}`;
    }

    window.addEventListener('resize', resize);
    return { start, stop, setAccent, selectAt, command, resize, getKinds: () => KIND, setReduceMotion, setStatic, simulateFanout, vakedFile,
      _dbg: () => ({ W, H, cw: gc.width, clientW: gc.clientWidth, clientH: gc.clientHeight, n: nodes.length, sample: nodes.slice(0, 5).map(n => ({ x: Math.round(n.x), y: Math.round(n.y), k: n.kind, l: n.label })) }) };
  }

  window.VakedConsole = { create };
})();
