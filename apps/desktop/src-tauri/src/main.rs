// SPDX-License-Identifier: Apache-2.0
// Prevents an additional console window on Windows in release mode.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    convsim_desktop_lib::run()
}
