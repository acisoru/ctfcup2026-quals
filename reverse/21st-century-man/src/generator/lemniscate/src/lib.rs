//! Text -> one polygon -> smoothed text S = {|h| < 1}, where
//!
//! ```text
//! h(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k )
//! ```
//!
//! maps the smoothed text into |z| < 1 and every other point of a chosen box or
//! circle into |z| > 1 (h = infinity at the few poles inside it), plus the
//! one-to-one conformal map of S onto the unit disk.
//!
//! Pipeline: [`font::text_rings`] -> [`merge::merge_to_one_polygon`] ->
//! [`lemniscate::build`] -> [`region::verify`] / [`diskmap::DiskMap::new`].

pub mod contour;
pub mod diskmap;
pub mod font;
pub mod geom;
pub mod io;
pub mod lemniscate;
pub mod merge;
pub mod region;
pub mod svg;

pub use diskmap::DiskMap;
pub use lemniscate::{BuildOptions, Model};
pub use num_complex::Complex64 as C;
pub use region::Region;
