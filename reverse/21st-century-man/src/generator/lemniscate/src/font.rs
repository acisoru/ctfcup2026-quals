//! Text -> polygons: glyph outlines from a TrueType/OpenType font, flattened
//! to straight segments, at font size 1 (one em = 1 unit).

use crate::geom::{self, Ring};
use num_complex::Complex64 as C;
use ttf_parser::{Face, GlyphId, OutlineBuilder};

/// DejaVu Sans Bold (Bitstream Vera / DejaVu license, see assets/LICENSE_DEJAVU).
pub static DEFAULT_FONT: &[u8] = include_bytes!("../assets/DejaVuSans-Bold.ttf");

struct Flatten {
    scale: f64,
    dx: f64,
    rings: Vec<Ring>,
    cur: Ring,
    last: C,
}

impl Flatten {
    fn p(&self, x: f32, y: f32) -> C {
        C::new(self.dx + x as f64 * self.scale, y as f64 * self.scale)
    }
    fn finish(&mut self) {
        if self.cur.len() >= 3 {
            let mut r = std::mem::take(&mut self.cur);
            if (r[0] - r[r.len() - 1]).norm() < 1e-12 {
                r.pop();
            }
            self.rings.push(r);
        }
        self.cur.clear();
    }
}

impl OutlineBuilder for Flatten {
    fn move_to(&mut self, x: f32, y: f32) {
        self.finish();
        let p = self.p(x, y);
        self.cur.push(p);
        self.last = p;
    }
    fn line_to(&mut self, x: f32, y: f32) {
        let p = self.p(x, y);
        self.cur.push(p);
        self.last = p;
    }
    fn quad_to(&mut self, x1: f32, y1: f32, x: f32, y: f32) {
        let (p0, p1, p2) = (self.last, self.p(x1, y1), self.p(x, y));
        let n = 10;
        for k in 1..=n {
            let t = k as f64 / n as f64;
            let q = p0 * (1.0 - t) * (1.0 - t) + p1 * 2.0 * t * (1.0 - t) + p2 * t * t;
            self.cur.push(q);
        }
        self.last = p2;
    }
    fn curve_to(&mut self, x1: f32, y1: f32, x2: f32, y2: f32, x: f32, y: f32) {
        let (p0, p1, p2, p3) = (self.last, self.p(x1, y1), self.p(x2, y2), self.p(x, y));
        let n = 14;
        for k in 1..=n {
            let t = k as f64 / n as f64;
            let u = 1.0 - t;
            let q = p0 * u * u * u + p1 * 3.0 * u * u * t + p2 * 3.0 * u * t * t + p3 * t * t * t;
            self.cur.push(q);
        }
        self.last = p3;
    }
    fn close(&mut self) {
        self.finish();
    }
}

fn kerning(face: &Face, left: GlyphId, right: GlyphId) -> i16 {
    if let Some(kern) = face.tables().kern {
        for st in kern.subtables {
            if st.horizontal && !st.variable {
                if let Some(k) = st.glyphs_kerning(left, right) {
                    return k;
                }
            }
        }
    }
    0
}

/// Glyph outlines of `text` as rings plus their nesting depth
/// (even depth = outer outline of a letter, odd depth = outline of a hole).
/// `spacing` adds extra space between characters (font-size units);
/// `simplify` is the Douglas-Peucker tolerance.
pub fn text_rings(
    text: &str,
    font: &[u8],
    spacing: f64,
    simplify: f64,
) -> Result<(Vec<Ring>, Vec<usize>), String> {
    let face = Face::parse(font, 0).map_err(|e| format!("cannot parse font: {e}"))?;
    let scale = 1.0 / face.units_per_em() as f64;
    let mut fl = Flatten { scale, dx: 0.0, rings: vec![], cur: vec![], last: C::new(0.0, 0.0) };
    let mut pen = 0.0;
    let mut prev: Option<GlyphId> = None;
    for (i, ch) in text.chars().enumerate() {
        let gid = face.glyph_index(ch).unwrap_or(GlyphId(0));
        if let Some(pg) = prev {
            pen += kerning(&face, pg, gid) as f64 * scale;
        }
        if !ch.is_whitespace() {
            fl.dx = pen + i as f64 * spacing;
            face.outline_glyph(gid, &mut fl);
            fl.finish();
        }
        pen += face.glyph_hor_advance(gid).unwrap_or(0) as f64 * scale;
        prev = Some(gid);
    }
    let mut rings: Vec<Ring> = vec![];
    for r in fl.rings {
        let mut q: Ring = Vec::with_capacity(r.len());
        for z in r {
            if q.last().map_or(true, |&l: &C| (l - z).norm() > 1e-9) {
                q.push(z);
            }
        }
        while q.len() > 1 && (q[0] - q[q.len() - 1]).norm() <= 1e-9 {
            q.pop();
        }
        let q = geom::simplify_ring(&q, simplify);
        if q.len() >= 3 && geom::signed_area(&q).abs() > 1e-5 {
            rings.push(q);
        }
    }
    if rings.is_empty() {
        return Err("the string produced no outlines (empty or only spaces?)".into());
    }
    let depth = ring_depths(&rings);
    Ok((rings, depth))
}

/// Nesting depth of each ring = number of other rings containing it.
pub fn ring_depths(rings: &[Ring]) -> Vec<usize> {
    (0..rings.len())
        .map(|i| {
            (0..rings.len())
                .filter(|&j| j != i && geom::point_in_ring(rings[i][0], &rings[j]))
                .count()
        })
        .collect()
}
