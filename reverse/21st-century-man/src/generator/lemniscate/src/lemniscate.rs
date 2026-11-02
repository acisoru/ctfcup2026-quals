//! The smoothing function
//!
//! ```text
//! g(z) = prod_j (z - a_j) / ( c * prod_h (z - b_h)^m_h )
//! ```
//!
//! and the smoothed text S = { z : |g(z)| < 1 }.
//!
//! * zeros a_j: N points just inside the text, chosen greedily so |g| is even
//!   along the text outline (projected weighted Leja points);
//! * poles b_h: placed adaptively in counters, holes and gaps between letters
//!   wherever S would otherwise fill them in, so the outline of S stays within
//!   `clearance` of the text (readability);
//! * level c: e^offset * max |num/den| on the text outline, so the polygon lies
//!   strictly inside S.
//!
//! S is kept simply connected (no holes), so it can be mapped onto the disk:
//! every hole of S would contain a pole (maximum principle), so a pole sealed
//! off from the outside is removed and its pocket allowed to fill in.
//! Every component of {|g| < 1} contains a zero and all zeros lie in the one
//! connected polygon, so {|g| < 1} is exactly S: everything else maps to |g| > 1
//! (g = infinity at the poles).

use crate::contour::{self, Grid};
use crate::geom::{self, Ring};
use num_complex::Complex64 as C;
use rayon::prelude::*;

#[derive(Clone, Debug)]
pub struct Model {
    pub zeros: Vec<C>,
    pub poles: Vec<C>,
    pub mults: Vec<u32>,
    /// log c
    pub logc: f64,
    /// target distance between the text and the smoothed outline
    pub clearance: f64,
    /// largest distance of a still-filled pocket point from the text (0 = none)
    pub gap: f64,
    /// pockets allowed to fill in to keep S simply connected
    pub filled: usize,
}

impl Model {
    /// log|num/den| without the level c.
    #[inline]
    pub fn log_abs_raw(&self, z: C) -> f64 {
        let mut s = 0.0;
        for chunk in self.zeros.chunks(16) {
            let mut prod = C::new(1.0, 0.0);
            for &a in chunk {
                prod *= z - a;
            }
            s += 0.5 * prod.norm_sqr().ln();
        }
        for (b, &m) in self.poles.iter().zip(&self.mults) {
            s -= m as f64 * 0.5 * (z - b).norm_sqr().ln();
        }
        s
    }
    /// log|g(z)|  (< 0 exactly on the smoothed text)
    #[inline]
    pub fn log_abs(&self, z: C) -> f64 {
        self.log_abs_raw(z) - self.logc
    }
    pub fn log_abs_many(&self, zs: &[C]) -> Vec<f64> {
        zs.par_iter().map(|&z| self.log_abs(z)).collect()
    }
    pub fn contains(&self, z: C) -> bool {
        self.log_abs(z) < 0.0
    }
    /// g'(z)/g(z)
    pub fn dlog(&self, z: C) -> C {
        let mut s = C::new(0.0, 0.0);
        for &a in &self.zeros {
            s += (z - a).inv();
        }
        for (b, &m) in self.poles.iter().zip(&self.mults) {
            s -= (z - b).inv() * m as f64;
        }
        s
    }
    /// g(z) itself (NaN at a pole; may overflow to infinity far away).
    pub fn eval(&self, z: C) -> C {
        if self.poles.iter().any(|&b| b == z) {
            return C::new(f64::NAN, f64::NAN);
        }
        let mut th = 0.0;
        for &a in &self.zeros {
            th += (z - a).arg();
        }
        for (b, &m) in self.poles.iter().zip(&self.mults) {
            th -= m as f64 * (z - b).arg();
        }
        C::from_polar(self.log_abs(z).exp(), geom::wrap(th))
    }
}

