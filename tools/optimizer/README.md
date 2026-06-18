# Optimizer — CI Fleet Agent
Ultra-compresses all layers (5-10 rounds) on every PR.
Dogfeeds bidirectionally: reads diff, compresses, pushes back.
Configurable: `OPTIMIZER_ROUNDS` env (default 7).
GENESIS_SEAL: 7c242080
