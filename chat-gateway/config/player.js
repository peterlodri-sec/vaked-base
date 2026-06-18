// Vaked-FM Console — OvenPlayer + Canvas Avatar
// Genesis-seeded · Web Audio · sub-second WebRTC

const GENESIS = "7c242080";

// ── Player init ──────────────────────────────────────────────────────────
const player = OvenPlayer.create("ovenplayer-container", {
    sources: [{ type: "webrtc", file: "wss://radio.vaked.dev:3334/app/stream" }],
    autoStart: true,
    mute: false,
});

// ── Audio analysis ───────────────────────────────────────────────────────
let audioCtx, analyser, dataArray;

player.on("ready", () => {
    const videoEl = document.querySelector("video");
    if (!videoEl) return;
    
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    
    const source = audioCtx.createMediaElementSource(videoEl);
    source.connect(analyser);
    analyser.connect(audioCtx.destination);
    
    dataArray = new Uint8Array(analyser.frequencyBinCount);
});

// ── Visualization: map frequency data to avatar ──────────────────────────
function getBassLevel() {
    if (!analyser || !dataArray) return 0;
    analyser.getByteFrequencyData(dataArray);
    return dataArray.slice(0, 8).reduce((a, b) => a + b, 0) / (8 * 255);
}

function getTrebleLevel() {
    if (!analyser || !dataArray) return 0;
    analyser.getByteFrequencyData(dataArray);
    const mid = Math.floor(dataArray.length / 2);
    return dataArray.slice(mid).reduce((a, b) => a + b, 0) / (mid * 255);
}

// ── Expose for Canvas avatar ────────────────────────────────────────────
window.vakedRadio = {
    getBassLevel,
    getTrebleLevel,
    genesis: GENESIS,
};
