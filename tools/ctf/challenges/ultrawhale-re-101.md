# CTF Challenge: ultrawhale RE 101

> Part of the RE + Audit Pipeline. Prove you understand the code.

## Challenge

The ultrawhale binary (`bin/ultrawhale`) contains a function called `ASCIIBox`
that renders pixel-perfect ASCII boxes. Your goal:

1. Locate `ASCIIBox` in the binary using `crabcc lookup sym ASCIIBox`
2. Identify what the `width` parameter does
3. Submit: the minimum and maximum allowed width values

## Hints

- `crabcc lookup refs ASCIIBox` shows 12 call sites
- The function signature is in `internal/blocks/ascii_box.go`

## Flag

```
flag{asciibox-min20-max80}
```

## Points

100 points. Category: reverse-engineering.

## Verification

```bash
crabcc lookup sym ASCIIBox
# Expected: 12 references, signature shows width clamping
```
