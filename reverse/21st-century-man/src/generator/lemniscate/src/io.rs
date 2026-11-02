//! JSON model file and CSV output.

use crate::diskmap::DiskMap;
use crate::geom::Ring;
use crate::lemniscate::Model;
use crate::region::{Region, RegionReport};
use num_complex::Complex64 as C;
use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::Path;

pub const DESCRIPTION: &str = "h(z) = prod_j (z - zeros[j]) / ( exp(log_c) * prod_k (z - poles[k])^pole_orders[k] ). \
The smoothed text is S = { z : |h(z)| < 1 } (one simply connected region; 'outline' traces its boundary |h| = 1). \
h is holomorphic on the region except at the poles inside it (h = infinity there); it maps S into |z| < 1 and every \
other point of the region into |z| > 1. 'disk_map' is the one-to-one conformal map phi of S onto |w| < 1: \
phi(z) = (z - z0) * exp( q0 + sum_k q[k] log(z - charges[k]) - i theta0 ), using the branch \
sum_k q[k] log(z - c_k) = sum_{k<K-1} s_k Log((z - c_k)/(z - c_{k+1})) with s_k = q[0]+..+q[k] (sum q = 0), so the branch cuts are the segments between consecutive charges.";

#[derive(Serialize, Deserialize)]
pub struct DiskMapFile {
    pub z0: [f64; 2],
    pub charges: Vec<[f64; 2]>,
    pub q: Vec<f64>,
    pub q0: f64,
    pub theta0: f64,
    pub boundary_error: f64,
    pub winding: f64,
}

#[derive(Serialize, Deserialize)]
pub struct ModelFile {
    pub description: String,
    pub text: String,
    pub degree: usize,
    pub zeros: Vec<[f64; 2]>,
    pub poles: Vec<[f64; 2]>,
    pub pole_orders: Vec<u32>,
    pub log_c: f64,
    pub clearance: f64,
    pub region: Region,
    pub region_report: Option<RegionReport>,
    /// the one polygon the text was turned into (outline first, then any holes)
    pub polygon: Vec<Vec<[f64; 2]>>,
    /// boundary of the smoothed text, |h| = 1
    pub outline: Vec<[f64; 2]>,
    pub disk_map: Option<DiskMapFile>,
}

fn xy(z: &C) -> [f64; 2] {
    [z.re, z.im]
}
fn cz(p: &[f64; 2]) -> C {
    C::new(p[0], p[1])
}

impl ModelFile {
    #[allow(clippy::too_many_arguments)]
    pub fn new(text: &str, model: &Model, region: Region, report: Option<RegionReport>, rings: &[Ring], outline: &[C], map: Option<&DiskMap>) -> Self {
        ModelFile {
            description: DESCRIPTION.into(),
            text: text.into(),
            degree: model.zeros.len(),
            zeros: model.zeros.iter().map(xy).collect(),
            poles: model.poles.iter().map(xy).collect(),
            pole_orders: model.mults.clone(),
            log_c: model.logc,
            clearance: model.clearance,
            region,
            region_report: report,
            polygon: rings.iter().map(|r| r.iter().map(xy).collect()).collect(),
            outline: outline.iter().map(xy).collect(),
            disk_map: map.map(|m| DiskMapFile {
                z0: xy(&m.z0),
                charges: m.zeta.iter().map(xy).collect(),
                q: m.q.clone(),
                q0: m.q0,
                theta0: m.theta0,
                boundary_error: m.boundary_error,
                winding: m.winding,
            }),
        }
    }
    pub fn model(&self) -> Model {
        Model {
            zeros: self.zeros.iter().map(cz).collect(),
            poles: self.poles.iter().map(cz).collect(),
            mults: self.pole_orders.clone(),
            logc: self.log_c,
            clearance: self.clearance,
            gap: f64::NAN,
            filled: 0,
        }
    }
    pub fn disk_map(&self) -> Option<DiskMap> {
        self.disk_map.as_ref().map(|d| {
            DiskMap::from_parts(self.model(), cz(&d.z0), d.charges.iter().map(cz).collect(), d.q.clone(), d.q0, d.theta0)
        })
    }
    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        std::fs::write(path, serde_json::to_string(self).unwrap())
    }
    pub fn load(path: &Path) -> Result<Self, String> {
        let s = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        serde_json::from_str(&s).map_err(|e| format!("{}: {e}", path.display()))
    }
}

/// CSV of rings: '# outline' / '# hole' header lines, then "x,y" per vertex.
pub fn write_rings_csv(path: &Path, rings: &[Ring], depth: &[usize]) -> std::io::Result<()> {
    let mut f = std::io::BufWriter::new(std::fs::File::create(path)?);
    for (r, d) in rings.iter().zip(depth) {
        writeln!(f, "{}", if d % 2 == 1 { "# hole" } else { "# outline" })?;
        for z in r {
            writeln!(f, "{:.6},{:.6}", z.re, z.im)?;
        }
    }
    Ok(())
}

pub fn write_curve_csv(path: &Path, c: &[C]) -> std::io::Result<()> {
    let mut f = std::io::BufWriter::new(std::fs::File::create(path)?);
    writeln!(f, "x,y")?;
    for z in c {
        writeln!(f, "{:.9},{:.9}", z.re, z.im)?;
    }
    Ok(())
}

/// Parse "x,y" (also "x y").
pub fn parse_point(s: &str) -> Result<C, String> {
    let v: Vec<f64> = s
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter(|t| !t.is_empty())
        .map(|t| t.parse::<f64>().map_err(|e| format!("bad number '{t}': {e}")))
        .collect::<Result<_, _>>()?;
    if v.len() != 2 {
        return Err(format!("expected 'x,y', got '{s}'"));
    }
    Ok(C::new(v[0], v[1]))
}
