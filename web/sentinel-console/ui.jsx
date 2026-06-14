/* vaked · sentinel console — React UI (chrome) */
const { useState, useEffect, useRef } = React;
const DS = window.VakedDesignSystem_ca2818 || {};
const KindBadge = DS.KindBadge || (({ kind, label }) => <span className="chip">{kind} {label || ''}</span>);
const Badge = DS.Badge || (({ children }) => <span className="chip">{children}</span>);

const ACCENTS = [['indigo', '#6366f1'], ['violet', '#7c3aed'], ['orange', '#f97316'], ['teal', '#0d9488']];
const TEAM = { workflow: 'ci · trigger', parallel: 'ci · cron', memory: 'ralph', index: 'eventd', mesh: 'agent-guardd', surface: 'surfaces', fiber: 'swe_af swarm', runtime: 'vakefield' };

function Seg({ s }) { return <span className={s[0]}>{s[1]}</span>; }

function Terminal({ sim, onClose }) {
  const [lines, setLines] = useState([
    { segs: [['tk-acc', 'vaked'], ['tk-dim', ' sentinel console \u2014 bare-metal vakefield']] },
    { segs: [['tk-dim', 'type '], ['tk-arg', 'help'], ['tk-dim', ' \u00b7 try '], ['tk-arg', 'swarm']] },
  ]);
  const [val, setVal] = useState('');
  const [h, setH] = useState(230);
  const [min, setMin] = useState(false);
  const bodyRef = useRef(null), inRef = useRef(null), drag = useRef(null);
  useEffect(() => { if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; }, [lines]);

  function run(e) {
    e.preventDefault();
    const raw = val; setVal('');
    if (!raw.trim()) return;
    const res = sim.command(raw);
    if (res.clear) { setLines([]); return; }
    setLines(l => [...l, { segs: [['tk-dollar', '$ '], ['tk-arg', raw]], cmd: true }, ...(res.lines || []).map(segs => ({ segs }))]);
  }
  function onDown(e) { drag.current = { y: e.clientY, h }; e.target.setPointerCapture(e.pointerId); }
  function onMove(e) { if (drag.current) setH(Math.max(120, Math.min(440, drag.current.h + (drag.current.y - e.clientY)))); }
  function onUp() { drag.current = null; }

  return (
    <div className="term-wrap">
      <div className="term-rz term-rz-t" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}></div>
      <div className="terminal">
        <div className="t-bar">
          <span className="t-dot r"></span><span className="t-dot y"></span><span className="t-dot g"></span>
          <span className="t-title">vakedc · ~/vakefield</span>
          <span className="t-spacer"></span>
          <button className="t-win" title="minimize" onClick={() => setMin(m => !m)}>{min ? '▢' : '–'}</button>
          <button className="t-win" title="close" onClick={() => onClose && onClose()}>✕</button>
        </div>
        {!min && <div className="t-body" ref={bodyRef} style={{ '--term-h': h + 'px' }} onClick={() => inRef.current && inRef.current.focus()}>
          {lines.map((l, i) => (
            <div className={'t-line' + (l.cmd ? ' t-cmd' : '')} key={i}>
              {l.segs.map((s, j) => <Seg s={s} key={j} />)}
            </div>
          ))}
          <form className="t-prompt" onSubmit={run}>
            <span className="tk-dollar">$&nbsp;</span>
            <input className="t-input" ref={inRef} value={val} onChange={e => setVal(e.target.value)}
              placeholder="enter a command…" autoFocus spellCheck="false" autoComplete="off" />
          </form>
        </div>}
      </div>
    </div>
  );
}