#[derive(Clone, Debug)]
pub struct BuildOptions {
    pub degree: usize,
    pub offset: f64,
    /// None = automatic: max(0.025, 0.8 * outline length / degree)
    pub clearance: Option<f64>,
    pub max_iter: usize,
    pub simply_connected: bool,
    /// None = automatic: min(0.025, outline length / degree)
    pub zero_depth: Option<f64>,
    pub verbose: bool,
}

impl Default for BuildOptions {
    fn default() -> Self {
        BuildOptions { degree: 1500, offset: 1.0, clearance: None, max_iter: 12, simply_connected: true, zero_depth: None, verbose: false }
    }
}

pub fn auto_clearance(rings: &[Ring], n: usize) -> f64 {
    let l: f64 = rings.iter().map(|r| geom::perimeter(r)).sum();
    (0.8 * l / n as f64).max(0.025)
}

struct Fitter {
    cand: Vec<C>,
    refs: Vec<C>,
    dense: Vec<C>,
    n: usize,
    offset: f64,
}

impl Fitter {
    /// Weighted Leja that evens |num/den| out on the true outline (`refs`) but
    /// puts each zero at the inner candidate below the outline point where |g|
    /// is currently largest.
    fn fit(&self, poles: &[C], mults: &[u32]) -> Model {
        let refs = &self.refs;
        let m = refs.len();
        let mut logr: Vec<f64> = refs
            .par_iter()
            .map(|&r| poles.iter().zip(mults).map(|(b, &k)| -(k as f64) * 0.5 * (r - b).norm_sqr().ln()).sum())
            .collect();
        let no_poles = poles.is_empty();
        if no_poles {
            let mean = refs.iter().sum::<C>() / m as f64;
            logr.par_iter_mut().zip(refs.par_iter()).for_each(|(l, &r)| *l = 0.5 * (r - mean).norm_sqr().ln());
        }
        let mut used = vec![false; m];
        let mut zeros = Vec::with_capacity(self.n);
        for it in 0..self.n {
            let k = logr
                .par_iter()
                .enumerate()
                .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
                .unwrap()
                .0;
            // nearest unused candidate (candidates are aligned with refs)
            let mut j = k;
            for d in 0..m {
                let a = (k + d) % m;
                if !used[a] {
                    j = a;
                    break;
                }
                let b = (k + m - d % m) % m;
                if !used[b] {
                    j = b;
                    break;
                }
            }
            used[j] = true;
            let a = self.cand[j];
            zeros.push(a);
            if it == 0 && no_poles {
                logr.iter_mut().for_each(|l| *l = 0.0);
            }
            logr.par_iter_mut().zip(refs.par_iter()).for_each(|(l, &r)| *l += 0.5 * (r - a).norm_sqr().ln());
        }
        let mut model = Model {
            zeros,
            poles: poles.to_vec(),
            mults: mults.to_vec(),
            logc: 0.0,
            clearance: 0.0,
            gap: f64::NAN,
            filled: 0,
        };
        let mx = self
            .dense
            .par_iter()
            .map(|&z| model.log_abs_raw(z))
            .filter(|v| v.is_finite())
            .reduce(|| f64::NEG_INFINITY, f64::max);
        model.logc = mx + self.offset;
        model
    }
}

/// Points about `d` inside the polygon below each outline sample.
fn inner_candidates(rings: &[Ring], s: &geom::Samples, d0: f64) -> Vec<C> {
    s.pts
        .par_iter()
        .zip(s.tangents.par_iter())
        .map(|(&p, &t)| {
            let nl = t * C::i();
            let n_in = if geom::point_in_rings(p + nl * 1e-6, rings) { nl } else { -nl };
            let mut d = d0;
            for _ in 0..4 {
                if d <= 0.0 {
                    break;
                }
                // step in, then slide along the distance gradient onto the
                // inner offset curve {dist = d} (matters at corners, where
                // the plain normal step ends up too close to the other edge)
                let mut q = p + n_in * d;
                for _ in 0..12 {
                    if !geom::point_in_rings(q, rings) {
                        break;
                    }
                    let c = geom::closest_on_rings(q, rings);
                    let dist = (q - c).norm();
                    if dist == 0.0 || (dist - d).abs() < 0.02 * d {
                        break;
                    }
                    q += (q - c) / dist * (d - dist);
                }
                if geom::point_in_rings(q, rings) && geom::dist_to_rings(q, rings) >= 0.7 * d {
                    return q;
                }
                d *= 0.5;
            }
            p + n_in * 1e-6
        })
        .collect()
}

