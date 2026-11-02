//! Minimal SVG figure: panels stacked vertically, each with its own world box.

use crate::region::Region;
use num_complex::Complex64 as C;
use std::fmt::Write;

pub struct Figure {
    width: f64,
    y: f64,
    body: String,
    n_clip: usize,
}

#[derive(Clone, Copy)]
pub struct Panel {
    pub x0: f64,
    pub y0: f64,
    pub x1: f64,
    pub y1: f64,
    px: f64,
    py: f64,
    w: f64,
    h: f64,
    clip: usize,
}

impl Panel {
    #[inline]
    fn tx(&self, z: C) -> (f64, f64) {
        (
            self.px + (z.re - self.x0) / (self.x1 - self.x0) * self.w,
            self.py + (self.y1 - z.im) / (self.y1 - self.y0) * self.h,
        )
    }
    fn scale(&self) -> f64 {
        self.w / (self.x1 - self.x0)
    }
}

fn esc(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}

impl Figure {
    pub fn new(width: f64, title: &str) -> Self {
        let mut f = Figure { width, y: 10.0, body: String::new(), n_clip: 0 };
        let _ = write!(
            f.body,
            r#"<text x="{}" y="{}" font-size="15" text-anchor="middle" font-family="sans-serif">{}</text>"#,
            width / 2.0,
            f.y + 14.0,
            esc(title)
        );
        f.y += 28.0;
        f
    }

    pub fn panel(&mut self, bbox: (f64, f64, f64, f64), title: &str) -> Panel {
        let (x0, y0, x1, y1) = bbox;
        let w = self.width - 20.0;
        let h = w * (y1 - y0) / (x1 - x0);
        let _ = write!(
            self.body,
            r#"<text x="{}" y="{}" font-size="12" text-anchor="middle" font-family="sans-serif">{}</text>"#,
            self.width / 2.0,
            self.y + 13.0,
            esc(title)
        );
        self.y += 20.0;
        let p = Panel { x0, y0, x1, y1, px: 10.0, py: self.y, w, h, clip: self.n_clip };
        let _ = write!(
            self.body,
            r##"<clipPath id="c{}"><rect x="{:.1}" y="{:.1}" width="{:.1}" height="{:.1}"/></clipPath><rect x="{:.1}" y="{:.1}" width="{:.1}" height="{:.1}" fill="#ffffff" stroke="#444" stroke-width="0.8"/>"##,
            p.clip, p.px, p.py, w, h, p.px, p.py, w, h
        );
        self.n_clip += 1;
        self.y += h + 18.0;
        p
    }

    fn d(p: &Panel, curves: &[Vec<C>], closed: bool) -> String {
        let mut s = String::new();
        for c in curves {
            for (i, &z) in c.iter().enumerate() {
                let (x, y) = p.tx(z);
                let _ = write!(s, "{}{:.2} {:.2} ", if i == 0 { "M" } else { "L" }, x, y);
            }
            if closed {
                s.push_str("Z ");
            }
        }
        s
    }

    /// Filled region bounded by closed curves (even-odd rule).
    pub fn fill(&mut self, p: &Panel, curves: &[Vec<C>], color: &str) {
        if curves.is_empty() {
            return;
        }
        let _ = write!(
            self.body,
            r#"<g clip-path="url(#c{})"><path d="{}" fill="{}" fill-rule="evenodd" stroke="none"/></g>"#,
            p.clip,
            Self::d(p, curves, true),
            color
        );
    }

    pub fn fill_stroke(&mut self, p: &Panel, curves: &[Vec<C>], fill: &str, stroke: &str, width: f64) {
        let _ = write!(
            self.body,
            r#"<g clip-path="url(#c{})"><path d="{}" fill="{}" fill-rule="evenodd" stroke="{}" stroke-width="{}"/></g>"#,
            p.clip,
            Self::d(p, curves, true),
            fill,
            stroke,
            width
        );
    }

    pub fn stroke(&mut self, p: &Panel, curves: &[Vec<C>], closed: bool, color: &str, width: f64, dash: Option<&str>) {
        if curves.is_empty() {
            return;
        }
        let dash = dash.map(|d| format!(r#" stroke-dasharray="{d}""#)).unwrap_or_default();
        let _ = write!(
            self.body,
            r#"<g clip-path="url(#c{})"><path d="{}" fill="none" stroke="{}" stroke-width="{}" stroke-linejoin="round"{}/></g>"#,
            p.clip,
            Self::d(p, curves, closed),
            color,
            width,
            dash
        );
    }

    pub fn crosses(&mut self, p: &Panel, pts: &[C], color: &str, size: f64) {
        let mut s = String::new();
        for &z in pts {
            let (x, y) = p.tx(z);
            let _ = write!(s, "M{:.1} {:.1} L{:.1} {:.1} M{:.1} {:.1} L{:.1} {:.1} ", x - size, y - size, x + size, y + size, x - size, y + size, x + size, y - size);
        }
        let _ = write!(self.body, r#"<g clip-path="url(#c{})"><path d="{}" stroke="{}" stroke-width="1.2" fill="none"/></g>"#, p.clip, s, color);
    }

    pub fn dots(&mut self, p: &Panel, pts: &[C], color: &str, r: f64) {
        let mut s = format!(r#"<g clip-path="url(#c{})" fill="{}">"#, p.clip, color);
        for &z in pts {
            let (x, y) = p.tx(z);
            let _ = write!(s, r#"<circle cx="{:.1}" cy="{:.1}" r="{}"/>"#, x, y, r);
        }
        s.push_str("</g>");
        self.body.push_str(&s);
    }

    pub fn region(&mut self, p: &Panel, region: &Region, fill: &str, stroke: &str, dash: Option<&str>) {
        let dash = dash.map(|d| format!(r#" stroke-dasharray="{d}""#)).unwrap_or_default();
        let shape = match *region {
            Region::Box([x0, y0, x1, y1]) => {
                let (ax, ay) = p.tx(C::new(x0, y1));
                let (bx, by) = p.tx(C::new(x1, y0));
                format!(r#"<rect x="{:.1}" y="{:.1}" width="{:.1}" height="{:.1}""#, ax, ay, bx - ax, by - ay)
            }
            Region::Circle([cx, cy, r]) => {
                let (x, y) = p.tx(C::new(cx, cy));
                format!(r#"<circle cx="{:.1}" cy="{:.1}" r="{:.1}""#, x, y, r * p.scale())
            }
        };
        let _ = write!(self.body, r#"<g clip-path="url(#c{})">{} fill="{}" stroke="{}" stroke-width="1"{}/></g>"#, p.clip, shape, fill, stroke, dash);
    }

    pub fn finish(self) -> String {
        format!(
            r##"<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="#ffffff"/>{}</svg>"##,
            self.body,
            w = self.width,
            h = self.y + 6.0
        )
    }
}
