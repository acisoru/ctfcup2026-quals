//! Riemann map  phi : S -> {|w| < 1},  phi(z0) = 0, phi'(z0) > 0,
//! for the smoothed text S = {|g| < 1} (a simply connected region with a smooth
//! analytic outline).
//!
//! Charge simulation method (Amano): with charges zeta_k just outside the outline
//!
//! ```text
//! phi(z) = (z - z0) * exp( Q0 + sum_k Q_k log(z - zeta_k) - i*theta0 )
//! ```
//!
//! with real Q0, Q_k chosen so |phi| = 1 at K outline points and sum Q_k = 0.
//! The zero total charge lets the logs be chained,
//! ```text
//! sum_k Q_k log(z - zeta_k) = sum_k S_k log((z - zeta_k)/(z - zeta_{k+1})),
//! ```
//! so every branch cut is a short segment between neighbouring charges, outside
//! S: phi is single-valued and holomorphic on S.

use crate::geom::{self, Ring};
use crate::lemniscate::{outline_curves, Model};
use faer::prelude::*;
use faer::Mat;
use num_complex::Complex64 as C;
use rayon::prelude::*;

#[derive(Clone, Debug)]
pub struct DiskMap {
    pub model: Model,
    pub z0: C,
    pub zeta: Vec<C>,
    pub q: Vec<f64>,
    pub q0: f64,
    pub theta0: f64,
    s: Vec<f64>,
    /// outline points used (counter-clockwise)
    pub boundary: Vec<C>,
    pub boundary_error: f64,
    pub winding: f64,
    pub min_boundary_step: f64,
    table: Vec<(C, C)>,
}

#[derive(Debug)]
pub struct NotSimplyConnected(pub usize);

impl std::fmt::Display for NotSimplyConnected {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "the smoothed outline has {} closed curves, so the region is not simply connected and has no conformal map onto the disk", self.0)
    }
}

fn project(model: &Model, z: &mut [C]) {
    z.par_iter_mut().for_each(|p| {
        for _ in 0..5 {
            let u = model.log_abs(*p);
            let grad = model.dlog(*p).conj();
            *p -= grad * (u / grad.norm_sqr());
        }
    });
}

