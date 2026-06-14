// agent-concurrency-probe — empirically measure the Workflow concurrent-agent cap.
// Fans out N agents; each stamps start/sleep/end; max overlapping interval = the
// real concurrent-slot count. Result on an 8-core M1: max_concurrent = 6 = min(16, cores-2).
// Run: Workflow({ name: "agent-concurrency-probe" })

export const meta = {
  name: 'agent-concurrency-probe',
  description: 'Empirically measure the Workflow concurrent-agent cap: fan out 24 agents, each stamps start/sleep/end, compute max interval overlap + wave structure',
  phases: [{ title: 'Probe' }, { title: 'Analyze' }],
}

const N = 24
const SLEEP = 6

const STAMP_SCHEMA = {
  type: 'object',
  required: ['start', 'end'],
  properties: {
    start: { type: 'number', description: 'epoch seconds at agent start' },
    end: { type: 'number', description: 'epoch seconds at agent end' },
  },
}

phase('Probe')
const stamps = await parallel(
  Array.from({ length: N }, (_, i) => () =>
    agent(
      `Run EXACTLY this one Bash command and report its two numbers, nothing else:\n` +
      `python3 -c "import time;s=time.time();time.sleep(${SLEEP});print(f'{s:.3f} {time.time():.3f}')"\n` +
      `Return start = first number, end = second number.`,
      { label: `probe#${i}`, phase: 'Probe', schema: STAMP_SCHEMA }
    ).then(r => ({ ...r, idx: i }))
  )
)

phase('Analyze')
const ok = stamps.filter(Boolean).filter(s => typeof s.start === 'number' && typeof s.end === 'number')
let maxConcurrent = 0
for (const a of ok) {
  const n = ok.filter(b => b.start < a.end && b.end > a.start).length
  if (n > maxConcurrent) maxConcurrent = n
}
const t0 = Math.min(...ok.map(s => s.start))
const waves = ok.map(s => Math.floor((s.start - t0) / SLEEP)).reduce((m, w) => { m[w] = (m[w] || 0) + 1; return m }, {})
const span = Math.max(...ok.map(s => s.end)) - t0
return {
  launched: N, returned: ok.length, sleep_s: SLEEP,
  max_concurrent: maxConcurrent,
  wave_sizes: waves,
  wall_span_s: Number(span.toFixed(2)),
  expected_cap: 'min(16, cores-2)',
  intervals: ok.map(s => ({ idx: s.idx, start: Number(s.start.toFixed(3)), end: Number(s.end.toFixed(3)) })),
}
