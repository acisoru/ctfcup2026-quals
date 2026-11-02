//! Marching squares: level curves of a scalar field sampled on a grid.

use num_complex::Complex64 as C;
use std::collections::HashMap;

/// A rectangular grid of sample points: x = x0 + j*dx, y = y0 + i*dy,
/// stored row-major (row i, column j).
#[derive(Clone, Debug)]
pub struct Grid {
    pub x0: f64,
    pub y0: f64,
    pub dx: f64,
    pub dy: f64,
    pub nx: usize,
    pub ny: usize,
}

impl Grid {
    pub fn new(x0: f64, y0: f64, x1: f64, y1: f64, cell: f64) -> Self {
        let nx = (((x1 - x0) / cell).ceil() as usize).max(2) + 1;
        let ny = (((y1 - y0) / cell).ceil() as usize).max(2) + 1;
        Grid { x0, y0, dx: cell, dy: cell, nx, ny }
    }
    pub fn with_size(x0: f64, y0: f64, x1: f64, y1: f64, nx: usize, ny: usize) -> Self {
        Grid { x0, y0, dx: (x1 - x0) / (nx - 1) as f64, dy: (y1 - y0) / (ny - 1) as f64, nx, ny }
    }
    #[inline]
    pub fn point(&self, i: usize, j: usize) -> C {
        C::new(self.x0 + j as f64 * self.dx, self.y0 + i as f64 * self.dy)
    }
    pub fn len(&self) -> usize {
        self.nx * self.ny
    }
    pub fn points(&self) -> Vec<C> {
        let mut v = Vec::with_capacity(self.len());
        for i in 0..self.ny {
            for j in 0..self.nx {
                v.push(self.point(i, j));
            }
        }
        v
    }
    /// Nearest grid cell (clamped) as a flat index.
    pub fn index_of(&self, z: C) -> usize {
        let j = (((z.re - self.x0) / self.dx).round().max(0.0) as usize).min(self.nx - 1);
        let i = (((z.im - self.y0) / self.dy).round().max(0.0) as usize).min(self.ny - 1);
        i * self.nx + j
    }
    pub fn border(&self) -> impl Iterator<Item = usize> + '_ {
        let (nx, ny) = (self.nx, self.ny);
        (0..nx).chain((ny - 1) * nx..ny * nx).chain((0..ny).map(move |i| i * nx)).chain((0..ny).map(move |i| i * nx + nx - 1))
    }
}

