# vaked-ide — native terminal via libghostty

> Status: **scaffold** (subsystem spec + feature-gated implementation).
> Owner decision 2026-06-13: embed the real Ghostty terminal surface
> (`libghostty`), not xterm.js. Ghostty is Zig — it sits naturally next to
> the rest of the Vaked stack ("Zig enforces").

## The constraint that shapes everything

The published `libghostty` **C embedding API** (`include/ghostty.h`) only
exposes two platform tags:

```c
typedef enum {
  GHOSTTY_PLATFORM_INVALID,
  GHOSTTY_PLATFORM_MACOS,   // ghostty_platform_macos_s { void* nsview; }
  GHOSTTY_PLATFORM_IOS,     // ghostty_platform_ios_s   { void* uiview; }
} ghostty_platform_e;
```

There are **no X11 / Wayland platform structs in the C header** — Ghostty's
Linux build drives surfaces through its internal GTK apprt, which is not
reachable from the C embedding API. Windows has no Ghostty backend at all.

So "true native libghostty embedding" is, today, a **macOS-first**
capability. This subsystem is built to match that reality honestly:

| Platform | Terminal backend |
|----------|------------------|
| macOS    | **embedded `libghostty` surface** (native NSView overlay) |
| Linux    | fallback: "Open in Ghostty" launches an external Ghostty window (when on `PATH`); pane shows the rationale |
| Windows  | fallback: external `$TERMINAL`; pane shows the rationale |

The embedded path is compiled only under `--features ghostty` **and**
`target_os = "macos"`. The feature is **OFF by default** so the existing
crate, CI, and non-macOS builds are unaffected.

## Why an overlay, not a webview widget

Tauri renders the UI in a `WKWebView` (macOS) inside an `NSWindow`.
`libghostty` does not draw into the DOM — it owns a Metal-backed `NSView`
and renders the terminal grid on the GPU itself. The only correct way to
combine them is a **native child view layered over the webview**:

```
NSWindow
└─ contentView (WKWebView, the React UI)
   └─ <child NSView>  ← handed to ghostty_surface_new(.nsview)
      libghostty draws the terminal grid here (Metal)
```

The webview reserves a transparent rectangle (the `<TerminalPane>` DOM
node). The frontend reports that rectangle's screen bounds to the backend
(`terminal_set_bounds`) on every resize/scroll; the backend keeps the child
`NSView`'s frame in lockstep. The native surface therefore *appears* to be a
pane inside the IDE while actually floating above the webview.

## AppKit threading

Every `libghostty` / AppKit call must run on the **main thread**. Tauri
commands run on a worker pool, so all surface operations are marshalled via
`AppHandle::run_on_main_thread(...)`. The `ghostty_runtime_config_s.wakeup_cb`
schedules a `ghostty_app_tick` back onto the main thread.

## Module layout (`src-tauri/src/`)

```
terminal/
  mod.rs        always compiled — re-exports; picks impl by cfg
  ffi.rs        #[cfg(ghostty)] raw `extern "C"` bindings to ghostty.h
  runtime.rs    #[cfg(macos+ghostty)] GhosttyRuntime: init/app/surface lifecycle + callbacks
  macos.rs      #[cfg(macos+ghostty)] NSView child overlay + frame tracking
commands/
  terminal.rs   TerminalState + #[tauri::command]s (stable names on every platform;
                fall back to an "unavailable" error when the embed path is off)
```

Stable command surface (same names on every target):

| Command | Purpose |
|---------|---------|
| `terminal_available` | `{ embedded: bool, reason: string }` — lets the UI decide pane vs. fallback |
| `terminal_open`      | create the app (once) + a surface in `cwd`; returns a surface id |
| `terminal_set_bounds`| `{ x, y, width, height, scale }` device-independent px → child NSView frame |
| `terminal_set_focus` | forward focus in/out so the grid shows a live cursor |
| `terminal_close`     | free the surface |
| `terminal_open_external` | fallback: spawn external Ghostty / `$TERMINAL` in `cwd` |

## ABI reconciliation (integration TODO)

`ghostty.h` is an **unstable** embedding ABI — `action_cb` and the clipboard
callbacks carry tagged-union structs that change between tags. `ffi.rs`
encodes the signatures against a pinned tag and marks the runtime-config
assembly as the single seam to re-verify when bumping libghostty. Pin the
tag in `build.rs` (`LIBGHOSTTY_PATH` / `pkg-config ghostty`) and re-diff
`ffi.rs` against that tag's header before enabling the feature in a release.

## Build wiring

`build.rs` links `libghostty` only when `CARGO_FEATURE_GHOSTTY` is set:

1. `LIBGHOSTTY_PATH=/path/to/lib` → `cargo:rustc-link-search` + `-l ghostty`
2. else `pkg-config --libs ghostty`
3. else emit a `cargo:warning` and leave the symbols for a later link
   (the feature is opt-in; a missing lib is a developer error, not a CI break).

```bash
# macOS, with a local libghostty build:
LIBGHOSTTY_PATH=$HOME/src/ghostty/zig-out/lib \
  cargo build --features ghostty
```

## Verification checklist

- [ ] Default build (no feature) compiles on all platforms; `terminal_available`
      returns `{ embedded: false, reason: "..." }`.
- [ ] macOS `--features ghostty`: `terminal_open` shows a live shell grid in the
      bottom pane; typing works; the grid tracks pane resize and window resize.
- [ ] Non-macOS: "Open in Ghostty" launches an external Ghostty window in the
      project directory; pane explains the fallback.