fn hole_pole(h: &Ring, rings: &[Ring]) -> C {
    let (x0, y0, x1, y1) = geom::bbox(h.iter().copied());
    let g = Grid::with_size(x0, y0, x1, y1, 60, 60);
    g.points()
        .into_iter()
        .filter(|&p| geom::point_in_ring(p, h) && !geom::point_in_rings(p, rings))
        .map(|p| (p, geom::dist_to_rings(p, rings)))
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
        .map(|x| x.0)
        .unwrap_or_else(|| h.iter().sum::<C>() / h.len() as f64)
}

/// Closed level curves |g| = 1 on a grid of the given cell size, widening the
/// grid until its border lies outside S.
pub fn outline_curves(model: &Model, rings: &[Ring], cell: f64) -> Vec<Vec<C>> {
    let (x0, y0, x1, y1) = geom::bbox(rings.iter().flatten().copied());
    let mut pad = 0.4;
    let mut out = vec![];
    for _ in 0..4 {
        let g = Grid::new(x0 - pad, y0 - pad, x1 + pad, y1 + pad, cell);
        let v = model.log_abs_many(&g.points());
        let ok = g.border().all(|k| v[k] > 0.0);
        out = contour::closed_curves(&g, &v, 0.0);
        if ok {
            break;
        }
        pad *= 2.0;
    }
    out
}

