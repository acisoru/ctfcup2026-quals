//! text_lemniscate: write a string as ONE polygon, smooth it into S = {|h| < 1}
//! with h holomorphic on a chosen box/circle except at a few poles, so that
//! h maps S into |z| < 1 and the rest of the box/circle into |z| > 1, and
//! compute the conformal map of S onto the unit disk.

use clap::{Args, Parser, Subcommand, ValueEnum};
use num_complex::Complex64 as C;
use rayon::prelude::*;
use std::path::PathBuf;
use std::time::Instant;
use text_lemniscate::contour::{self, Grid};
use text_lemniscate::io::{self, ModelFile};
use text_lemniscate::lemniscate::{self, outline_curves, BuildOptions};
use text_lemniscate::merge::{self, Connect, Holes};
use text_lemniscate::region::{self, Region};
use text_lemniscate::svg::Figure;
use text_lemniscate::{font, geom, DiskMap};

#[derive(Parser)]
#[command(name = "text_lemniscate", version, about = "Smooth text into a region S = {|h| < 1}: h maps S into |z|<1 and the rest of a box/circle into |z|>1; plus the conformal map of S onto the disk.")]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Build the polygon, the function h, the disk map; write SVG / JSON / CSV.
    Build(BuildArgs),
    /// Evaluate h (and the disk map) from a saved model at given points.
    Eval(EvalArgs),
}

#[derive(Clone, Copy, ValueEnum)]
enum ConnectArg {
    Nearest,
    Underline,
    None,
}
#[derive(Clone, Copy, ValueEnum)]
enum HolesArg {
    Cut,
    Keep,
    Fill,
}
#[derive(Clone, Copy, ValueEnum)]
enum RegionArg {
    Box,
    Circle,
}

#[derive(Args)]
struct BuildArgs {
    /// the string to draw
    text: String,
    /// number of zeros of h; several values make one set of panels each
    #[arg(short, long, num_args = 1.., default_values_t = [1500])]
    degree: Vec<usize>,
    /// extra space between letters (font-size units)
    #[arg(long, default_value_t = 0.15)]
    spacing: f64,
    /// how pieces are joined into one polygon
    #[arg(long, value_enum, default_value_t = ConnectArg::Nearest)]
    connect: ConnectArg,
    /// holes: cut = slit open (one simple polygon), keep, fill
    #[arg(long, value_enum, default_value_t = HolesArg::Cut)]
    holes: HolesArg,
    /// bridge width
    #[arg(long, default_value_t = 0.06)]
    bridge: f64,
    /// slit width
    #[arg(long, default_value_t = 0.08)]
    slit: f64,
    /// keep the smoothed outline within this distance of the text ('auto' or a number; 0 = no poles)
    #[arg(long, default_value = "auto")]
    clearance: String,
    /// rounds of adaptive pole placement
    #[arg(long, default_value_t = 12)]
    max_iter: usize,
    /// log-level above the text: |h| = e^-offset on the letters
    #[arg(long, default_value_t = 1.0)]
    offset: f64,
    /// TrueType/OpenType font file (default: built-in DejaVu Sans Bold)
    #[arg(long)]
    font: Option<PathBuf>,
    /// polygon simplification tolerance
    #[arg(long, default_value_t = 0.004)]
    simplify: f64,
    /// bounding region on which h is used
    #[arg(long, value_enum, default_value_t = RegionArg::Box)]
    region: RegionArg,
    /// margin of the automatic box/circle around the text
    #[arg(long, default_value_t = 0.15)]
    margin: f64,
    /// explicit region: "x0,y0,x1,y1" (box) or "cx,cy,r" (circle)
    #[arg(long, allow_hyphen_values = true)]
    bounds: Option<String>,
    /// point "x,y" sent to 0 by the disk map (default: deepest point of S)
    #[arg(long, allow_hyphen_values = true)]
    center: Option<String>,
    /// skip the conformal disk map
    #[arg(long)]
    no_map: bool,
    /// disk map: spacing of the outline points (default: min(clearance/5, length/800), finer at tight bends)
    #[arg(long)]
    map_spacing: Option<f64>,
    /// disk map: distance of the charges outside the outline, in point spacings
    #[arg(long, default_value_t = 2.0)]
    map_charge: f64,
    /// panels per degree: any of overlay,smooth,function,map
    #[arg(long, default_value = "overlay,function,map")]
    panels: String,
    /// plot grid points per font-size unit
    #[arg(long, default_value_t = 200)]
    res: usize,
    /// SVG figure
    #[arg(short, long, default_value = "text_lemniscate.svg")]
    out: PathBuf,
    /// JSON model of the last degree (h, region, outline, disk map)
    #[arg(long)]
    model: Option<PathBuf>,
    /// CSV of the polygon
    #[arg(long)]
    polygon: Option<PathBuf>,
    /// CSV of the smoothed outline |h| = 1 (last degree)
    #[arg(long)]
    outline: Option<PathBuf>,
    /// less output
    #[arg(short, long)]
    quiet: bool,
}

