//! Raw FFI bindings to the `libghostty` C embedding API (`include/ghostty.h`).
//!
//! Only compiled under `--features ghostty`. These declarations mirror the
//! published embedding header. The embedding ABI is **unstable** — the tagged
//! unions carried by `action_cb` and the clipboard callbacks change between
//! Ghostty tags. Treat [`ghostty_runtime_config_s`] as the single seam to
//! re-verify when bumping the pinned libghostty version (see
//! `docs/terminal-embedding.md`).
#![allow(non_camel_case_types, dead_code)]

use std::os::raw::{c_char, c_void};

// --- Opaque handles -------------------------------------------------------
pub type ghostty_app_t = *mut c_void;
pub type ghostty_config_t = *mut c_void;
pub type ghostty_surface_t = *mut c_void;

// --- Platform tagging -----------------------------------------------------
// The C header only defines MACOS and IOS. X11/Wayland are intentionally
// absent: Linux drives surfaces through Ghostty's internal GTK apprt, which
// is not reachable from this C API.
pub const GHOSTTY_PLATFORM_INVALID: u32 = 0;
pub const GHOSTTY_PLATFORM_MACOS: u32 = 1;
pub const GHOSTTY_PLATFORM_IOS: u32 = 2;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ghostty_platform_macos_s {
    /// Pointer to the `NSView` libghostty draws the terminal grid into.
    pub nsview: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ghostty_platform_ios_s {
    pub uiview: *mut c_void,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub union ghostty_platform_u {
    pub macos: ghostty_platform_macos_s,
    pub ios: ghostty_platform_ios_s,
}

#[repr(C)]
#[derive(Clone, Copy)]
pub struct ghostty_env_var_s {
    pub key: *const c_char,
    pub value: *const c_char,
}

#[repr(C)]
pub struct ghostty_surface_config_s {
    pub platform_tag: u32,
    pub platform: ghostty_platform_u,
    pub userdata: *mut c_void,
    pub scale_factor: f64,
    pub font_size: f32,
    pub working_directory: *const c_char,
    pub command: *const c_char,
    pub env_vars: *mut ghostty_env_var_s,
    pub env_var_count: usize,
    pub initial_input: *const c_char,
    pub wait_after_command: bool,
    /// `ghostty_surface_context_e`; 0 selects the default context.
    pub context: u32,
}

// --- Runtime callbacks ----------------------------------------------------
// NOTE (ABI seam): `action_cb` and the clipboard callbacks carry tagged-union
// structs in the real header that vary by tag. We bind the stable-shaped
// callbacks we actually implement (wakeup / close-surface / clipboard write)
// and keep `action_cb` as a pointer-width slot to be reconciled against the
// pinned `ghostty.h` before enabling the feature in a release build.
pub type ghostty_runtime_wakeup_cb = unsafe extern "C" fn(userdata: *mut c_void);
pub type ghostty_runtime_action_cb = *mut c_void; // reconcile per pinned tag
pub type ghostty_runtime_read_clipboard_cb =
    unsafe extern "C" fn(userdata: *mut c_void, location: u32, state: *mut c_void);
pub type ghostty_runtime_confirm_read_clipboard_cb = unsafe extern "C" fn(
    userdata: *mut c_void,
    contents: *const c_char,
    state: *mut c_void,
    request: u32,
);
pub type ghostty_runtime_write_clipboard_cb = unsafe extern "C" fn(
    userdata: *mut c_void,
    contents: *const c_char,
    location: u32,
    confirm: bool,
);
pub type ghostty_runtime_close_surface_cb =
    unsafe extern "C" fn(userdata: *mut c_void, process_alive: bool);

#[repr(C)]
pub struct ghostty_runtime_config_s {
    pub userdata: *mut c_void,
    pub supports_selection_clipboard: bool,
    pub wakeup_cb: ghostty_runtime_wakeup_cb,
    pub action_cb: ghostty_runtime_action_cb,
    pub read_clipboard_cb: ghostty_runtime_read_clipboard_cb,
    pub confirm_read_clipboard_cb: ghostty_runtime_confirm_read_clipboard_cb,
    pub write_clipboard_cb: ghostty_runtime_write_clipboard_cb,
    pub close_surface_cb: ghostty_runtime_close_surface_cb,
}

// --- Imported functions ---------------------------------------------------
extern "C" {
    pub fn ghostty_init(argc: usize, argv: *mut *mut c_char) -> i32;

    pub fn ghostty_config_new() -> ghostty_config_t;
    pub fn ghostty_config_free(cfg: ghostty_config_t);
    pub fn ghostty_config_load_default_files(cfg: ghostty_config_t);
    pub fn ghostty_config_finalize(cfg: ghostty_config_t);

    pub fn ghostty_app_new(
        runtime: *const ghostty_runtime_config_s,
        cfg: ghostty_config_t,
    ) -> ghostty_app_t;
    pub fn ghostty_app_free(app: ghostty_app_t);
    pub fn ghostty_app_tick(app: ghostty_app_t);

    pub fn ghostty_surface_new(
        app: ghostty_app_t,
        cfg: *const ghostty_surface_config_s,
    ) -> ghostty_surface_t;
    pub fn ghostty_surface_free(surface: ghostty_surface_t);
    pub fn ghostty_surface_refresh(surface: ghostty_surface_t);
    pub fn ghostty_surface_draw(surface: ghostty_surface_t);
    pub fn ghostty_surface_set_size(surface: ghostty_surface_t, width: u32, height: u32);
    pub fn ghostty_surface_set_content_scale(surface: ghostty_surface_t, x: f64, y: f64);
    pub fn ghostty_surface_set_focus(surface: ghostty_surface_t, focused: bool);
    pub fn ghostty_surface_set_occlusion(surface: ghostty_surface_t, visible: bool);
}
