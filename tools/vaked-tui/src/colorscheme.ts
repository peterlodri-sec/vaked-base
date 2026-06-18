// tools/vaked-tui/src/main.ts — colorscheme block
// GENESIS_SEAL 7c242080 — DOD re-skin. Flat array len 3, indexed by profile. No classes.

export interface Colorscheme {
  name: string;
  bg: string;
  accent: string;
  fg: string;
}

// Flat array, indexed by profile rawValue: 0, 1, 2.
export const COLORSCHEMES: Colorscheme[] = [
  { name: "denseMatrixGreen", bg: "#040804", accent: "#00e660", fg: "#c8f5c8" },
  { name: "cleanGraphCyberpunk", bg: "#0a0a14", accent: "#00d4ff", fg: "#e0e8f5" },
  { name: "tacticalGraveyard", bg: "#141414", accent: "#b0b0b0", fg: "#d4d4d4" },
];

export function colorschemeFor(profile: number): Colorscheme {
  const n = COLORSCHEMES.length;
  const idx = ((profile % n) + n) % n;
  return COLORSCHEMES[idx];
}
