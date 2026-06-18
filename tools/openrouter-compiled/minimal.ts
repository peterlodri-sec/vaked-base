"use strict";

/**
 * Minimal compiled entry point for the Vaked agent.
 * Only the APIs actually used by the agent SDK are imported.
 * Designed for deno compile / bun build --compile + strip.
 *
 * GENESIS_SEAL: 7c242080
 */

// Only import what we need — tree-shaking removes the rest
import { createVakedAgent } from "../openrouter-ts/dist/index.js";

async function main() {
  const prompt = Deno?.args?.[0] ?? process?.argv?.[2] ?? "Hello";
  const model = Deno?.args?.[1] ?? process?.argv?.[3] ?? "deepseek";

  const agent = createVakedAgent({ context7: false, langfuse: false });
  const answer = await agent.ask(prompt, model);
  console.log(answer);
}

main().catch((err) => {
  console.error("vaked:", err.message);
  // Don't use process.exit — Deno doesn't have it
  if (typeof process !== "undefined") process.exit(1);
  else throw err;
});
