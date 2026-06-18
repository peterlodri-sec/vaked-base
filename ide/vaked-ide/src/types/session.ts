export type SessionKind = "human" | "a2a" | "gateway";

export type AgentRole =
  | "user"
  | "openrouter"
  | "deepseek"
  | "claude"
  | "gemini"
  | "schema-advisor"
  | "capability-expert"
  | "lowering-guide"
  | "a2a-peer";

export interface TextRange {
  startLine: number;
  startCol: number;
  endLine: number;
  endCol: number;
}

export interface GraphPatch {
  addedNodes: string[];
  removedNodes: string[];
  addedEdges: Array<{ from: string; to: string; label: string }>;
  removedEdges: Array<{ from: string; to: string; label: string }>;
  modifiedNodeProps: Array<{ id: string; props: Record<string, unknown> }>;
}

export interface SuggestedEdit {
  range: TextRange;
  newText: string;
  rationale: string;
}

export interface SessionMessage {
  id: string;
  role: AgentRole;
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  graphPatch?: GraphPatch;
  suggestedEdit?: SuggestedEdit;
}

export interface GatewayRoute {
  routedTo: AgentRole;
  rationale: string;
}

export interface Session {
  id: string;
  kind: SessionKind;
  label: string;
  messages: SessionMessage[];
  activeAgents: AgentRole[];
  yjsRoomId?: string;
  createdAt: number;
  lastRoute?: GatewayRoute;
}

export const AGENT_LABELS: Record<AgentRole, string> = {
  "user": "You",
  "openrouter": "OpenRouter",
  "deepseek": "DeepSeek V4",
  "claude": "Claude Opus",
  "gemini": "Gemini Flash",
  "schema-advisor": "Schema Advisor",
  "capability-expert": "Capability Expert",
  "lowering-guide": "Lowering Guide",
  "a2a-peer": "Agent Peer",
};

export const AGENT_COLORS: Record<AgentRole, string> = {
  "user": "#6366f1",
  "openrouter": "#f97316",
  "deepseek": "#10b981",
  "claude": "#f97316",
  "gemini": "#3b82f6",
  "schema-advisor": "#14b8a6",
  "capability-expert": "#a855f7",
  "lowering-guide": "#22c55e",
  "a2a-peer": "#3b82f6",
};
