import { useState, useEffect, useCallback } from "react";

export interface PeerNode {
  hostname: string;
  ipOrTailnet: string;
  role: string;
  platform: string;
  active: boolean;
  pingMs?: number;
}

export function useTailscaleDiscovery() {
  const [peers, setPeers] = useState<PeerNode[]>([
    { hostname: "dev-cx53", ipOrTailnet: "dev-cx53.tail2870dc.ts.net", role: "Dev Workstation & Honcho", platform: "NixOS x86_64", active: true, pingMs: 14 },
    { hostname: "hetzner", ipOrTailnet: "hetzner.tail2870dc.ts.net", role: "ARM64 Runner & BitNet Spider", platform: "NixOS aarch64", active: true, pingMs: 22 },
    { hostname: "public-services-host", ipOrTailnet: "167.233.105.32", role: "Mastodon & Forgejo Node", platform: "NixOS x86_64", active: true, pingMs: 18 },
    { hostname: "mbp", ipOrTailnet: "localhost", role: "M3 Workstation (Native)", platform: "aarch64-darwin", active: true, pingMs: 1 },
  ]);

  const [discovering, setDiscovering] = useState(false);

  const refreshPeers = useCallback(async () => {
    setDiscovering(true);
    // Simulate active peer ping check over Tailscale subnet
    await new Promise((r) => setTimeout(r, 600));
    setPeers((prev) =>
      prev.map((p) => ({
        ...p,
        active: true,
        pingMs: Math.floor(Math.random() * 15) + 10,
      }))
    );
    setDiscovering(false);
  }, []);

  useEffect(() => {
    refreshPeers();
  }, [refreshPeers]);

  return { peers, discovering, refreshPeers };
}
