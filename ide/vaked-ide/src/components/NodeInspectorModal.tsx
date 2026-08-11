import React from 'react';

export interface ConstellationNodeDetails {
  id: string;
  name: string;
  url: string;
  rssUrl: string;
  sitemapUrl: string;
  sslStatus: string;
  simdConfig: string;
  latencyMs: number;
}

interface NodeInspectorModalProps {
  node: ConstellationNodeDetails | null;
  onClose: () => void;
}

export const NodeInspectorModal: React.FC<NodeInspectorModalProps> = ({ node, onClose }) => {
  if (!node) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-zinc-950 border border-purple-500/30 rounded-xl p-6 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex justify-between items-center border-b border-purple-500/20 pb-3">
          <div>
            <span className="text-[10px] font-mono text-teal-400 uppercase tracking-widest">CONSTELLATION INSPECTOR</span>
            <h2 className="text-lg font-bold text-zinc-100 font-mono">{node.name}</h2>
          </div>
          <button
            onClick={onClose}
            className="px-2.5 py-1 text-xs font-mono rounded bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white"
          >
            ✕ ESC
          </button>
        </div>

        {/* Overview */}
        <div className="space-y-3 font-mono text-xs">
          <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80 space-y-1.5">
            <div className="text-[10px] text-zinc-500 uppercase">Endpoint Details</div>
            <div className="text-teal-400 font-semibold truncate">{node.url}</div>
            <div className="flex justify-between text-zinc-400 text-[11px]">
              <span>SSL: <strong className="text-emerald-400">{node.sslStatus}</strong></span>
              <span>Latency: <strong className="text-amber-400">{node.latencyMs} ms</strong></span>
            </div>
          </div>

          {/* RSS & Syndication */}
          <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80 space-y-1.5">
            <div className="text-[10px] text-zinc-500 uppercase">RSS & Syndication</div>
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-400">RSS 2.0 Feed:</span>
              <a href={node.rssUrl} target="_blank" rel="noreferrer" className="text-purple-400 hover:underline">{node.rssUrl}</a>
            </div>
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-400">XML Sitemap:</span>
              <a href={node.sitemapUrl} target="_blank" rel="noreferrer" className="text-purple-400 hover:underline">{node.sitemapUrl}</a>
            </div>
          </div>

          {/* SIMD Kernel Config */}
          <div className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-800/80 space-y-1.5">
            <div className="text-[10px] text-zinc-500 uppercase">SIMD Matrix Operator</div>
            <div className="text-zinc-300 text-[11px] font-mono">{node.simdConfig}</div>
          </div>
        </div>

        {/* Footer */}
        <div className="pt-2 text-right">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-mono font-bold rounded-lg bg-teal-400 text-black hover:bg-teal-300 transition-colors"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeInspectorModal;