/// Level curves {v = level}. Cells with a NaN corner are skipped.
/// Returns polylines and whether each one is closed.
pub fn contour_lines(g: &Grid, v: &[f64], level: f64) -> Vec<(Vec<C>, bool)> {
    let (nx, ny) = (g.nx, g.ny);
    let nh = ny * (nx - 1);
    let h_edge = |j: usize, i: usize| i * (nx - 1) + j; // (j,i)-(j+1,i)
    let v_edge = |j: usize, i: usize| nh + i * nx + j; // (j,i)-(j,i+1)
    let edge_point = |e: usize| -> C {
        let (a, b) = if e < nh {
            let i = e / (nx - 1);
            let j = e % (nx - 1);
            (i * nx + j, i * nx + j + 1)
        } else {
            let k = e - nh;
            (k, k + nx)
        };
        let (va, vb) = (v[a] - level, v[b] - level);
        let t = if va == vb { 0.5 } else { (va / (va - vb)).clamp(0.0, 1.0) };
        let pa = g.point(a / nx, a % nx);
        let pb = g.point(b / nx, b % nx);
        pa + (pb - pa) * t
    };

    let mut segs: Vec<(usize, usize)> = vec![];
    for i in 0..ny - 1 {
        for j in 0..nx - 1 {
            let a = v[i * nx + j];
            let b = v[i * nx + j + 1];
            let c = v[(i + 1) * nx + j + 1];
            let d = v[(i + 1) * nx + j];
            if a.is_nan() || b.is_nan() || c.is_nan() || d.is_nan() {
                continue;
            }
            let case = (a >= level) as u8 | ((b >= level) as u8) << 1 | ((c >= level) as u8) << 2 | ((d >= level) as u8) << 3;
            let bottom = h_edge(j, i);
            let top = h_edge(j, i + 1);
            let left = v_edge(j, i);
            let right = v_edge(j + 1, i);
            let center_up = (a + b + c + d) / 4.0 >= level;
            match case {
                0 | 15 => {}
                1 | 14 => segs.push((left, bottom)),
                2 | 13 => segs.push((bottom, right)),
                3 | 12 => segs.push((left, right)),
                4 | 11 => segs.push((right, top)),
                6 | 9 => segs.push((bottom, top)),
                7 | 8 => segs.push((left, top)),
                5 => {
                    if center_up {
                        segs.push((bottom, right));
                        segs.push((top, left));
                    } else {
                        segs.push((left, bottom));
                        segs.push((right, top));
                    }
                }
                10 => {
                    if center_up {
                        segs.push((left, bottom));
                        segs.push((right, top));
                    } else {
                        segs.push((bottom, right));
                        segs.push((top, left));
                    }
                }
                _ => unreachable!(),
            }
        }
    }

    // chain segments through shared edges
    let mut by_edge: HashMap<usize, Vec<usize>> = HashMap::new();
    for (k, &(e1, e2)) in segs.iter().enumerate() {
        by_edge.entry(e1).or_default().push(k);
        by_edge.entry(e2).or_default().push(k);
    }
    let mut used = vec![false; segs.len()];
    let mut out = vec![];
    for s0 in 0..segs.len() {
        if used[s0] {
            continue;
        }
        used[s0] = true;
        let (start, mut cur) = segs[s0];
        let mut fwd = vec![start, cur];
        let mut closed = false;
        loop {
            let next = by_edge.get(&cur).and_then(|ks| ks.iter().copied().find(|&k| !used[k]));
            match next {
                Some(k) => {
                    used[k] = true;
                    let (e1, e2) = segs[k];
                    cur = if e1 == cur { e2 } else { e1 };
                    if cur == start {
                        closed = true;
                        break;
                    }
                    fwd.push(cur);
                }
                None => break,
            }
        }
        if !closed {
            // extend backwards from the start
            let mut back = vec![];
            let mut cur = start;
            while let Some(k) = by_edge.get(&cur).and_then(|ks| ks.iter().copied().find(|&k| !used[k])) {
                used[k] = true;
                let (e1, e2) = segs[k];
                cur = if e1 == cur { e2 } else { e1 };
                back.push(cur);
            }
            back.reverse();
            back.extend(fwd);
            fwd = back;
        }
        out.push((fwd.into_iter().map(edge_point).collect(), closed));
    }
    out
}

/// Only the closed curves.
pub fn closed_curves(g: &Grid, v: &[f64], level: f64) -> Vec<Vec<C>> {
    contour_lines(g, v, level).into_iter().filter(|(c, closed)| *closed && c.len() > 3).map(|(c, _)| c).collect()
}

/// 4-connected component labels of a boolean mask (0 = background).
pub fn label(mask: &[bool], nx: usize, ny: usize) -> (Vec<u32>, u32) {
    let mut lab = vec![0u32; mask.len()];
    let mut n = 0u32;
    let mut stack = vec![];
    for s in 0..mask.len() {
        if !mask[s] || lab[s] != 0 {
            continue;
        }
        n += 1;
        lab[s] = n;
        stack.push(s);
        while let Some(k) = stack.pop() {
            let (i, j) = (k / nx, k % nx);
            let mut visit = |m: usize| {
                if mask[m] && lab[m] == 0 {
                    lab[m] = n;
                    stack.push(m);
                }
            };
            if j > 0 {
                visit(k - 1);
            }
            if j + 1 < nx {
                visit(k + 1);
            }
            if i > 0 {
                visit(k - nx);
            }
            if i + 1 < ny {
                visit(k + nx);
            }
        }
    }
    (lab, n)
}

/// Cells of the mask with a 4-neighbour outside it (or on the grid border).
pub fn edge_cells(mask: &[bool], nx: usize, ny: usize) -> usize {
    (0..mask.len())
        .filter(|&k| {
            if !mask[k] {
                return false;
            }
            let (i, j) = (k / nx, k % nx);
            j == 0 || j + 1 == nx || i == 0 || i + 1 == ny || !mask[k - 1] || !mask[k + 1] || !mask[k - nx] || !mask[k + nx]
        })
        .count()
}

/// Binary dilation with the 4-neighbour cross, `iters` times.
pub fn dilate(mask: &[bool], nx: usize, ny: usize, iters: usize) -> Vec<bool> {
    let mut m = mask.to_vec();
    for _ in 0..iters {
        let prev = m.clone();
        for k in 0..m.len() {
            if prev[k] {
                continue;
            }
            let (i, j) = (k / nx, k % nx);
            m[k] = (j > 0 && prev[k - 1]) || (j + 1 < nx && prev[k + 1]) || (i > 0 && prev[k - nx]) || (i + 1 < ny && prev[k + nx]);
        }
    }
    m
}
