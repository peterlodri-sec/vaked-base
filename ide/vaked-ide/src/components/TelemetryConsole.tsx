import React, { useEffect, useState, useRef } from 'react';

export interface TelemetryLogMessage {
  id: string;
  timestamp: string;
  node: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
  latencyMs?: number;
}

export const TelemetryConsole: React.FC = () => {
  const [logs, setLogs] = useState<TelemetryLogMessage[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Initial mock telemetry entries for demonstration
    const initialLogs: TelemetryLogMessage[] = [
      { id: '1', timestamp: new Date().toISOString(), node: 'portail.vaked.dev', level: 'INFO', message: 'Tokio WebSocket Telemetry Streamer initialized', latencyMs: 14 },
      { id: '2', timestamp: new Date().toISOString(), node: 'axiomquant.org', level: 'INFO', message: 'KaTeX 0.16.9 Math Engine rendering Monographs 1-13', latencyMs: 18 },
      { id: '3', timestamp: new Date().toISOString(), node: 'art.vaked.dev', level: 'INFO', message: 'OSC-9000 Oscilloscope trace visualizer active', latencyMs: 12 },
    ];
    setLogs(initialLogs);
    setIsConnected(true);

    // Try connecting to Rust Tokio WebSocket telemetry server
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket('ws://localhost:8080/telemetry');
      socket.onopen = () => setIsConnected(true);
      socket.onmessage = (event) => {
        if (isPaused) return;
        try {
          const data = JSON.parse(event.data);
          const newEntry: TelemetryLogMessage = {
            id: Math.random().toString(36).substring(2, 9),
            timestamp: data.timestamp || new Date().toISOString(),
            node: data.node || 'constellation-fleet',
            level: data.level || 'INFO',
            message: data.message || 'Node heartbeat received',
            latencyMs: data.latencyMs || Math.floor(Math.random() * 20) + 10
          };
          setLogs((prev) => [...prev.slice(-100), newEntry]);
        } catch {
          // Fallback parsing
        }
      };
      socket.onerror = () => setIsConnected(false);
      socket.onclose = () => setIsConnected(false);
    } catch {
      setIsConnected(false);
    }

    return () => {
      if (socket) socket.close();
    };
  }, [isPaused]);

  useEffect(() => {
    if (!isPaused && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isPaused]);

  return (
    <div className="flex flex-col h-full bg-zinc-950 border border-purple-500/20 rounded-xl overflow-hidden font-mono text-xs shadow-2xl">
      {/* Header Bar */}
      <div className="flex justify-between items-center px-4 py-2.5 bg-zinc-900/80 border-b border-purple-500/20">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-500'}`} />
          <span className="font-bold text-zinc-200">VAKED SENTINEL TELEMETRY STREAM</span>
          <span className="text-[10px] text-zinc-500">ws://localhost:8080/telemetry</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setIsPaused(!isPaused)}
            className="px-2.5 py-1 text-[10px] rounded bg-zinc-800 border border-zinc-700 text-zinc-300 hover:text-white"
          >
            {isPaused ? '▶ RESUME' : '⏸ PAUSE'}
          </button>
          <button
            onClick={() => setLogs([])}
            className="px-2.5 py-1 text-[10px] rounded bg-zinc-800 border border-zinc-700 text-zinc-300 hover:text-white"
          >
            🗑 CLEAR
          </button>
        </div>
      </div>

      {/* Log Output Stream */}
      <div className="flex-1 p-3 overflow-y-auto space-y-1.5 bg-black/60">
        {logs.map((log) => (
          <div key={log.id} className="flex gap-2 items-start text-[11px] leading-relaxed hover:bg-zinc-900/40 p-1 rounded">
            <span className="text-zinc-500 text-[10px] shrink-0">{log.timestamp.substring(11, 19)}</span>
            <span className="text-teal-400 font-semibold shrink-0 w-32 truncate">{log.node}</span>
            <span className={`px-1.5 py-0.5 text-[9px] rounded font-bold shrink-0 ${
              log.level === 'INFO' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/30' :
              log.level === 'WARN' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30' :
              'bg-red-500/10 text-red-400 border border-red-500/30'
            }`}>
              {log.level}
            </span>
            <span className="text-zinc-300 flex-1">{log.message}</span>
            {log.latencyMs && (
              <span className="text-amber-400 text-[10px] shrink-0">{log.latencyMs} ms</span>
            )}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>
    </div>
  );
};

export default TelemetryConsole;
