use text_lemniscate::contour::{self, Grid};
use text_lemniscate::lemniscate::{self, outline_curves, BuildOptions};
use text_lemniscate::merge::{self, Connect, Holes};
use text_lemniscate::{font, geom, region, DiskMap, Region, C};

#[test]
fn contour_of_a_circle_is_one_closed_curve() {
    let g = Grid::new(-2.0, -2.0, 2.0, 2.0, 0.02);
    let v: Vec<f64> = g.points().iter().map(|z| z.norm() - 1.0).collect();
    let cs = contour::closed_curves(&g, &v, 0.0);
    assert_eq!(cs.len(), 1);
    let a = geom::signed_area(&cs[0]).abs();
    assert!((a - std::f64::consts::PI).abs() < 1e-2, "area {a}");
}

#[test]
fn text_becomes_one_simple_polygon() {
    let (rings, _) = font::text_rings("Bob 8", font::DEFAULT_FONT, 0.15, 0.004).unwrap();
    let (one, depth) = merge::merge_to_one_polygon(&rings, Connect::Nearest, 0.06, Holes::Cut, 0.08).unwrap();
    assert_eq!(one.len(), 1, "one ring");
    assert_eq!(depth, vec![0]);
}

/// The main requirement: h maps the smoothed text into |z| < 1 and every
/// other point of the region into |z| > 1 (or is infinite at a pole); the
/// smoothed text is simply connected and its disk map is one-to-one.
#[test]
fn h_separates_text_from_rest_of_region() {
    let (rings, _) = font::text_rings("Hi", font::DEFAULT_FONT, 0.15, 0.004).unwrap();
    let (one, depth) = merge::merge_to_one_polygon(&rings, Connect::Nearest, 0.06, Holes::Cut, 0.08).unwrap();
    let opt = BuildOptions { degree: 400, ..Default::default() };
    let model = lemniscate::build(&one, &depth, &opt);
    // the polygon is inside S
    for r in &one {
        for &z in r {
            assert!(model.log_abs(z) < 0.0);
        }
    }
    // S has one outline curve (simply connected)
    let curves = outline_curves(&model, &one, model.clearance / 6.0);
    assert_eq!(curves.len(), 1);
    // region check
    let reg = Region::auto_box(geom::bbox(one.iter().flatten().copied()), 0.15);
    let rep = region::verify(&model, &reg, &curves[0], 300);
    assert!(rep.text_inside_region);
    assert_eq!(rep.violations, 0);
    // disk map: one-to-one, |phi| = 1 on the outline, round trip
    let mut m = DiskMap::new(&model, &one, None, None, 2.0, false).unwrap();
    assert!((m.winding - 1.0).abs() < 1e-6);
    assert!(m.boundary_error < 1e-4, "boundary error {}", m.boundary_error);
    let w = C::new(0.3, -0.2);
    let z = m.from_disk(w);
    assert!((m.to_disk(z) - w).norm() < 1e-10);
}
