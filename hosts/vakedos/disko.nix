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
            options."com.sun:auto-snapshot" = "false";
          };
        };
      };
    };
  };
}
