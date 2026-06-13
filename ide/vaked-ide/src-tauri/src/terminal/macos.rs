//! macOS child-`NSView` overlay for the embedded Ghostty surface.
//!
//! Tauri's UI is a `WKWebView` filling the window's `contentView`. We add a
//! sibling child `NSView` on top of it and hand that view to
//! `ghostty_surface_new(.nsview)`. The webview reserves a transparent
//! rectangle (`<TerminalPane>`); the frontend reports its bounds and we keep
//! this child view's frame in lockstep.
//!
//! All functions here MUST be called on the AppKit main thread.
#![cfg(all(feature = "ghostty", target_os = "macos"))]

use objc2::rc::Id;
use objc2::runtime::AnyObject;
use objc2::{class, msg_send, msg_send_id};
use std::os::raw::c_void;

#[repr(C)]
#[derive(Clone, Copy)]
struct CGPoint {
    x: f64,
    y: f64,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct CGSize {
    width: f64,
    height: f64,
}
#[repr(C)]
#[derive(Clone, Copy)]
struct CGRect {
    origin: CGPoint,
    size: CGSize,
}

/// Device-independent bounds of the terminal pane, as reported by the webview
/// (top-left origin, like CSS / `getBoundingClientRect`).
#[derive(Clone, Copy, Debug)]
pub struct PaneBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

unsafe fn content_view(ns_window: *mut c_void) -> *mut AnyObject {
    let window = ns_window as *mut AnyObject;
    msg_send![window, contentView]
}

unsafe fn content_height(ns_window: *mut c_void) -> f64 {
    let cv = content_view(ns_window);
    let bounds: CGRect = msg_send![cv, bounds];
    bounds.size.height
}

/// AppKit uses a bottom-left origin; the webview reports top-left. Flip Y
/// against the content view height so the overlay lines up with the DOM node.
unsafe fn to_appkit_rect(ns_window: *mut c_void, b: PaneBounds) -> CGRect {
    let ch = content_height(ns_window);
    CGRect {
        origin: CGPoint {
            x: b.x,
            y: ch - (b.y + b.height),
        },
        size: CGSize {
            width: b.width,
            height: b.height,
        },
    }
}

/// Create the child `NSView` overlay and return a retained raw pointer to it.
/// The returned pointer is what gets stored in `ghostty_platform_macos_s.nsview`.
pub unsafe fn create_overlay(ns_window: *mut c_void, b: PaneBounds) -> *mut c_void {
    let frame = to_appkit_rect(ns_window, b);

    let view: Id<AnyObject> = {
        let alloc: Id<AnyObject> = msg_send_id![class!(NSView), alloc];
        msg_send_id![alloc, initWithFrame: frame]
    };

    // Layer-backed so Ghostty's Metal layer has somewhere to attach.
    let _: () = msg_send![&*view, setWantsLayer: true];
    // Pin to the bottom-left so our explicit frame updates win.
    let _: () = msg_send![&*view, setAutoresizingMask: 0u64];

    let cv = content_view(ns_window);
    let _: () = msg_send![cv, addSubview: &*view];

    // Leak the retain into a raw pointer the runtime owns until `destroy`.
    Id::into_raw(view) as *mut c_void
}

/// Reposition/resize the overlay to follow the pane's DOM rectangle.
pub unsafe fn set_overlay_frame(view: *mut c_void, ns_window: *mut c_void, b: PaneBounds) {
    if view.is_null() {
        return;
    }
    let frame = to_appkit_rect(ns_window, b);
    let view = view as *mut AnyObject;
    let _: () = msg_send![view, setFrame: frame];
}

/// Remove the overlay from the view hierarchy and release the retain.
pub unsafe fn destroy_overlay(view: *mut c_void) {
    if view.is_null() {
        return;
    }
    let view = view as *mut AnyObject;
    let _: () = msg_send![view, removeFromSuperview];
    // Balance the retain leaked by `Id::into_raw` in `create_overlay`.
    let _ = Id::from_raw(view);
}
