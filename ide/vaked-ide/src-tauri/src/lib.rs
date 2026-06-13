pub mod commands;
pub mod error;
pub mod lsp;
pub mod session;

use commands::{graph::*, lsp::*, session::*, surface::*};
use commands::lsp::LspState;
use session::SessionState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = env_logger::try_init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(LspState::new())
        .manage(SessionState::new())
        .invoke_handler(tauri::generate_handler![
            // graph commands
            parse_vaked,
            check_vaked_raw,
            lower_vaked,
            // lsp commands
            start_lsp,
            lsp_send,
            stop_lsp,
            // session commands
            create_session,
            send_session_message,
            gateway_route,
            get_yjs_port,
            // surface commands
            register_surface_launcher,
            open_surface_view,
        ])
        .run(tauri::generate_context!())
        .expect("error while running vaked-ide");
}
