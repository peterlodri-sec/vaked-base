# nix-darwin fragment — Ollama local inference server for M3 Pro 46GB
# Add to your nix-darwin configuration.nix or flake's darwinModules.
#
# Usage:
#   darwin-rebuild switch --flake .#your-host
#
# After switch: ollama is a launchd service (auto-start on login).
# API endpoint: http://localhost:11434  (OpenAI-compat at /v1/chat/completions)

{ pkgs, ... }:

{
  services.ollama = {
    enable = true;
    acceleration = "metal";           # Apple GPU via Metal Performance Shaders
    listenAddress = "127.0.0.1:11434";

    # Models to pull on first start. Both fit in 46GB together (~49GB peak, use swap).
    # Swap to smaller variants if you run other memory-heavy apps simultaneously.
    models = [
      "llama3.3:70b-instruct-q4_K_M"  # ~40GB — primary bench target
      "qwen2.5:14b-instruct"           # ~9GB  — secondary bench target
    ];

    # Environment — increase keep-alive so models stay loaded between bench calls
    environmentVariables = {
      OLLAMA_KEEP_ALIVE = "30m";
      OLLAMA_MAX_LOADED_MODELS = "1";  # swap between models; prevents OOM
      OLLAMA_NUM_PARALLEL = "1";
    };
  };

  # Optional: expose on LAN (e.g. for dev-cx53 to call back to your M3)
  # Change listenAddress to "0.0.0.0:11434" and add firewall rule if needed.
}