impl DiskMap {
    pub fn new(model: &Model, rings: &[Ring], z0: Option<C>, spacing: Option<f64>, q: f64, verbose: bool) -> Result<Self, NotSimplyConnected> {
        let clr = if model.clearance > 0.0 { model.clearance } else { 0.04 };
        let curves = outline_curves(model, rings, clr / 6.0);
        if curves.len() != 1 {
            return Err(NotSimplyConnected(curves.len()));
        }
        let mut c = curves.into_iter().next().unwrap();
        project(model, &mut c);
        if geom::signed_area(&c) < 0.0 {
            c.reverse();
        }
        // resample the outline with spacing ~ 0.4 x (distance to the nearest
        // zero or pole of g): those are what put fine detail into the outline,
        // and the map's analytic continuation has its singularities at that scale
        let nc = c.len();
        let len: f64 = (0..nc).map(|i| (c[(i + 1) % nc] - c[i]).norm()).sum();
        let h0 = spacing.unwrap_or((clr / 5.0).min(len / 800.0));
        let sing: Vec<C> = model.zeros.iter().chain(model.poles.iter()).copied().collect();
        let local: Vec<f64> = c
            .par_iter()
            .map(|&z| {
                let dmin = sing.iter().map(|&a| (a - z).norm()).fold(f64::INFINITY, f64::min);
                (0.4 * dmin).clamp(h0 / 6.0, h0)
            })
            .collect();
        // tau = integral of ds / h(s); points evenly spaced in tau
        let mut tau = vec![0.0; nc + 1];
        for i in 0..nc {
            let ds = (c[(i + 1) % nc] - c[i]).norm();
            tau[i + 1] = tau[i] + ds * 0.5 * (1.0 / local[i] + 1.0 / local[(i + 1) % nc]);
        }
        let total = tau[nc];
        let k = (total.ceil() as usize).clamp(400, 5000);
        let mut zc = Vec::with_capacity(k);
        let mut seg = 0;
        for i in 0..k {
            let t = i as f64 * total / k as f64;
            while seg + 1 < nc && tau[seg + 1] < t {
                seg += 1;
            }
            let a = c[seg];
            let b = c[(seg + 1) % nc];
            let w = if tau[seg + 1] > tau[seg] { (t - tau[seg]) / (tau[seg + 1] - tau[seg]) } else { 0.0 };
            zc.push(a + (b - a) * w);
        }
        project(model, &mut zc);
        // local spacing at each point (for the charge distances)
        let hs: Vec<f64> = (0..k).map(|i| 0.5 * ((zc[(i + 1) % k] - zc[i]).norm() + (zc[i] - zc[(i + k - 1) % k]).norm())).collect();
        let normals: Vec<C> = zc.iter().map(|&z| {
            let n = model.dlog(z).conj();
            n / n.norm()
        }).collect();

        let z0 = z0.unwrap_or_else(|| deepest_point(model, &zc));

        // charges outside, pulled in where another part of the outline is close
        let mut f = vec![q; k];
        let mut zeta: Vec<C> = vec![];
        let mut dmat: Vec<f64> = vec![];
        for _ in 0..6 {
            zeta = (0..k).map(|i| zc[i] + normals[i] * (f[i] * hs[i])).collect();
            dmat = (0..k * k).into_par_iter().map(|ij| (zc[ij / k] - zeta[ij % k]).norm()).collect();
            let out: Vec<bool> = zeta.par_iter().map(|&z| model.log_abs(z) > 0.0).collect();
            let mid_out: Vec<bool> = (0..k).into_par_iter().map(|i| model.log_abs((zeta[i] + zeta[(i + 1) % k]) * 0.5) > 0.0).collect();
            let mut any = false;
            for j in 0..k {
                let mind = (0..k).map(|i| dmat[i * k + j]).fold(f64::INFINITY, f64::min);
                let bad = mind < 0.6 * f[j] * hs[j] || !out[j] || !mid_out[j] || !mid_out[(j + k - 1) % k];
                if bad {
                    f[j] *= 0.5;
                    any = true;
                }
            }
            if !any {
                break;
            }
        }

        // (K+1)x(K+1): Q0 + sum_k Q_k log|z_i - zeta_k| = -log|z_i - z0|,  sum_k Q_k = 0
        let a = Mat::<f64>::from_fn(k + 1, k + 1, |i, j| {
            if i < k {
                if j == 0 { 1.0 } else { dmat[i * k + j - 1].ln() }
            } else if j == 0 {
                0.0
            } else {
                1.0
            }
        });
        let mut rhs = Mat::<f64>::from_fn(k + 1, 1, |i, _| if i < k { -(zc[i] - z0).norm().ln() } else { 0.0 });
        let lu = a.partial_piv_lu();
        lu.solve_in_place(&mut rhs);
        let q0 = rhs[(0, 0)];
        let qv: Vec<f64> = (0..k).map(|i| rhs[(i + 1, 0)]).collect();
        let mut sv = Vec::with_capacity(k - 1);
        let mut acc = 0.0;
        for &x in &qv[..k - 1] {
            acc += x;
            sv.push(acc);
        }
        let mut map = DiskMap {
            model: model.clone(),
            z0,
            zeta,
            q: qv,
            q0,
            theta0: 0.0,
            s: sv,
            boundary: zc,
            boundary_error: 0.0,
            winding: 0.0,
            min_boundary_step: 0.0,
            table: vec![],
        };
        map.theta0 = map.f(z0).im;
        map.check();
        if verbose {
            eprintln!(
                "      conformal map: {k} outline points, max ||phi|-1| on the outline = {:.1e}, winding number {:.6}, smallest outline arc on the circle {:.1e} rad",
                map.boundary_error, map.winding, map.min_boundary_step
            );
        }
        Ok(map)
    }

    /// Rebuild from saved parameters.
    pub fn from_parts(model: Model, z0: C, zeta: Vec<C>, q: Vec<f64>, q0: f64, theta0: f64) -> Self {
        let mut s = Vec::with_capacity(q.len().saturating_sub(1));
        let mut acc = 0.0;
        for &x in &q[..q.len().saturating_sub(1)] {
            acc += x;
            s.push(acc);
        }
        DiskMap { model, z0, zeta, q, q0, theta0, s, boundary: vec![], boundary_error: f64::NAN, winding: f64::NAN, min_boundary_step: f64::NAN, table: vec![] }
    }

