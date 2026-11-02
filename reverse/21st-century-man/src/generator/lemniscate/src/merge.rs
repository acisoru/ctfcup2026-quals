//! Merge all glyphs of a string into ONE polygon: bridges join separate
//! pieces, slits open holes to the outside.

use crate::geom::{self, Ring};
use geo::{Area, BooleanOps, Centroid, Coord, LineString, MultiPolygon, Polygon};
use num_complex::Complex64 as C;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Connect {
    Nearest,
    Underline,
    None,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Holes {
    /// slit every hole open to the outside -> one simple polygon
    Cut,
    /// keep holes as inner boundaries
    Keep,
    /// drop holes
    Fill,
}

fn ls(r: &[C]) -> LineString<f64> {
    let mut v: Vec<Coord<f64>> = r.iter().map(|z| Coord { x: z.re, y: z.im }).collect();
    v.push(v[0]);
    LineString::new(v)
}

fn ring_of(l: &LineString<f64>) -> Ring {
    let mut r: Ring = l.0.iter().map(|c| C::new(c.x, c.y)).collect();
    if r.len() > 1 && (r[0] - r[r.len() - 1]).norm() < 1e-12 {
        r.pop();
    }
    r
}

fn rings_of(p: &Polygon<f64>) -> Vec<Ring> {
    let mut v = vec![ring_of(p.exterior())];
    v.extend(p.interiors().iter().map(ring_of));
    v
}

fn parts(mp: MultiPolygon<f64>) -> Vec<Polygon<f64>> {
    mp.0.into_iter().filter(|p| p.unsigned_area() > 1e-7).collect()
}

/// Rectangle of the given width from pa to pb, extended by `width` into both ends.
fn bar(pa: C, pb: C, width: f64) -> Polygon<f64> {
    let d = pb - pa;
    let l = d.norm();
    let u = if l > 0.0 { d / l } else { C::new(0.0, 1.0) };
    let n = u * C::i() * (width / 2.0);
    let a = pa - u * width;
    let b = pb + u * width;
    Polygon::new(ls(&[a + n, b + n, b - n, a - n]), vec![])
}

/// Nearest pair of points (on ring a, on ring b).
fn nearest_pair(a: &[C], b: &[C]) -> (C, C, f64) {
    let mut best = (a[0], b[0], f64::INFINITY);
    let one = |p: C, r: &[C]| geom::closest_on_ring(p, r);
    for &p in a {
        let q = one(p, b);
        let d = (p - q).norm();
        if d < best.2 {
            best = (p, q, d);
        }
    }
    for &q in b {
        let p = one(q, a);
        let d = (p - q).norm();
        if d < best.2 {
            best = (p, q, d);
        }
    }
    best
}

fn poly_distance(a: &[Ring], b: &[Ring]) -> f64 {
    let mut d = f64::INFINITY;
    for ra in a {
        for &p in ra {
            d = d.min(geom::dist_to_rings(p, b));
        }
    }
    for rb in b {
        for &p in rb {
            d = d.min(geom::dist_to_rings(p, a));
        }
    }
    d
}

/// Union of all glyphs (even-odd fill) joined into one polygon.
/// Returns rings and depths (0 = outline, 1 = hole) like `font::text_rings`.
pub fn merge_to_one_polygon(
    rings: &[Ring],
    connect: Connect,
    bridge: f64,
    holes: Holes,
    slit: f64,
) -> Result<(Vec<Ring>, Vec<usize>), String> {
    // even-odd fill of all glyph contours
    let subject = MultiPolygon::new(rings.iter().map(|r| Polygon::new(ls(r), vec![])).collect());
    let mut shape = subject.union(&MultiPolygon::<f64>::new(vec![]));

    if connect == Connect::Underline {
        let (x0, _, x1, _) = geom::bbox(rings.iter().flatten().copied());
        let b = Polygon::new(
            ls(&[
                C::new(x0, -1.2 * bridge),
                C::new(x1, -1.2 * bridge),
                C::new(x1, 0.35 * bridge),
                C::new(x0, 0.35 * bridge),
            ]),
            vec![],
        );
        shape = shape.union(&b);
    }

    if connect != Connect::None {
        loop {
            let mut ps = parts(shape.clone());
            if ps.len() <= 1 {
                shape = MultiPolygon::new(ps);
                break;
            }
            ps.sort_by(|a, b| b.unsigned_area().partial_cmp(&a.unsigned_area()).unwrap());
            let main = rings_of(&ps[0]);
            let (oi, _) = ps[1..]
                .iter()
                .enumerate()
                .map(|(i, p)| (i + 1, poly_distance(&main, &rings_of(p))))
                .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
                .unwrap();
            let other = rings_of(&ps[oi]);
            // aim at the piece's centre so the bridge sits mid-gap
            let c = ps[oi].centroid().map(|p| C::new(p.x(), p.y())).unwrap_or(other[0][0]);
            let pb = geom::closest_on_rings(c, &main);
            let pa = geom::closest_on_rings(pb, &other);
            shape = shape.union(&bar(pb, pa, bridge));
        }
    }

    let mut out_rings = vec![];
    let mut out_depth = vec![];
    for p in parts(shape) {
        let p = match holes {
            Holes::Fill => Polygon::new(p.exterior().clone(), vec![]),
            Holes::Cut => {
                let mut q = p;
                while !q.interiors().is_empty() {
                    q = cut_one_hole(&q, slit)?;
                }
                q
            }
            Holes::Keep => p,
        };
        let rs = rings_of(&p);
        for (k, r) in rs.into_iter().enumerate() {
            out_rings.push(r);
            out_depth.push(if k == 0 { 0 } else { 1 });
        }
    }
    Ok((out_rings, out_depth))
}

/// Open the hole closest to the outside with a slit that keeps the polygon in
/// one piece, preferring short slits that open into free space (so a smoothed
/// outline can follow them into the hole).
fn cut_one_hole(p: &Polygon<f64>, slit: f64) -> Result<Polygon<f64>, String> {
    let ext = ring_of(p.exterior());
    let holes: Vec<Ring> = p.interiors().iter().map(ring_of).collect();
    let (hi, _) = holes
        .iter()
        .enumerate()
        .map(|(i, h)| (i, nearest_pair(h, &ext).2))
        .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
        .unwrap();
    let h = &holes[hi];
    let (pa0, pb0, _) = nearest_pair(h, &ext);
    let mut targets = vec![(pa0, pb0)];
    let mut verts: Vec<C> = ext.clone();
    let hv = vec![h.clone()];
    verts.sort_by(|a, b| geom::dist_to_rings(*a, &hv).partial_cmp(&geom::dist_to_rings(*b, &hv)).unwrap());
    for &q in verts.iter().take(60) {
        targets.push((geom::closest_on_rings(q, &hv), q));
    }
    let n_int = p.interiors().len();
    let mut best: Option<(f64, Polygon<f64>)> = None;
    for (pa, pb) in targets {
        let qs = parts(p.difference(&bar(pa, pb, slit)));
        if qs.len() != 1 || qs[0].interiors().len() >= n_int {
            continue;
        }
        let q = qs.into_iter().next().unwrap();
        let d = pb - pa;
        let l = d.norm();
        let u = if l > 0.0 { d / l } else { C::new(0.0, 1.0) };
        let probe = pb + u * 0.15;
        let qr = rings_of(&q);
        let room = if geom::point_in_rings(probe, &qr) { 0.0 } else { geom::dist_to_rings(probe, &qr).min(0.15) };
        let score = room - 0.5 * l;
        if best.as_ref().map_or(true, |b| score > b.0) {
            best = Some((score, q));
        }
    }
    best.map(|b| b.1).ok_or_else(|| {
        "could not slit a hole open without splitting the polygon; try a smaller --slit or --holes keep/fill".to_string()
    })
}