function Inspector({ sel }) {
  if (!sel) return (
    <div className="rail-sec inspector">
      <div className="rail-head"><span className="eyebrow">inspector</span></div>
      <div className="insp-empty">No node selected — click any node in the swarm, or any row in live activity, to inspect it.</div>
    </div>
  );
  if (sel.isEvent) return (
    <div className="rail-sec inspector">
      <div className="rail-head"><span className="eyebrow">inspector</span><Badge variant="success">◉ event</Badge></div>
      <div className="insp-top">
        <div><div className="insp-name">{sel.label}</div><div className="insp-file">{sel.note}</div></div>
        <KindBadge kind={sel.kind} />
      </div>
      <div className="insp-stats">
        <div className="insp-stat"><b>{sel.ms}</b><span>latency</span></div>
        <div className="insp-stat"><b style={{ fontSize: 13 }}>{sel.kind}</b><span>kind</span></div>
      </div>
      <div className="insp-grp"><div className="insp-lbl">trace</div><div className="insp-chips"><span className="chip">testified → eventd</span><span className="chip">live</span></div></div>
    </div>
  );
  const caps = { runtime: ['parallel', 'supervised-dag', 'otp'], fiber: ['plan', 'code', 'review', 'publish'], workflow: ['trigger', 'gha', 'advisory'], parallel: ['cron', 'round-robin'], memory: ['append-only', 'ratified'], index: ['hash-chain', 'testify'], mesh: ['cgroup/skb', 'deny-default'], surface: ['reveal'] }[sel.kind] || ['typed'];
  return (
    <div className="rail-sec inspector">
      <div className="rail-head"><span className="eyebrow">inspector</span><Badge variant="success">◉ live</Badge></div>
      <div className="insp-top">
        <div><div className="insp-name">{sel.label}</div><div className="insp-file">{sel.file}</div></div>
        <KindBadge kind={sel.kind} />
      </div>
      <div className="insp-stats">
        <div className="insp-stat"><b>{sel.fanIn}</b><span>fan-in</span></div>
        <div className="insp-stat"><b>{sel.fanOut}</b><span>fan-out</span></div>
        <div className="insp-stat"><b>{sel.id}</b><span>node id</span></div>
      </div>
      <div className="insp-grp">
        <div className="insp-lbl">capabilities</div>
        <div className="insp-chips">{caps.map((c, i) => <span className="chip" key={i}>{c}</span>)}</div>
      </div>
    </div>
  );
}

const TOUR = [
  { t: 'what is vaked?', center: true, b: <span>vaked is a flake-native <b>capability-graph language</b> for agentic, native, mesh-aware, parallel systems. This console watches it run live — a <b>swe_af</b> agent swarm self-iterating on bare metal, every step testified to the eventd hash chain.</span> },
  { t: 'the swarm', area: 'graph', b: <span>Each glowing node is a capability — <b>runtime, fiber, index, mesh…</b> CI agents (trigger + cron) and the <b>ralph</b> loop spawn fibers that fan out, then finish and get reaped. Click any node to inspect it.</span> },
  { t: 'scale → singularity', sel: '.meter', b: <span>Watch the cycle: the swarm <b>scales up + fans out</b> as agents race and epochs jump, hits singularity, then <b>winds down</b> to “sentinel + base services only” before the next epoch. Swatches retint the console.</span> },
  { t: 'live activity', sel: '.rail .activity', b: <span>Every spawn, CI trigger, ralph decision, eventd append and guardd enforcement streams here — the freshest row flashes, then settles. Click a row to inspect the event.</span> },
  { t: 'inspector', sel: '.inspector', b: <span>Select a node — or a live-activity row — for its <b>kind badge</b>, fan-in / fan-out, source file and capabilities.</span> },
  { t: 'the terminal', sel: '.term-wrap', b: <span>Drive <b>vakedc</b> by hand — try <b>help</b>, <b>swarm</b>, <b>vaked graph</b>, <b>ralph status</b>, <b>eventd tail</b>. Drag the top edge to resize.</span> },
];
function tourRect(s) {
  const pad = 8;
  if (s.area === 'graph') {
    const railW = window.innerWidth > 880 ? 320 : 0;
    return { left: 10, top: 62, width: Math.max(180, window.innerWidth - railW - 20), height: Math.max(160, window.innerHeight - 212) };
  }
  if (s.sel) { const el = document.querySelector(s.sel); if (el) { const r = el.getBoundingClientRect(); return { left: r.left - pad, top: r.top - pad, width: r.width + pad * 2, height: r.height + pad * 2 }; } }
  return null;
}
function cardPos(rect) {
  if (!rect) return { left: '50%', top: '50%', transform: 'translate(-50%,-50%)' };
  const cardW = 344, cardH = 230, gap = 12;
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - cardW - 12);
  let top = rect.top + rect.height + gap;
  if (top + cardH > window.innerHeight - 12) top = Math.max(12, rect.top - cardH - gap);
  return { left, top };
}
function Tour({ onClose }) {
  const [i, setI] = useState(0);
  const [, force] = useState(0);
  useEffect(() => { const h = () => force(x => x + 1); window.addEventListener('resize', h); const id = setTimeout(h, 60); return () => { window.removeEventListener('resize', h); clearTimeout(id); }; }, [i]);
  const s = TOUR[i];
  const rect = s.center ? null : tourRect(s);
  const cardStyle = s.center ? { left: '50%', top: '50%', transform: 'translate(-50%,-50%)' } : cardPos(rect);
  return (
    <div>
      {s.center || !rect ? <div className="tour-dim" onClick={onClose}></div> : <div className="tour-ring" style={rect}></div>}
      <div className="tour-card" style={cardStyle}>
        <div className="tour-step">{i + 1} / {TOUR.length} · guided tour</div>
        <h3>{s.t}</h3>
        <p>{s.b}</p>
        <div className="tour-dots">{TOUR.map((_, j) => <i key={j} className={j === i ? 'on' : ''}></i>)}</div>
        <div className="tour-btns">
          <button className="tour-skip" onClick={onClose}>skip</button>
          <span style={{ flex: 1 }}></span>
          {i > 0 && <button className="tour-ghost" onClick={() => setI(i - 1)}>back</button>}
          <button className="tour-next" onClick={() => i < TOUR.length - 1 ? setI(i + 1) : onClose()}>{i < TOUR.length - 1 ? 'next' : 'enter console'}</button>
        </div>
      </div>
    </div>
  );
}