/// Build the smoothing function for a polygon (rings + nesting depth).
pub fn build(rings: &[Ring], depth: &[usize], opt: &BuildOptions) -> Model {
    let n = opt.degree;
    let m = (40 * n).max(20000);
    let samples = geom::sample_rings(rings, m);
    let l_total: f64 = samples.perims.iter().sum();
    let zero_depth = opt.zero_depth.unwrap_or((l_total / n as f64).min(0.025));
    let cand = inner_candidates(rings, &samples, zero_depth);
    let dense = geom::sample_rings(rings, 4 * m).pts;
    let fitter = Fitter { cand, refs: samples.pts.clone(), dense, n, offset: opt.offset };
    let max_poles = (0.85 * n as f64) as u32;
    let say = |s: String| {
        if opt.verbose {
            eprintln!("      {s}");
        }
    };

    let mut poles: Vec<C> = vec![];
    let mut mults: Vec<u32> = vec![];
    for (i, r) in rings.iter().enumerate() {
        if depth[i] % 2 == 1 {
            poles.push(hole_pole(r, rings));
            mults.push(((n as f64 * samples.perims[i] / l_total).round() as u32).max(1));
        }
    }
    let mut model = fitter.fit(&poles, &mults);
    let clearance = opt.clearance.unwrap_or_else(|| auto_clearance(rings, n));
    model.clearance = clearance;
    if clearance <= 0.0 {
        return model;
    }

    // analysis grid: which points must end up OUTSIDE S
    let cell = clearance / 2.5;
    let (bx0, by0, bx1, by1) = geom::bbox(rings.iter().flatten().copied());
    let pad = (2.0 * clearance + cell).max(0.3);
    let grid = Grid::new(bx0 - pad, by0 - pad, bx1 + pad, by1 + pad, cell);
    let (nx, ny) = (grid.nx, grid.ny);
    let pts = grid.points();
    let dist = geom::dist_field(&pts, rings);
    let ink = geom::ink_field(&pts, rings);
    let hull = geom::convex_hull(&rings.iter().flatten().copied().collect::<Vec<_>>());
    let must_be_out: Vec<bool> = (0..pts.len())
        .into_par_iter()
        .map(|k| !ink[k] && dist[k] > clearance && geom::in_convex(pts[k], &hull))
        .collect();
    let mut given_up = vec![false; pts.len()];

    // filled-in pockets: components of must_be_out & !given_up & (|g| < 1)
    let assess = |lg: &[f64], given_up: &[bool]| -> (Vec<u32>, Vec<u32>, f64, usize) {
        let bad: Vec<bool> = (0..lg.len()).map(|k| must_be_out[k] && !given_up[k] && lg[k] < 0.0).collect();
        let (lab, nl) = contour::label(&bad, nx, ny);
        let mut sizes = vec![0usize; nl as usize + 1];
        for &l in &lab {
            sizes[l as usize] += 1;
        }
        let comps: Vec<u32> = (1..=nl).filter(|&l| sizes[l as usize] >= 3).collect();
        let mut gap: f64 = 0.0;
        let mut nbad = 0;
        for k in 0..lab.len() {
            if lab[k] > 0 && sizes[lab[k] as usize] >= 3 {
                gap = gap.max(dist[k]);
                nbad += 1;
            }
        }
        (lab, comps, gap, nbad)
    };
    // poles whose |g| >= 1 region does not reach the outside of the grid
    let trapped_poles = |lg: &[f64], poles: &[C]| -> (Vec<usize>, Vec<u32>) {
        let pos: Vec<bool> = lg.iter().map(|&v| v >= 0.0).collect();
        let (lab, _) = contour::label(&pos, nx, ny);
        let border: std::collections::HashSet<u32> = grid.border().map(|k| lab[k]).filter(|&l| l > 0).collect();
        let t = poles
            .iter()
            .enumerate()
            .filter(|&(_, &b)| {
                let l = lab[grid.index_of(b)];
                l == 0 || !border.contains(&l)
            })
            .map(|(i, _)| i)
            .collect();
        (t, lab)
    };

    let mut best: Option<(usize, Model)> = None;
    let mut it = 0;
    let mut can_add = true;
    for _guard in 0..(6 * opt.max_iter + 20) {
        let lg = model.log_abs_many(&pts);
        let (lab, comps, gap, nbad) = assess(&lg, &given_up);
        let (trapped, plab) = if opt.simply_connected && !poles.is_empty() { trapped_poles(&lg, &poles) } else { (vec![], vec![]) };
        if trapped.is_empty() {
            model.gap = gap;
            if best.as_ref().map_or(true, |b| nbad <= b.0) {
                best = Some((nbad, model.clone()));
            }
        }
        say(format!(
            "round {it}: {} poles (total order {}), {} filled-in pockets, {} sealed pole(s)",
            poles.len(),
            mults.iter().sum::<u32>(),
            comps.len(),
            trapped.len()
        ));
        if !comps.is_empty() && can_add && it < opt.max_iter {
            // open every pocket first (also pushes poles into slits and mouths,
            // which un-seals poles trapped behind them)
            it += 1;
            let mut new_poles = poles.clone();
            let mut new_mults = mults.clone();
            for &k in &comps {
                let comp: Vec<bool> = lab.iter().map(|&l| l == k).collect();
                let j = (0..comp.len()).filter(|&q| comp[q]).max_by(|&a, &b| dist[a].partial_cmp(&dist[b]).unwrap()).unwrap();
                let p = pts[j];
                let near = new_poles.iter().position(|&b| lab[grid.index_of(b)] == k || (b - p).norm() < dist[j]);
                if let Some(i) = near {
                    new_mults[i] = (new_mults[i] as f64 * 1.6).ceil() as u32 + 1;
                } else {
                    // new pole at the pocket's deepest point; order ~ its share of
                    // the outline (a pocket rim counts both walls, hence the 1/2)
                    let wall = 0.5 * contour::edge_cells(&comp, nx, ny) as f64 * cell;
                    new_poles.push(p);
                    new_mults.push(((n as f64 * wall / l_total).round() as u32).max(2));
                }
            }
            let total: u32 = new_mults.iter().sum();
            if total > max_poles {
                // total pole order must stay below the degree: scale this round down
                let old: Vec<u32> = mults.iter().copied().chain(std::iter::repeat(0).take(new_mults.len() - mults.len())).collect();
                let room = max_poles as i64 - mults.iter().sum::<u32>() as i64;
                let added = (new_poles.len() - poles.len()) as i64;
                if room < added + 1 {
                    say("pole budget reached; raise the degree or the clearance".into());
                    can_add = false;
                    continue;
                }
                let inc: Vec<u32> = new_mults.iter().zip(&old).map(|(a, b)| a - b).collect();
                let s = room as f64 / inc.iter().sum::<u32>().max(1) as f64;
                new_mults = old.iter().zip(&inc).map(|(&o, &i)| o + ((i as f64 * s) as u32).max(if o == 0 { 1 } else { 0 })).collect();
            }
            poles = new_poles;
            mults = new_mults;
            model = fitter.fit(&poles, &mults);
            continue;
        }
        if !trapped.is_empty() {
            // nothing left to open, yet some poles sit in sealed islands
            // (holes of S): let those pockets fill instead
            say(format!("letting {} sealed pocket(s) fill so the shape stays simply connected", trapped.len()));
            for &i in &trapped {
                let l = plab[grid.index_of(poles[i])];
                let region: Vec<bool> = if l > 0 {
                    plab.iter().map(|&x| x == l).collect()
                } else {
                    pts.iter().map(|&z| (z - poles[i]).norm() < 2.0 * cell).collect()
                };
                let region = contour::dilate(&region, nx, ny, 2);
                for k in 0..region.len() {
                    given_up[k] |= region[k];
                }
            }
            let keep: Vec<usize> = (0..poles.len()).filter(|i| !trapped.contains(i)).collect();
            poles = keep.iter().map(|&i| poles[i]).collect();
            mults = keep.iter().map(|&i| mults[i]).collect();
            model = fitter.fit(&poles, &mults);
            continue;
        }
        break;
    }
    let mut model = best.map(|b| b.1).unwrap_or(model);

    // final check on a fine grid: the outline must be ONE closed curve
    if opt.simply_connected && !model.poles.is_empty() {
        for _ in 0..10 {
            let curves = outline_curves(&model, rings, clearance / 6.0);
            if curves.len() <= 1 {
                break;
            }
            let outer = (0..curves.len())
                .max_by(|&a, &b| geom::signed_area(&curves[a]).abs().partial_cmp(&geom::signed_area(&curves[b]).abs()).unwrap())
                .unwrap();
            let inner: Vec<&Vec<C>> = curves.iter().enumerate().filter(|(i, _)| *i != outer).map(|(_, c)| c).collect();
            let keep: Vec<usize> = (0..model.poles.len()).filter(|&i| !inner.iter().any(|c| geom::point_in_ring(model.poles[i], c))).collect();
            if keep.len() == model.poles.len() {
                break;
            }
            say(format!("fine check: {} sealed pole(s) removed", model.poles.len() - keep.len()));
            let p: Vec<C> = keep.iter().map(|&i| model.poles[i]).collect();
            let mu: Vec<u32> = keep.iter().map(|&i| model.mults[i]).collect();
            model = fitter.fit(&p, &mu);
        }
        let lg = model.log_abs_many(&pts);
        model.gap = assess(&lg, &given_up).2;
    }
    model.clearance = clearance;
    let gu: Vec<bool> = (0..given_up.len()).map(|k| given_up[k] && must_be_out[k]).collect();
    model.filled = contour::label(&gu, nx, ny).1 as usize;
    model
}
