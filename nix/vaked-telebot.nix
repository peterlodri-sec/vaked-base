# NixOS module for vaked-telebot — the interactive Telegram control surface.
#
# Exposed from the flake as nixosModules.vaked-telebot (which also defaults the
# `package` to the flake's packages.<system>.vaked-telebot). On a NixOS host:
#
#   imports = [ inputs.vaked.nixosModules.vaked-telebot ];
#   services.vaked-telebot = {
#     enable = true;
#     environmentFile = config.sops.secrets.vaked-telebot.path;   # sops-nix / agenix
#   };
#
# The daemon is stdlib-only; the package is just python3 + the repo's tools/eventd
# subtree, so the closure is tiny. Runs unprivileged (DynamicUser) with the secrets
# as a systemd credential (never in the process env) and the full sandbox set.
{ config, lib, ... }:
let
  cfg = config.services.vaked-telebot;
in
{
  options.services.vaked-telebot = {
    enable = lib.mkEnableOption "vaked-telebot, the interactive Telegram control surface for the Vaked agent fleet";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The vaked-telebot package (a python3 wrapper around tools/telebot/telebot.py).";
    };

    environmentFile = lib.mkOption {
      type = lib.types.path;
      description = ''
        Path to a KEY=VALUE secrets file loaded as a systemd credential (tmpfs,
        0400 — never in the process environment). Keys: TELEGRAM_TOKEN, TELEGRAM_TO,
        TELEGRAM_ADMIN_IDS, GITHUB_TOKEN, GITHUB_REPOSITORY, OPENROUTER_API_KEY,
        and optionally TELEBOT_MODEL. Manage it with sops-nix or agenix.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.vaked-telebot = {
      description = "vaked-telebot — interactive Telegram control surface for the agent fleet";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        ExecStart = "${cfg.package}/bin/vaked-telebot";
        # Unprivileged + private state dir (the daemon writes its ledger/offset here).
        DynamicUser = true;
        StateDirectory = "vaked-telebot";
        Environment = [ "TELEBOT_STATE_DIR=%S/vaked-telebot" ];
        # Secrets as a credential → $CREDENTIALS_DIRECTORY/telebot.env (read by
        # telebot._load_credentials). Never in the process env / `systemctl show`.
        LoadCredential = [ "telebot.env:${cfg.environmentFile}" ];
        Restart = "on-failure";
        RestartSec = 5;

        # Sandboxing — a network daemon holding API tokens gets the full set.
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        CapabilityBoundingSet = "";
        AmbientCapabilities = "";
        SystemCallFilter = [ "@system-service" ];
        SystemCallErrorNumber = "EPERM";
      };
    };
  };
}
