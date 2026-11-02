//! The bounding region B (box or circle) on which the function h = g is used:
//! h maps the smoothed text S into |z| < 1 and every other point of B into
//! |z| > 1 (h = infinity at the poles that lie in B).

use crate::lemniscate::Model;
use num_complex::Complex64 as C;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Region {
    /// [x0, y0, x1, y1]
    Box([f64; 4]),
    /// [cx, cy, r]
    Circle([f64; 3]),
}

impl Region {
    /// Box around the text's bounding box, expanded by `margin`.
    pub fn auto_box(bb: (f64, f64, f64, f64), margin: f64) -> Self {
        Region::Box([bb.0 - margin, bb.1 - margin, bb.2 + margin, bb.3 + margin])
    }
    /// Circle around the text's bounding box: radius = half diagonal + margin.
    pub fn auto_circle(bb: (f64, f64, f64, f64), margin: f64) -> Self {
        let c = C::new((bb.0 + bb.2) / 2.0, (bb.1 + bb.3) / 2.0);
        let r = (C::new(bb.2, bb.3) - c).norm() + margin;
        Region::Circle([c.re, c.im, r])
    }
    pub fn contains(&self, z: C) -> bool {
        match *self {
            Region::Box([x0, y0, x1, y1]) => z.re >= x0 && z.re <= x1 && z.im >= y0 && z.im <= y1,
            Region::Circle([cx, cy, r]) => (z - C::new(cx, cy)).norm() <= r,
        }
    }
    pub fn bbox(&self) -> (f64, f64, f64, f64) {
        match *self {
            Region::Box([x0, y0, x1, y1]) => (x0, y0, x1, y1),
            Region::Circle([cx, cy, r]) => (cx - r, cy - r, cx + r, cy + r),
        }
    }
    /// Points along the edge of the region.
    pub fn edge(&self, n: usize) -> Vec<C> {
        match *self {
            Region::Box([x0, y0, x1, y1]) => {
                let per = 2.0 * ((x1 - x0) + (y1 - y0));
                let corners = [C::new(x0, y0), C::new(x1, y0), C::new(x1, y1), C::new(x0, y1)];
                let mut v = vec![];
                for s in 0..4 {
                    let (a, b) = (corners[s], corners[(s + 1) % 4]);
                    let m = (((b - a).norm() / per) * n as f64).ceil() as usize + 1;
                    for k in 0..m {
                        v.push(a + (b - a) * (k as f64 / m as f64));
                    }
                }
                v
            }
            Region::Circle([cx, cy, r]) => (0..n)
                .map(|k| C::new(cx, cy) + C::from_polar(r, 2.0 * std::f64::consts::PI * k as f64 / n as f64))
                .collect(),
        }
    }
    pub fn describe(&self) -> String {
        match *self {
            Region::Box([x0, y0, x1, y1]) => format!("box [{x0:.3}, {x1:.3}] x [{y0:.3}, {y1:.3}]"),
            Region::Circle([cx, cy, r]) => format!("circle |z - ({cx:.3}{cy:+.3}i)| <= {r:.3}"),
        }
    }
}

/// What the program verifies about h on the region.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RegionReport {
    /// min over the region's edge of log|h|; > 0 means the smoothed text lies inside the region
    pub min_log_abs_on_edge: f64,
    pub text_inside_region: bool,
    /// poles of h inside the region: the only points where h is not finite
    pub poles_in_region: Vec<[f64; 2]>,
    /// sample points of the region outside S that land in |z| < 1 (must be 0)
    pub violations: usize,
    /// sample points checked
    pub samples: usize,
}

/// Check h = g on the region: the smoothed text must fit inside it (|h| > 1 on
/// its edge) and no sample point of the region outside S may land in |z| < 1.
/// `outline` is the (single, closed) outline curve of S.
pub fn verify(model: &Model, region: &Region, outline: &[C], res: usize) -> RegionReport {
    let edge = region.edge(4000);
    let min_edge = edge.par_iter().map(|&z| model.log_abs(z)).reduce(|| f64::INFINITY, f64::min);
    let poles_in: Vec<[f64; 2]> = model.poles.iter().filter(|&&b| region.contains(b)).map(|b| [b.re, b.im]).collect();
    // independent check: a point counts as "in the text" if it is inside the
    // traced outline polygon; points of B outside it must have |h| >= 1
    // (within a hair of the outline the traced polygon and the exact curve may
    // disagree, so points closer than 1e-3 to the outline are skipped)
    let (x0, y0, x1, y1) = region.bbox();
    let g = crate::contour::Grid::with_size(x0, y0, x1, y1, res, ((y1 - y0) / (x1 - x0) * res as f64).max(10.0) as usize);
    let pts: Vec<C> = g.points().into_iter().filter(|&z| region.contains(z)).collect();
    let outl = vec![outline.to_vec()];
    let violations = pts
        .par_iter()
        .filter(|&&z| {
            !crate::geom::point_in_ring(z, outline)
                && model.log_abs(z) < 0.0
                && crate::geom::dist_to_rings(z, &outl) > 1e-3
        })
        .count();
    RegionReport { min_log_abs_on_edge: min_edge, text_inside_region: min_edge > 0.0, poles_in_region: poles_in, violations, samples: pts.len() }
}
