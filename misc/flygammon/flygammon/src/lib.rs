//! Library surface for flygammon, so the CTF daemon can reuse the engine, model
//! and agent directly. The `main.rs` binary keeps its own module tree; this lib
//! exposes the same modules for external crates (e.g. `flygammon-task/daemon`).

pub mod agent;
pub mod bench;
pub mod calib;
pub mod engine;
pub mod eval;
pub mod external;
pub mod features;
pub mod model;
pub mod train;