#[derive(Args)]
struct EvalArgs {
    /// model JSON written by `build --model`
    #[arg(long)]
    model: PathBuf,
    /// file with one "x,y" per line
    #[arg(long)]
    points: Option<PathBuf>,
    /// a point "x,y" (repeatable)
    #[arg(long = "at", allow_hyphen_values = true)]
    at: Vec<String>,
    /// a disk point "u,v" to map back into the text with the inverse disk map (repeatable)
    #[arg(long = "inverse", allow_hyphen_values = true)]
    inverse: Vec<String>,
}

fn main() {
    let cli = Cli::parse();
    let r = match cli.cmd {
        Cmd::Build(a) => build(a),
        Cmd::Eval(a) => eval(a),
    };
    if let Err(e) = r {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

fn parse_nums(s: &str) -> Result<Vec<f64>, String> {
    s.split(',').map(|t| t.trim().parse::<f64>().map_err(|e| format!("bad number '{t}': {e}"))).collect()
}

/// Closed curves of {v < 0} with the grid border forced outside (for fills).
fn fill_curves(g: &Grid, v: &[f64]) -> Vec<Vec<C>> {
    let mut w = v.to_vec();
    for k in g.border() {
        w[k] = 1.0;
    }
    contour::closed_curves(g, &w, 0.0)
}

fn build(a: BuildArgs) -> Result<(), String> {
    let font_data: Vec<u8> = match &a.font {
        Some(p) => std::fs::read(p).map_err(|e| format!("{}: {e}", p.display()))?,
        None => font::DEFAULT_FONT.to_vec(),
    };
    let (glyph_rings, depth) = font::text_rings(&a.text, &font_data, a.spacing, a.simplify)?;
    let nholes = depth.iter().filter(|d| *d % 2 == 1).count();
    println!("\"{}\": glyphs give {} outlines ({} holes)", a.text, glyph_rings.len(), nholes);
    let connect = match a.connect {
        ConnectArg::Nearest => Connect::Nearest,
        ConnectArg::Underline => Connect::Underline,
        ConnectArg::None => Connect::None,
    };
    let holes = match a.holes {
        HolesArg::Cut => Holes::Cut,
        HolesArg::Keep => Holes::Keep,
        HolesArg::Fill => Holes::Fill,
    };
    let merged = connect != Connect::None || holes != Holes::Keep;
    let (rings, depth) = if merged {
        merge::merge_to_one_polygon(&glyph_rings, connect, a.bridge, holes, a.slit)?
    } else {
        (glyph_rings.clone(), depth)
    };
    let nouter = depth.iter().filter(|d| *d % 2 == 0).count();
    let nh = depth.len() - nouter;
    let shape_desc = if nouter == 1 && nh == 0 { "ONE simple polygon".to_string() } else { format!("{nouter} polygon(s) with {nh} hole(s)") };
    println!("  -> {shape_desc}, {} vertices", rings.iter().map(|r| r.len()).sum::<usize>());
    if let Some(p) = &a.polygon {
        io::write_rings_csv(p, &rings, &depth).map_err(|e| e.to_string())?;
        println!("  polygon written to {}", p.display());
    }

    let bb = geom::bbox(rings.iter().flatten().copied());
    let region = match (&a.bounds, a.region) {
        (Some(s), _) => {
            let v = parse_nums(s)?;
            match v.len() {
                4 => Region::Box([v[0], v[1], v[2], v[3]]),
                3 => Region::Circle([v[0], v[1], v[2]]),
                _ => return Err("--bounds wants x0,y0,x1,y1 or cx,cy,r".into()),
            }
        }
        (None, RegionArg::Box) => Region::auto_box(bb, a.margin),
        (None, RegionArg::Circle) => Region::auto_circle(bb, a.margin),
    };
    println!("  region: {}", region.describe());
    let center = a.center.as_deref().map(io::parse_point).transpose()?;
    let clearance = if a.clearance == "auto" { None } else { Some(a.clearance.parse::<f64>().map_err(|e| format!("--clearance: {e}"))?) };
    let panels: Vec<String> = a.panels.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
    for p in &panels {
        if !["overlay", "smooth", "function", "map"].contains(&p.as_str()) {
            return Err(format!("unknown panel '{p}'"));
        }
    }
    let do_map = !a.no_map && holes != Holes::Keep;
    if !a.no_map && holes == Holes::Keep {
        println!("  (--holes keep: the smoothed region has holes, so no conformal map onto the disk exists; skipping it)");
    }

    // plotting area: the region plus a little room
    let (rx0, ry0, rx1, ry1) = region.bbox();
    let (px0, py0, px1, py1) = (rx0.min(bb.0) - 0.08, ry0.min(bb.1) - 0.08, rx1.max(bb.2) + 0.08, ry1.max(bb.3) + 0.08);
    let nxp = ((px1 - px0) * a.res as f64) as usize;
    let nyp = ((py1 - py0) * a.res as f64) as usize;
    let gp = Grid::with_size(px0, py0, px1, py1, nxp.max(50), nyp.max(20));
    let gpts = gp.points();
    let mut fig = Figure::new(1000.0, &format!("\"{}\" as {}  —  h maps the smoothed text into |z|<1, the rest of the {} into |z|>1", a.text, shape_desc, match region { Region::Box(_) => "box", Region::Circle(_) => "circle" }));

    let mut last: Option<(lemniscate::Model, Vec<C>, Option<DiskMap>, region::RegionReport)> = None;
    for &n in &a.degree {
        let t0 = Instant::now();
        println!("  degree {n}:");
        let opt = BuildOptions {
            degree: n,
            offset: a.offset,
            clearance,
            max_iter: a.max_iter,
            simply_connected: holes != Holes::Keep,
            zero_depth: None,
            verbose: !a.quiet,
        };
        let model = lemniscate::build(&rings, &depth, &opt);
        let npoles: u32 = model.mults.iter().sum();
        let kind = if npoles == 0 { "polynomial".to_string() } else { format!("{} poles, total order {npoles}", model.poles.len()) };
        let gap_txt = if model.gap == 0.0 { format!("outline within {:.3} of the text", model.clearance) } else { format!("target {:.3}, worst pocket {:.3}", model.clearance, model.gap) };
        let filled_txt = if model.filled > 0 { format!(", {} pocket(s) filled to stay simply connected", model.filled) } else { String::new() };
        println!("    {kind}; {gap_txt}{filled_txt}  ({:.1}s)", t0.elapsed().as_secs_f64());

        // the outline of S, the disk map, and the region check
        let map = if do_map {
            match DiskMap::new(&model, &rings, center, a.map_spacing, a.map_charge, !a.quiet) {
                Ok(m) => Some(m),
                Err(e) => {
                    println!("    {e}");
                    None
                }
            }
        } else {
            None
        };
        let outline: Vec<C> = match &map {
            Some(m) => m.boundary.clone(),
            None => {
                let mut cs = outline_curves(&model, &rings, model.clearance.max(0.02) / 6.0);
                cs.sort_by(|x, y| geom::signed_area(y).abs().partial_cmp(&geom::signed_area(x).abs()).unwrap());
                cs.into_iter().next().unwrap_or_default()
            }
        };
        let report = region::verify(&model, &region, &outline, 500);
        println!(
            "    region check: smoothed text {} the region (min log|h| on its edge = {:.2}); {} pole(s) inside the region (h = inf there); \
             {} of {} sample points outside the text land in |z|<1",
            if report.text_inside_region { "fits inside" } else { "does NOT fit inside" },
            report.min_log_abs_on_edge,
            report.poles_in_region.len(),
            report.violations,
            report.samples
        );
        if !report.text_inside_region {
            println!("    warning: enlarge the region (--margin / --bounds); part of the smoothed text lies outside it");
        }

        // ----- panels -----
        let lg = model.log_abs_many(&gpts);
        let s_curves = fill_curves(&gp, &lg);
        let pbox = (px0, py0, px1, py1);
        for panel in &panels {
            match panel.as_str() {
                "overlay" => {
                    let p = fig.panel(pbox, &format!("degree {n}: polygon, smoothed outline |h| = 1 (red), poles (x) — {kind}; {gap_txt}{filled_txt}"));
                    fig.fill(&p, &s_curves, "#cfe3f7");
                    fig.fill_stroke(&p, &rings, "#8c8c8c", "#000", 0.6);
                    if merged {
                        fig.stroke(&p, &glyph_rings, true, "#f2f2f2", 0.5, None);
                    }
                    fig.stroke(&p, &[outline.clone()], true, "#d62728", 1.6, None);
                    fig.crosses(&p, &model.poles, "#9467bd", 3.5);
                    fig.region(&p, &region, "none", "#333", Some("6 4"));
                }
                "smooth" => {
                    let p = fig.panel(pbox, &format!("degree {n}: the smoothed text S alone"));
                    fig.fill(&p, &s_curves, "#1f3b73");
                }
                "function" => {
                    let p = fig.panel(
                        pbox,
                        &format!(
                            "degree {n}: h on the region — |h|<1 on S (blue), |h|>1 elsewhere (orange); level curves |h| = 1/4, 1/2 | 1 | 2, 8, 64; h = inf at the {} dot(s); {} violations",
                            report.poles_in_region.len(),
                            report.violations
                        ),
                    );
                    fig.region(&p, &region, "#fde3c8", "none", None);
                    fig.fill(&p, &s_curves, "#cfe3f7");
                    let masked: Vec<f64> = gpts.par_iter().zip(lg.par_iter()).map(|(&z, &v)| if region.contains(z) { v } else { f64::NAN }).collect();
                    for &lev in &[0.25f64, 0.5] {
                        let cs: Vec<Vec<C>> = contour::contour_lines(&gp, &masked, lev.ln()).into_iter().map(|c| c.0).collect();
                        fig.stroke(&p, &cs, false, "#1f77b4", 0.6, None);
                    }
                    for &lev in &[2.0f64, 8.0, 64.0] {
                        let cs: Vec<Vec<C>> = contour::contour_lines(&gp, &masked, lev.ln()).into_iter().map(|c| c.0).collect();
                        fig.stroke(&p, &cs, false, "#e6862e", 0.6, None);
                    }
                    fig.stroke(&p, &[outline.clone()], true, "#000", 1.2, None);
                    let pin: Vec<C> = report.poles_in_region.iter().map(|q| C::new(q[0], q[1])).collect();
                    fig.dots(&p, &pin, "#000", 2.2);
                    fig.region(&p, &region, "none", "#333", None);
                }
                "map" => {
                    let Some(m) = &map else { continue };
                    let p = fig.panel(
                        pbox,
                        &format!(
                            "degree {n}: conformal map of S onto |w|<1 — preimages of |w| = r (blue) and rays (orange); max ||phi|-1| on outline {:.0e}, winding {:.4}",
                            m.boundary_error, m.winding
                        ),
                    );
                    fig.fill(&p, &s_curves, "#eef4fb");
                    fig.stroke(&p, &[outline.clone()], true, "#000", 1.0, None);
                    let mres = a.res.min(160);
                    let gm = Grid::with_size(px0, py0, px1, py1, ((px1 - px0) * mres as f64) as usize, ((py1 - py0) * mres as f64) as usize);
                    let w: Vec<C> = m.to_disk_many(&gm.points());
                    let r: Vec<f64> = w.iter().map(|z| z.norm()).collect();
                    for &rad in &[0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 0.99, 0.999, 0.9999] {
                        let cs: Vec<Vec<C>> = contour::contour_lines(&gm, &r, rad).into_iter().map(|c| c.0).collect();
                        fig.stroke(&p, &cs, false, "#1f77b4", 0.6, None);
                    }
                    for k in 0..24 {
                        let rot = C::from_polar(1.0, -2.0 * std::f64::consts::PI * k as f64 / 24.0);
                        let f: Vec<f64> = w.iter().map(|&z| {
                            let q = z * rot;
                            if q.re > 0.0 { q.im } else { f64::NAN }
                        }).collect();
                        let cs: Vec<Vec<C>> = contour::contour_lines(&gm, &f, 0.0).into_iter().map(|c| c.0).collect();
                        fig.stroke(&p, &cs, false, "#ff7f0e", 0.6, None);
                    }
                    fig.dots(&p, &[m.z0], "#d62728", 3.0);
                }
                _ => {}
            }
        }
        println!("    ({:.1}s)", t0.elapsed().as_secs_f64());
        last = Some((model, outline, map, report));
    }

    std::fs::write(&a.out, fig.finish()).map_err(|e| e.to_string())?;
    println!("saved {}", a.out.display());
    if let Some((model, outline, map, report)) = last {
        if let Some(p) = &a.outline {
            io::write_curve_csv(p, &outline).map_err(|e| e.to_string())?;
            println!("smoothed outline written to {}", p.display());
        }
        if let Some(p) = &a.model {
            ModelFile::new(&a.text, &model, region, Some(report), &rings, &outline, map.as_ref()).save(p).map_err(|e| e.to_string())?;
            println!("model written to {}  (evaluate with: text_lemniscate eval --model {} --at x,y)", p.display(), p.display());
        }
    }
    Ok(())
}

fn eval(a: EvalArgs) -> Result<(), String> {
    let mf = ModelFile::load(&a.model)?;
    let model = mf.model();
    let mut map = mf.disk_map();
    let mut pts: Vec<C> = a.at.iter().map(|s| io::parse_point(s)).collect::<Result<_, _>>()?;
    if let Some(p) = &a.points {
        let s = std::fs::read_to_string(p).map_err(|e| format!("{}: {e}", p.display()))?;
        for line in s.lines() {
            let t = line.trim();
            if t.is_empty() || t.starts_with('#') || t.starts_with('x') {
                continue;
            }
            pts.push(io::parse_point(t)?);
        }
    }
    if !pts.is_empty() {
        println!("x,y,in_text,in_region,h_re,h_im,abs_h,log_abs_h,phi_re,phi_im");
        for z in pts {
            let h = model.eval(z);
            let inside = model.contains(z);
            let phi = match &map {
                Some(m) if inside => m.phi(z),
                _ => C::new(f64::NAN, f64::NAN),
            };
            println!(
                "{},{},{},{},{:.12e},{:.12e},{:.12e},{:.12},{:.15},{:.15}",
                z.re,
                z.im,
                inside as u8,
                mf.region.contains(z) as u8,
                h.re,
                h.im,
                model.log_abs(z).exp(),
                model.log_abs(z),
                phi.re,
                phi.im
            );
        }
    }
    if !a.inverse.is_empty() {
        let Some(m) = map.as_mut() else { return Err("the model has no disk map".into()) };
        println!("u,v,x,y");
        for s in &a.inverse {
            let w = io::parse_point(s)?;
            if w.norm() >= 1.0 {
                println!("{},{},nan,nan", w.re, w.im);
                continue;
            }
            let z = m.from_disk(w);
            println!("{},{},{:.15},{:.15}", w.re, w.im, z.re, z.im);
        }
    }
    Ok(())
}
