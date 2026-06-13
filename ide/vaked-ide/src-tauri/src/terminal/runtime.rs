//! `GhosttyRuntime` — embedded-terminal lifecycle on macOS.
//!
//! libghostty + AppKit are main-thread-only, so the runtime instance lives in
//! a main-thread `thread_local!`. Commands marshal closures onto the main
//! thread (`AppHandle::run_on_main_thread`) which touch it there. The
//! `wakeup_cb` reschedules `ghostty_app_tick` back onto the main thread.
#![cfg(all(feature = "ghostty", target_os = "macos"))]

use std::cell::RefCell;
use std::ffi::CString;
use std::os::raw::c_void;
use std::sync::OnceLock;

use tauri::{AppHandle, Manager};

use super::ffi;
use super::macos::{self, PaneBounds};

thread_local! {
    /// The single main-thread runtime. `None` until the first `open`.
    static RUNTIME: RefCell<Option<GhosttyRuntime>> = const { RefCell::new(None) };
}

/// Stashed for the `wakeup_cb`, which must reschedule a tick onto main.
static APP_HANDLE: OnceLock<AppHandle> = OnceLock::new();

struct GhosttyRuntime {
    app: ffi::ghostty_app_t,
    config: ffi::ghostty_config_t,
    surface: ffi::ghostty_surface_t,
    overlay: *mut c_void,
    ns_window: *mut c_void,
}

// --- Runtime callbacks (extern "C") --------------------------------------

unsafe extern "C" fn wakeup_cb(_userdata: *mut c_void) {
    // Called from libghostty's thread; service the app on main.
    if let Some(app) = APP_HANDLE.get() {
        let _ = app.run_on_main_thread(|| {
            RUNTIME.with(|r| {
                if let Some(rt) = r.borrow().as_ref() {
                    if !rt.app.is_null() {
                        unsafe { ffi::ghostty_app_tick(rt.app) };
                    }
                }
            });
        });
    }
}

unsafe extern "C" fn read_clipboard_cb(_u: *mut c_void, _loc: u32, _state: *mut c_void) {}
unsafe extern "C" fn confirm_read_clipboard_cb(
    _u: *mut c_void,
    _c: *const std::os::raw::c_char,
    _state: *mut c_void,
    _req: u32,
) {
}
unsafe extern "C" fn write_clipboard_cb(
    _u: *mut c_void,
    _c: *const std::os::raw::c_char,
    _loc: u32,
    _confirm: bool,
) {
}
unsafe extern "C" fn close_surface_cb(_u: *mut c_void, _alive: bool) {
    RUNTIME.with(|r| {
        if let Some(rt) = r.borrow_mut().as_mut() {
            rt.surface = std::ptr::null_mut();
        }
    });
}

fn runtime_config() -> ffi::ghostty_runtime_config_s {
    ffi::ghostty_runtime_config_s {
        userdata: std::ptr::null_mut(),
        supports_selection_clipboard: false,
        wakeup_cb,
        // ABI seam: see ffi.rs. Reconcile against the pinned ghostty.h before
        // enabling the feature in a release.
        action_cb: std::ptr::null_mut(),
        read_clipboard_cb,
        confirm_read_clipboard_cb,
        write_clipboard_cb,
        close_surface_cb,
    }
}

/// Initialize libghostty exactly once (process-wide).
unsafe fn ensure_init() {
    use std::sync::Once;
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        ffi::ghostty_init(0, std::ptr::null_mut());
    });
}

/// Open (or focus) the embedded terminal in `cwd`. Runs on the main thread.
pub fn open_on_main(app: &AppHandle, ns_window: *mut c_void, bounds: PaneBounds, cwd: Option<String>, scale: f64) {
    let _ = APP_HANDLE.set(app.clone());

    RUNTIME.with(|r| {
        let mut slot = r.borrow_mut();
        if slot.as_ref().map(|rt| !rt.surface.is_null()).unwrap_or(false) {
            return; // already open
        }

        unsafe {
            ensure_init();

            // App is created once and reused across open/close.
            let (gapp, gcfg) = match slot.as_ref() {
                Some(rt) if !rt.app.is_null() => (rt.app, rt.config),
                _ => {
                    let cfg = ffi::ghostty_config_new();
                    ffi::ghostty_config_load_default_files(cfg);
                    ffi::ghostty_config_finalize(cfg);
                    let rc = runtime_config();
                    let gapp = ffi::ghostty_app_new(&rc, cfg);
                    (gapp, cfg)
                }
            };

            let overlay = macos::create_overlay(ns_window, bounds);

            let cwd_c = cwd.as_deref().map(|s| CString::new(s).unwrap());
            let mut scfg = ffi::ghostty_surface_config_s {
                platform_tag: ffi::GHOSTTY_PLATFORM_MACOS,
                platform: ffi::ghostty_platform_u {
                    macos: ffi::ghostty_platform_macos_s { nsview: overlay },
                },
                userdata: std::ptr::null_mut(),
                scale_factor: scale,
                font_size: 0.0, // 0 → inherit config default
                working_directory: cwd_c
                    .as_ref()
                    .map(|c| c.as_ptr())
                    .unwrap_or(std::ptr::null()),
                command: std::ptr::null(),
                env_vars: std::ptr::null_mut(),
                env_var_count: 0,
                initial_input: std::ptr::null(),
                wait_after_command: false,
                context: 0,
            };

            let surface = ffi::ghostty_surface_new(gapp, &mut scfg);
            ffi::ghostty_surface_set_content_scale(surface, scale, scale);
            ffi::ghostty_surface_set_size(
                surface,
                (bounds.width * scale) as u32,
                (bounds.height * scale) as u32,
            );
            ffi::ghostty_surface_set_focus(surface, true);

            *slot = Some(GhosttyRuntime {
                app: gapp,
                config: gcfg,
                surface,
                overlay,
                ns_window,
            });
        }
    });
}

/// Track the pane's DOM rectangle. Runs on the main thread.
pub fn set_bounds_on_main(bounds: PaneBounds, scale: f64) {
    RUNTIME.with(|r| {
        if let Some(rt) = r.borrow().as_ref() {
            unsafe {
                macos::set_overlay_frame(rt.overlay, rt.ns_window, bounds);
                if !rt.surface.is_null() {
                    ffi::ghostty_surface_set_size(
                        rt.surface,
                        (bounds.width * scale) as u32,
                        (bounds.height * scale) as u32,
                    );
                    ffi::ghostty_surface_refresh(rt.surface);
                }
            }
        }
    });
}

/// Forward focus changes. Runs on the main thread.
pub fn set_focus_on_main(focused: bool) {
    RUNTIME.with(|r| {
        if let Some(rt) = r.borrow().as_ref() {
            if !rt.surface.is_null() {
                unsafe { ffi::ghostty_surface_set_focus(rt.surface, focused) };
            }
        }
    });
}

/// Free the surface + overlay (app is kept for reuse). Runs on the main thread.
pub fn close_on_main() {
    RUNTIME.with(|r| {
        if let Some(rt) = r.borrow_mut().as_mut() {
            unsafe {
                if !rt.surface.is_null() {
                    ffi::ghostty_surface_free(rt.surface);
                    rt.surface = std::ptr::null_mut();
                }
                macos::destroy_overlay(rt.overlay);
                rt.overlay = std::ptr::null_mut();
            }
        }
    });
}