    fn check(&mut self) {
        let k = self.boundary.len();
        let mut mid: Vec<C> = (0..k).map(|i| (self.boundary[i] + self.boundary[(i + 1) % k]) * 0.5).collect();
        project(&self.model, &mut mid);
        self.boundary_error = mid.par_iter().map(|&z| (self.phi(z).norm() - 1.0).abs()).reduce(|| 0.0, f64::max);
        let th: Vec<f64> = self.boundary.par_iter().map(|&z| self.phi(z).arg()).collect();
        let d: Vec<f64> = (0..k).map(|i| geom::wrap(th[(i + 1) % k] - th[i])).collect();
        self.winding = d.iter().sum::<f64>() / (2.0 * std::f64::consts::PI);
        self.min_boundary_step = d.iter().map(|x| x.abs()).fold(f64::INFINITY, f64::min);
    }

    /// Q0 + sum Q_k log(z - zeta_k) - i theta0, chained branch.
    fn f(&self, z: C) -> C {
        let k = self.zeta.len();
        let mut re = self.q0;
        let mut im = 0.0;
        let mut prev = (z - self.zeta[0]).arg();
        re += self.q[0] * (z - self.zeta[0]).norm().ln();
        for i in 1..k {
            let d = z - self.zeta[i];
            re += self.q[i] * d.norm().ln();
            let a = d.arg();
            im += self.s[i - 1] * geom::wrap(prev - a);
            prev = a;
        }
        C::new(re, im - self.theta0)
    }

    /// phi(z) for z in S (no inside test).
    pub fn phi(&self, z: C) -> C {
        (z - self.z0) * self.f(z).exp()
    }

    pub fn dphi(&self, z: C) -> C {
        let fp: C = self.zeta.iter().zip(&self.q).map(|(&zt, &qk)| (z - zt).inv() * qk).sum();
        self.f(z).exp() * (C::new(1.0, 0.0) + (z - self.z0) * fp)
    }

    /// phi(z) for z in S; NaN outside S.
    pub fn to_disk(&self, z: C) -> C {
        if self.model.contains(z) { self.phi(z) } else { C::new(f64::NAN, f64::NAN) }
    }

    pub fn to_disk_many(&self, zs: &[C]) -> Vec<C> {
        zs.par_iter().map(|&z| self.to_disk(z)).collect()
    }

    /// phi^{-1}(w), |w| < 1, by Newton from the nearest tabulated point.
    pub fn from_disk(&mut self, w: C) -> C {
        if self.table.is_empty() {
            let (x0, y0, x1, y1) = if self.boundary.is_empty() {
                geom::bbox(self.zeta.iter().copied())
            } else {
                geom::bbox(self.boundary.iter().copied())
            };
            let g = crate::contour::Grid::with_size(x0, y0, x1, y1, 300, 120);
            let mut pts: Vec<C> = g.points().into_iter().filter(|&z| self.model.contains(z)).collect();
            pts.push(self.z0);
            self.table = pts.par_iter().map(|&z| (z, self.phi(z))).collect();
        }
        let mut z = self.table.iter().min_by(|a, b| (a.1 - w).norm().partial_cmp(&(b.1 - w).norm()).unwrap()).unwrap().0;
        for _ in 0..60 {
            let r = self.phi(z) - w;
            if r.norm() < 1e-12 {
                break;
            }
            let mut step = r / self.dphi(z);
            for _ in 0..40 {
                if self.model.contains(z - step) {
                    break;
                }
                step *= 0.5;
            }
            z -= step;
        }
        z
    }
}

fn deepest_point(model: &Model, b: &[C]) -> C {
    let (x0, y0, x1, y1) = geom::bbox(b.iter().copied());
    let g = crate::contour::Grid::with_size(x0, y0, x1, y1, 160, 60);
    let sub: Vec<C> = b.iter().step_by(4).copied().collect();
    g.points()
        .into_par_iter()
        .filter(|&z| model.contains(z))
        .map(|z| (z, sub.iter().map(|&p| (p - z).norm()).fold(f64::INFINITY, f64::min)))
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
        .map(|x| x.0)
        .unwrap_or(b[0])
}
