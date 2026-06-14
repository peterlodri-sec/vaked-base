# protocol/hcp/

HCP wire protocol implementation — WP3 (Jun 24–Oct 15 2026).

- Spec: [`../rfcs/0001-hcp.md`](../rfcs/0001-hcp.md) (and 0002–0007)
- Plan: [`../../docs/superpowers/plans/2026-06-14-wp3-kickoff.md`](../../docs/superpowers/plans/2026-06-14-wp3-kickoff.md)

## Layout

```
hcpbin/   Rust crate — binary codec (RFC 0002)  [WP3-S1]
litany/   Rust crate — frame + routing layer     [WP3-S2+]
```

Build target: `dev-cx53` via `nix develop`.