function Toggle({ on, set, label }) {
  return (
    <button className={'twk-toggle' + (on ? ' on' : '')} onClick={() => set(!on)}>
      <span className="twk-knob"></span><span>{label}</span>
    </button>
  );
}
function fanLabel(n) { return n >= 1e6 ? (n / 1e6).toFixed(n % 1e6 ? 1 : 0) + 'm' : (n / 1e3).toFixed(0) + 'k'; }
function Tweaks({ onClose, accent, chooseAccent, reduce, toggleReduce, staticG, toggleStatic, fanN, setFanN, runSim, show, setShow, vaked }) {
  const toSlider = n => Math.round((Math.log10(n) - 4) / 3 * 1000);
  const fromSlider = v => { const x = Math.pow(10, 4 + v / 1000 * 3); return Math.max(10000, Math.round(x / 1000) * 1000); };
  return (
    <div className="twk-panel">
      <div className="twk-head"><span className="twk-ttl">tweaks</span><button className="twk-x" onClick={onClose}>✕</button></div>
      <div className="twk-body">
        <div className="twk-sec">accent</div>
        <div className="twk-swatches">
          {ACCENTS.map(([n, hex]) => <button key={hex} title={n} onClick={() => chooseAccent(hex)} className={'twk-sw' + (accent === hex ? ' on' : '')} style={{ background: hex }}></button>)}
        </div>
        <div className="twk-sec">motion</div>
        <Toggle on={reduce} set={toggleReduce} label="reduce motion" />
        <Toggle on={staticG} set={toggleStatic} label="static · full fan-out (10k)" />
        <div className="twk-sec">simulate fan-out</div>
        <input type="range" min="0" max="1000" value={toSlider(fanN)} onChange={e => setFanN(fromSlider(+e.target.value))} className="twk-range" />
        <div className="twk-fanrow"><span className="twk-fanval">{fanLabel(fanN)}</span><button className="twk-go" onClick={runSim}>▸ simulate</button></div>
        <div className="twk-fanhint">ramp swe_af swarm → hold at N → descale</div>
        <div className="twk-sec">panels</div>
        <Toggle on={show.legend} set={v => setShow(s => ({ ...s, legend: v }))} label="legend" />
        <Toggle on={show.activity} set={v => setShow(s => ({ ...s, activity: v }))} label="live activity" />
        <Toggle on={show.terminal} set={v => setShow(s => ({ ...s, terminal: v }))} label="terminal" />
        <div className="twk-sec">live · .vaked</div>
        <pre className="twk-vaked"><code>{vaked}</code></pre>
      </div>
    </div>
  );
}

