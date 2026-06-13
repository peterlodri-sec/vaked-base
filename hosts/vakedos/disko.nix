# hosts/vakedos/disko.nix — declarative disk layout for the vakedos host.
#
# Vultr bare metal is Legacy PCBIOS only (no EFI), so each disk carries a 1 MiB
# BIOS-boot partition (type EF02) for GRUB plus a ZFS partition. The two ZFS
# partitions form a mirrored `rpool`. Consumed by disko via the flake and applied
# by nixos-anywhere at install time.
#
# BEFORE INSTALL: replace the two `device` placeholders with the box's real
# stable disk paths — `ssh root@<IP> ls -l /dev/disk/by-id` and use the
# `/dev/disk/by-id/...` names (never /dev/sdX, which is not stable).
{
  disko.devices = {
    disk = {
      disk1 = {
        type = "disk";
        device = "/dev/disk/by-id/REPLACE-WITH-DISK-1-ID";
        content = {
          type = "gpt";
          partitions = {
            boot = {
              size = "1M";
              type = "EF02"; # BIOS boot partition (Legacy/GRUB; Vultr has no EFI)
            };
            zfs = {
              size = "100%";
              content = {
                type = "zfs";
                pool = "rpool";
              };
            };
          };
        };
      };
      disk2 = {
        type = "disk";
        device = "/dev/disk/by-id/REPLACE-WITH-DISK-2-ID";
        content = {
          type = "gpt";
          partitions = {
            boot = {
              size = "1M";
              type = "EF02";
            };
            zfs = {
              size = "100%";
              content = {
                type = "zfs";
                pool = "rpool";
              };
            };
          };
        };
      };
    };

    zpool = {
      rpool = {
        type = "zpool";
        mode = "mirror";
        options.ashift = "12";
        rootFsOptions = {
          compression = "zstd";
          acltype = "posixacl";
          xattr = "sa";
          atime = "off";
          mountpoint = "none";
          "com.sun:auto-snapshot" = "false";
        };

        datasets = {
          root = {
            type = "zfs_fs";
            mountpoint = "/";
          };
          nix = {
            type = "zfs_fs";
            mountpoint = "/nix";
            options."com.sun:auto-snapshot" = "false";
          };
          var = {
            type = "zfs_fs";
            mountpoint = "/var";
          };
          home = {
            type = "zfs_fs";
            mountpoint = "/home";
          };
          # Dedicated Nix build scratch — keeps large EPYC builds off the root
          # dataset. configuration.nix points the builder's TMPDIR here.
          build = {
            type = "zfs_fs";
            mountpoint = "/build";
            options = {
              "com.sun:auto-snapshot" = "false";
              recordsize = "1M"; # large, write-once build artifacts
              # Throwaway scratch: skip sync writes (a crash just re-runs the
              # build) and use the cheaper compressor — big build-throughput win.
              sync = "disabled";
              compression = "lz4";
            };
          };
          # Runtime state plane for the membrane daemons (docs/runtime/README.md).
          # eventd's append-only, hash-chained audit spine and memoryd's mined
          # memory plane live here; ZFS checksums back the tamper-evidence story,
          # and snapshots are kept (auto-snapshot on) for audit history.
          "var/lib/vaked" = {
            type = "zfs_fs";
            mountpoint = "/var/lib/vaked";
            options."com.sun:auto-snapshot" = "true";
          };
          # Unmounted reservation so the pool never reaches 100% (a full ZFS pool
          # wedges writes). Sized as headroom, not for data.
          reserved = {
            type = "zfs_fs";
            options = {
              mountpoint = "none";
              reservation = "10G";
            };
          };
        };
      };
    };
  };
}
