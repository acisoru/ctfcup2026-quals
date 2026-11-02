//! Small planar-geometry helpers. Points are complex numbers.

use num_complex::Complex64 as C;
use rayon::prelude::*;

/// A closed polygon ring (first vertex not repeated at the end).
pub type Ring = Vec<C>;

#[inline]
pub fn cross(a: C, b: C) -> f64 {
    (a.conj() * b).im
}

pub fn signed_area(r: &[C]) -> f64 {
    let n = r.len();
    (0..n).map(|i| cross(r[i], r[(i + 1) % n])).sum::<f64>() * 0.5
}

pub fn perimeter(r: &[C]) -> f64 {
    let n = r.len();
    (0..n).map(|i| (r[(i + 1) % n] - r[i]).norm()).sum()
}

/// Even-odd ray casting for one ring.
pub fn point_in_ring(p: C, r: &[C]) -> bool {
    let n = r.len();
    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let (a, b) = (r[i], r[j]);
        if (a.im > p.im) != (b.im > p.im) {
            let x = a.re + (p.im - a.im) * (b.re - a.re) / (b.im - a.im);
            if p.re < x {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

/// Even-odd over several rings (outer outlines and holes together).
pub fn point_in_rings(p: C, rings: &[Ring]) -> bool {
    rings.iter().filter(|r| point_in_ring(p, r)).count() % 2 == 1
}

#[inline]
pub fn closest_on_segment(p: C, a: C, b: C) -> C {
    let ab = b - a;
    let l2 = ab.norm_sqr();
    if l2 == 0.0 {
        return a;
    }
    let t = (((p - a) * ab.conj()).re / l2).clamp(0.0, 1.0);
    a + ab * t
}

#[inline]
pub fn dist_to_segment(p: C, a: C, b: C) -> f64 {
    (p - closest_on_segment(p, a, b)).norm()
}

pub fn dist_to_ring(p: C, r: &[C]) -> f64 {
    let n = r.len();
    (0..n)
        .map(|i| dist_to_segment(p, r[i], r[(i + 1) % n]))
        .fold(f64::INFINITY, f64::min)
}

pub fn dist_to_rings(p: C, rings: &[Ring]) -> f64 {
    rings.iter().map(|r| dist_to_ring(p, r)).fold(f64::INFINITY, f64::min)
}

/// Closest point on one ring.
pub fn closest_on_ring(p: C, r: &[C]) -> C {
    let n = r.len();
    let mut best = (f64::INFINITY, p);
    for i in 0..n {
        let q = closest_on_segment(p, r[i], r[(i + 1) % n]);
        let d = (p - q).norm_sqr();
        if d < best.0 {
            best = (d, q);
        }
    }
    best.1
}

/// Closest point on any of the rings.
pub fn closest_on_rings(p: C, rings: &[Ring]) -> C {
    let mut best = (f64::INFINITY, p);
    for r in rings {
        let n = r.len();
        for i in 0..n {
            let q = closest_on_segment(p, r[i], r[(i + 1) % n]);
            let d = (p - q).norm();
            if d < best.0 {
                best = (d, q);
            }
        }
    }
    best.1
}

/// Distance field over many points (parallel).
pub fn dist_field(points: &[C], rings: &[Ring]) -> Vec<f64> {
    points.par_iter().map(|&p| dist_to_rings(p, rings)).collect()
}

pub fn ink_field(points: &[C], rings: &[Ring]) -> Vec<bool> {
    points.par_iter().map(|&p| point_in_rings(p, rings)).collect()
}

/// Evenly spaced samples (by arclength) along all rings, about `m` in total.
/// Returns (points, unit tangents, ring index of each sample, perimeters).
pub struct Samples {
    pub pts: Vec<C>,
    pub tangents: Vec<C>,
    pub ring: Vec<usize>,
    pub perims: Vec<f64>,
}

pub fn sample_rings(rings: &[Ring], m: usize) -> Samples {
    let perims: Vec<f64> = rings.iter().map(|r| perimeter(r)).collect();
    let total: f64 = perims.iter().sum();
    let ds = total / m as f64;
    let mut out = Samples { pts: vec![], tangents: vec![], ring: vec![], perims: perims.clone() };
    for (ri, r) in rings.iter().enumerate() {
        let n = ((perims[ri] / ds).round() as usize).max(8);
        let step = perims[ri] / n as f64;
        let mut seg = 0usize;
        let mut seg_start = 0.0;
        let nv = r.len();
        for k in 0..n {
            let t = (k as f64 + 0.5) * step;
            loop {
                let len = (r[(seg + 1) % nv] - r[seg]).norm();
                if t <= seg_start + len || seg == nv - 1 {
                    break;
                }
                seg_start += len;
                seg += 1;
            }
            let a = r[seg];
            let b = r[(seg + 1) % nv];
            let e = b - a;
            let len = e.norm().max(1e-300);
            let s = ((t - seg_start) / len).clamp(0.0, 1.0);
            out.pts.push(a + e * s);
            out.tangents.push(e / len);
            out.ring.push(ri);
        }
    }
    out
}

/// Douglas-Peucker simplification of a closed ring.
pub fn simplify_ring(p: &[C], tol: f64) -> Ring {
    if tol <= 0.0 || p.len() < 8 {
        return p.to_vec();
    }
    let i1 = (0..p.len())
        .max_by(|&a, &b| (p[a] - p[0]).norm().partial_cmp(&(p[b] - p[0]).norm()).unwrap())
        .unwrap();
    let mut ring: Vec<C> = p.to_vec();
    ring.push(p[0]);
    let mut keep = vec![false; ring.len()];
    fn dp(pts: &[C], off: usize, tol: f64, keep: &mut [bool]) {
        let mut stack = vec![(0usize, pts.len() - 1)];
        keep[off] = true;
        keep[off + pts.len() - 1] = true;
        while let Some((i, j)) = stack.pop() {
            if j <= i + 1 {
                continue;
            }
            let (a, b) = (pts[i], pts[j]);
            let ab = b - a;
            let (mut best, mut bk) = (-1.0, i);
            for k in i + 1..j {
                let d = if ab.norm() == 0.0 {
                    (pts[k] - a).norm()
                } else {
                    cross(ab, pts[k] - a).abs() / ab.norm()
                };
                if d > best {
                    best = d;
                    bk = k;
                }
            }
            if best > tol {
                keep[off + bk] = true;
                stack.push((i, bk));
                stack.push((bk, j));
            }
        }
    }
    dp(&ring[..=i1], 0, tol, &mut keep);
    dp(&ring[i1..], i1, tol, &mut keep);
    let q: Vec<C> = ring[..ring.len() - 1]
        .iter()
        .zip(keep.iter())
        .filter(|&(_, &k)| k)
        .map(|(&z, _)| z)
        .collect();
    if q.len() >= 3 { q } else { p.to_vec() }
}

/// Convex hull (Andrew's monotone chain), counter-clockwise.
pub fn convex_hull(points: &[C]) -> Vec<C> {
    let mut p: Vec<C> = points.to_vec();
    p.sort_by(|a, b| a.re.partial_cmp(&b.re).unwrap().then(a.im.partial_cmp(&b.im).unwrap()));
    p.dedup();
    if p.len() < 3 {
        return p;
    }
    let mut lower: Vec<C> = vec![];
    for &z in &p {
        while lower.len() >= 2 && cross(lower[lower.len() - 1] - lower[lower.len() - 2], z - lower[lower.len() - 2]) <= 0.0 {
            lower.pop();
        }
        lower.push(z);
    }
    let mut upper: Vec<C> = vec![];
    for &z in p.iter().rev() {
        while upper.len() >= 2 && cross(upper[upper.len() - 1] - upper[upper.len() - 2], z - upper[upper.len() - 2]) <= 0.0 {
            upper.pop();
        }
        upper.push(z);
    }
    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}

/// Inside (or on) a counter-clockwise convex polygon.
pub fn in_convex(p: C, hull: &[C]) -> bool {
    let n = hull.len();
    (0..n).all(|i| cross(hull[(i + 1) % n] - hull[i], p - hull[i]) >= -1e-12)
}

pub fn bbox(points: impl IntoIterator<Item = C>) -> (f64, f64, f64, f64) {
    let mut b = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for z in points {
        b.0 = b.0.min(z.re);
        b.1 = b.1.min(z.im);
        b.2 = b.2.max(z.re);
        b.3 = b.3.max(z.im);
    }
    b
}

/// Wrap an angle to (-pi, pi].
#[inline]
pub fn wrap(a: f64) -> f64 {
    let t = (a + std::f64::consts::PI).rem_euclid(2.0 * std::f64::consts::PI) - std::f64::consts::PI;
    if t <= -std::f64::consts::PI { t + 2.0 * std::f64::consts::PI } else { t }
}