function App() {
  const graphRef = useRef(null), meshRef = useRef(null), simRef = useRef(null);
  const [events, setEvents] = useState([]);
  const [stats, setStats] = useState({ agentsFmt: '1.0k', agentsFull: '1,024', epoch: 0, nodes: 0, edges: 0, aps: '0', singularity: '0.0', eventH: 0 });
  const [sel, setSel] = useState(null);
  const [accent, setAccent] = useState('#6366f1');
  const [ready, setReady] = useState(false);
  const [tour, setTour] = useState(false);
  const [tw, setTw] = useState(false);
  const [show, setShow] = useState({ legend: true, activity: true, terminal: true });
  const [reduce, setReduce] = useState(false);
  const [staticG, setStaticG] = useState(false);
  const [fanN, setFanN] = useState(100000);
  const [vaked, setVaked] = useState('');

  useEffect(() => {
    const sim = window.VakedConsole.create({
      graph: graphRef.current, mesh: meshRef.current,
      onEvent: ev => setEvents(list => [{ ...ev, id: ev.t + '-' + Math.random() }, ...list].slice(0, 26)),
      onStats: setStats,
      onSelect: setSel,
    });
    simRef.current = sim; sim.setAccent(accent); sim.start(); setReady(true); window.__sim = sim;
    try { if (!localStorage.getItem('vaked.tour.v1')) setTour(true); } catch (e) {}
    const vk = setInterval(() => { try { setVaked(sim.vakedFile()); } catch (e) {} }, 700);
    return () => { sim.stop(); clearInterval(vk); };
  }, []);

  function onGraphClick(e) {
    simRef.current && simRef.current.selectAt(e.clientX, e.clientY);
  }
  function chooseAccent(hex) {
    setAccent(hex); document.documentElement.style.setProperty('--accent', hex);
    simRef.current && simRef.current.setAccent(hex);
  }
  function endTour() { setTour(false); try { localStorage.setItem('vaked.tour.v1', '1'); } catch (e) {} }
  function pickEvent(ev) { setSel({ isEvent: true, kind: ev.kind, label: ev.sym, note: ev.note, ms: ev.ms }); }
  function toggleReduce(v) { setReduce(v); simRef.current && simRef.current.setReduceMotion(v); }
  function toggleStatic(v) { setStaticG(v); simRef.current && simRef.current.setStatic(v); }
  function runSim() { simRef.current && simRef.current.simulateFanout(fanN); }

  return (
    <React.Fragment>
      <canvas className="layer mesh" ref={meshRef}></canvas>
      <canvas className="layer graph" ref={graphRef} onClick={onGraphClick}></canvas>

      <header className="hdr">
        <div className="hdr-brand">
          <img className="hdr-logo" src={(window.__resources && window.__resources.logo) || 'assets/logo-mark.png'} alt="vaked" />
          <div className="hdr-word"><span className="wm">vaked</span><span className="wm-sub">sentinel console</span></div>
        </div>
        <div className="hdr-mid">
          <span className="hud"><span className="hud-bolt">⚡</span> agents <b>{stats.agentsFmt}</b> <span style={{ color: 'var(--color-text-dimmed)' }}>{stats.phaseLabel || '↑ self-iterating'}</span></span>
          <span className="hdr-tag">bare-metal · vakefield · EPYC 4345P</span>
        </div>
        <div className="hdr-right">
          <button className="tour-help" onClick={() => setTw(true)}>⚙ tweaks</button>
          <button className="tour-help" onClick={() => setTour(true)}>? tour</button>
          <div style={{ display: 'flex', gap: 5 }}>
            {ACCENTS.map(([n, hex]) => (
              <button key={hex} title={n} onClick={() => chooseAccent(hex)}
                style={{ width: 16, height: 16, borderRadius: 4, border: accent === hex ? '2px solid #e2e8f0' : '1px solid #374151', background: hex, cursor: 'pointer', padding: 0 }}></button>
            ))}
          </div>
          <div className="meter"><span className="meter-val">{stats.singularity}%</span><span className="meter-lbl">→ singularity</span></div>
          <div className="conn"><span className="conn-dot"></span> live</div>
        </div>
      </header>

      {!tour && show.legend && <div className="legend">
        <div className="lg-eye">the swarm</div>
        <div className="lg-copy">A <b>swe_af</b> agent swarm self-iterating on bare metal — CI agents (<b>trigger</b> + <b>cron</b>) and the <b>ralph</b> dogfooding loop spawn fibers, every step <b>testified</b> to eventd. Epochs jump; the count races <b>→ singularity</b>.</div>
        <div className="lg-keys">
          <span className="lg-key"><i style={{ background: '#a78bfa' }}></i>runtime</span>
          <span className="lg-key"><i style={{ background: '#fb923c' }}></i>fiber</span>
          <span className="lg-key"><i style={{ background: '#fbbf24' }}></i>workflow</span>
          <span className="lg-key"><i style={{ background: '#f59e0b' }}></i>parallel</span>
          <span className="lg-key"><i style={{ background: '#818cf8' }}></i>memory</span>
          <span className="lg-key"><i style={{ background: '#2dd4bf' }}></i>index</span>
          <span className="lg-key"><i style={{ background: '#f87171' }}></i>mesh</span>
          <span className="lg-key"><i style={{ background: '#4ade80' }}></i>surface</span>
        </div>
        <div className="lg-foot">click a node to inspect · drag terminal top-edge to resize</div>
      </div>}

      <aside className="rail">
        {show.activity && <div className="rail-sec activity">
          <div className="rail-head"><span className="eyebrow">live activity</span><span className="live-tag"><i></i> streaming</span></div>
          <div className="act-list">
            {(function () {
              var m = new Map();
              events.forEach(function (ev) {
                var k = ev.kind;
                if (!m.has(k)) m.set(k, { kind: k, glyph: ev.glyph, color: ev.color, team: TEAM[k] || k, count: 0, last: ev });
                var g = m.get(k); g.count++; if (ev.t >= g.last.t) g.last = ev;
              });
              var groups = Array.from(m.values()).sort(function (a, b) { return b.last.t - a.last.t; });
              return groups.map(function (g) {
                return (
                  <div className="act-row team-row fresh" key={g.kind + ':' + g.last.id} onClick={function () { pickEvent(g.last); }}>
                    <span className="act-glyph" style={{ color: g.color }}>{g.glyph}</span>
                    <span className="act-sym">{g.team} <small>{g.last.note}</small></span>
                    <span className="team-count" title={g.count + ' recent events'}>×{g.count}</span>
                  </div>
                );
              });
            })()}
          </div>
        </div>}
        <Inspector sel={sel} />
      </aside>

      {ready && show.terminal && <Terminal sim={simRef.current} onClose={() => setShow(s => ({ ...s, terminal: false }))} />}
      {tour && <Tour onClose={endTour} />}
      {tw && <Tweaks onClose={() => setTw(false)} accent={accent} chooseAccent={chooseAccent} reduce={reduce} toggleReduce={toggleReduce} staticG={staticG} toggleStatic={toggleStatic} fanN={fanN} setFanN={setFanN} runSim={runSim} show={show} setShow={setShow} vaked={vaked} />}

      <footer className="status">
        <span className="st st-lsp">◉ vakedc-lsp</span>
        <span className="st sep">·</span>
        <span className="st ok"><em>✓ clean</em></span>
        <span className="st sep">·</span>
        <span className="st"><b>{stats.nodes}</b> nodes · <b>{stats.edges}</b> edges</span>
        <span className="st sep">·</span>
        <span className="st">epoch <b>{(stats.epoch || 0).toLocaleString('en-US')}</b></span>
        <span className="st spacer"></span>
        <span className="st">eventd <b>{stats.eventH}</b></span>
        <span className="st sep">·</span>
        <span className="st">≈ <b>{stats.aps}</b> agents/s</span>
        <span className="st sep">·</span>
        <span className="st">agents <b>{stats.agentsFull}</b></span>
      </footer>
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
