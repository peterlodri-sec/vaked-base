import React from 'react';

interface LatencySparklineProps {
  history: number[];
  width?: number;
  height?: number;
  label?: string;
}

export const LatencySparkline: React.FC<LatencySparklineProps> = ({
  history,
  width = 180,
  height = 40,
  label = "portail-vaked-dev"
}) => {
  if (!history || history.length === 0) {
    return <div className="text-xs text-zinc-500 font-mono">No telemetry...</div>;
  }

  const min = Math.min(...history);
  const max = Math.max(...history);
  const range = max - min || 1;
  const current = history[history.length - 1];

  const points = history.map((val, idx) => {
    const x = (idx / (history.length - 1 || 1)) * width;
    const y = height - ((val - min) / range) * (height - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  return (
    <div className="flex flex-col gap-1 p-2 rounded-lg bg-zinc-900/80 border border-purple-500/20 backdrop-blur-md">
      <div className="flex justify-between items-center text-[10px] font-mono text-zinc-400">
        <span className="font-semibold text-teal-400">{label}</span>
        <span className="text-amber-400 font-bold">{current} ms</span>
      </div>
      
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          <linearGradient id="sparkline-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#62e6c9" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#b48bff" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        
        <polyline
          fill="none"
          stroke="#62e6c9"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          points={points}
        />
      </svg>
      
      <div className="flex justify-between text-[9px] font-mono text-zinc-500">
        <span>min: {min}ms</span>
        <span>max: {max}ms</span>
      </div>
    </div>
  );
};

export default LatencySparkline;
