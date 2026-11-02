use std::io::{Read, Write};
use std::sync::mpsc::{self, Receiver};
use std::time::Duration;

use clap::Parser;
use eframe::egui::{self, Color32, Pos2, Rect, Sense, Stroke, Vec2};
use rand::RngExt;

/// Draw a shape, then ask the g(x, y) evaluator on the UART whether a random
/// point inside it is valid (|g| < 1).
#[derive(Parser, Debug, Clone)]
#[command(version, about)]
struct Args {
    /// Serial port of the board, e.g. /dev/ttyUSB0
    #[arg(short, long)]
    port: String,

    /// Baud rate of the serial port (8N1)
    #[arg(short, long, default_value_t = 921_600)]
    baud: u32,

    /// Read timeout in milliseconds when waiting for the device's reply
    /// (a simulated device needs several seconds per evaluation)
    #[arg(short, long, default_value_t = 60_000)]
    timeout_ms: u64,

    /// Coordinate box the canvas maps onto, as x0,y0,x1,y1 (y pointing up).
    /// Default: the region the device answers for.
    #[arg(
        short,
        long,
        value_parser = parse_region,
        default_value = "-3.9,-0.12748074465531917,3.9,0.12748074465531917"
    )]
    region: Region,
}

/// Axis-aligned box in model coordinates.
#[derive(Debug, Clone, Copy, PartialEq)]
struct Region {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
}

fn parse_region(s: &str) -> Result<Region, String> {
    let v: Vec<f64> = s
        .split(',')
        .map(|t| t.trim().parse::<f64>().map_err(|e| format!("{t:?}: {e}")))
        .collect::<Result<_, _>>()?;
    let [x0, y0, x1, y1] = v[..] else {
        return Err("expected x0,y0,x1,y1".into());
    };
    if !(x1 > x0 && y1 > y0) {
        return Err("expected x0 < x1 and y0 < y1".into());
    }
    Ok(Region { x0, y0, x1, y1 })
}

impl Region {
    fn width(&self) -> f64 {
        self.x1 - self.x0
    }
    fn height(&self) -> f64 {
        self.y1 - self.y0
    }

    /// Largest rectangle with this region's aspect ratio centred in `avail`.
    /// The canvas the region is drawn on: the whole available area. The two
    /// axes are scaled independently (the device's region is a 30:1 strip,
    /// which would be unusable at its true aspect ratio).
    fn fit_into(&self, avail: Rect) -> Rect {
        avail
    }

    /// Map a pixel inside `canvas` to model coordinates (y pointing up).
    fn canvas_to_model(&self, p: Pos2, canvas: Rect) -> (f64, f64) {
        let d: Vec2 = p - canvas.min;
        let fx = (d.x / canvas.width()) as f64;
        let fy = (d.y / canvas.height()) as f64;
        (self.x0 + fx * self.width(), self.y1 - fy * self.height())
    }
}

fn main() -> eframe::Result {
    let args = Args::parse();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([960.0, 420.0])
            .with_title("Shape checker"),
        ..Default::default()
    };
    eframe::run_native(
        "Shape checker",
        options,
        Box::new(move |_cc| Ok(Box::new(App::new(args)))),
    )
}

/// Result of one round trip to the device.
struct Verdict {
    title: String,
    body: String,
}

struct App {
    args: Args,
    /// Points of the stroke currently being drawn / last drawn, in canvas coordinates.
    stroke: Vec<Pos2>,
    /// Set while the pointer is held down inside the canvas.
    drawing: bool,
    /// Canvas rectangle from the last frame (the region box in pixels).
    canvas: Rect,
    /// Popup waiting to be shown / currently shown.
    popup: Option<Verdict>,
    /// Pending UART round trip.
    pending: Option<Receiver<Verdict>>,
}

impl App {
    fn new(args: Args) -> Self {
        Self {
            args,
            stroke: Vec::new(),
            drawing: false,
            canvas: Rect::NOTHING,
            popup: None,
            pending: None,
        }
    }

    fn check(&mut self) {
        let Some(poly) = closed_polygon(&self.stroke) else {
            self.popup = Some(Verdict {
                title: "Cannot determine validity".into(),
                body: "Cannot determine validity"
                    .into(),
            });
            return;
        };

        let point = random_point_inside(&poly);
        let (x, y) = self.args.region.canvas_to_model(point, self.canvas);

        let args = self.args.clone();
        let (tx, rx) = mpsc::channel();
        self.pending = Some(rx);
        std::thread::spawn(move || {
            let verdict = match query_device(&args, x as f32, y as f32) {
                Ok(r) => verdict_for(&r),
                Err(e) => Verdict {
                    title: "UART error".into(),
                    body: e,
                },
            };
            let _ = tx.send(verdict);
        });
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        let ctx = &ctx;
        // Collect the result of a finished UART round trip.
        if let Some(rx) = &self.pending {
            match rx.try_recv() {
                Ok(v) => {
                    self.popup = Some(v);
                    self.pending = None;
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    self.popup = Some(Verdict {
                        title: "UART error".into(),
                        body: "worker thread died".into(),
                    });
                    self.pending = None;
                }
                Err(mpsc::TryRecvError::Empty) => ctx.request_repaint_after(Duration::from_millis(50)),
            }
        }

        let busy = self.pending.is_some() || self.popup.is_some();

        egui::Panel::top("toolbar").show(ui, |ui| {
            ui.horizontal(|ui| {
                if ui.add_enabled(!busy, egui::Button::new("Check")).clicked() {
                    self.check();
                }
                if ui.add_enabled(!busy, egui::Button::new("Clear")).clicked() {
                    self.stroke.clear();
                }
                if self.pending.is_some() {
                    ui.spinner();
                    ui.label("waiting for device…");
                }
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let r = &self.args.region;
                    ui.label(format!(
                        "{} @ {} baud   x ∈ [{:.3}, {:.3}]  y ∈ [{:.3}, {:.3}]",
                        self.args.port, self.args.baud, r.x0, r.x1, r.y0, r.y1
                    ));
                });
            });
        });

        egui::CentralPanel::default().show(ui, |ui| {
            let (response, painter) =
                ui.allocate_painter(ui.available_size_before_wrap(), Sense::drag());
            self.canvas = self.args.region.fit_into(response.rect);

            painter.rect_filled(self.canvas, 0.0, Color32::from_gray(245));
            painter.rect_stroke(
                self.canvas,
                0.0,
                Stroke::new(1.0, Color32::from_gray(160)),
                egui::StrokeKind::Inside,
            );

            if !busy {
                if response.drag_started() {
                    self.stroke.clear();
                    self.drawing = true;
                }
                if let Some(p) = response.interact_pointer_pos().filter(|_| self.drawing) {
                    let p = p.clamp(self.canvas.min, self.canvas.max);
                    if self.stroke.last().is_none_or(|l| l.distance(p) >= 1.0) {
                        self.stroke.push(p);
                    }
                }
                if response.drag_stopped() {
                    self.drawing = false;
                }
            }

            if self.stroke.len() >= 2 {
                painter.add(egui::Shape::line(
                    self.stroke.clone(),
                    Stroke::new(2.0, Color32::from_rgb(30, 60, 200)),
                ));
                if !self.drawing && closed_polygon(&self.stroke).is_some() {
                    // Show the implicit closing segment.
                    painter.line_segment(
                        [*self.stroke.last().unwrap(), self.stroke[0]],
                        Stroke::new(1.0, Color32::from_rgb(30, 60, 200)),
                    );
                }
            } else if let Some(&p) = self.stroke.first() {
                painter.circle_filled(p, 1.5, Color32::from_rgb(30, 60, 200));
            }

            if self.stroke.is_empty() {
                painter.text(
                    self.canvas.center(),
                    egui::Align2::CENTER_CENTER,
                    "Draw a closed shape with the mouse, then press Check",
                    egui::FontId::proportional(16.0),
                    Color32::from_gray(120),
                );
            }
        });

        if let Some(v) = &self.popup {
            let mut close = false;
            egui::Modal::new(egui::Id::unique("verdict")).show(ctx, |ui| {
                ui.set_width(420.0);
                ui.heading(&v.title);
                ui.separator();
                ui.label(egui::RichText::new(&v.body).monospace());
                ui.add_space(8.0);
                ui.vertical_centered(|ui| {
                    if ui.button("OK").clicked() {
                        close = true;
                    }
                });
            });
            if close || ctx.input(|i| i.key_pressed(egui::Key::Escape) || i.key_pressed(egui::Key::Enter)) {
                self.popup = None;
            }
        }
    }
}

/// Distance (in canvas pixels) within which the end of a stroke counts as meeting its start.
const CLOSE_TOLERANCE: f32 = 20.0;
/// Minimum enclosed area (in square pixels) for a shape to count as enclosing a region.
const MIN_AREA: f32 = 25.0;

/// Interpret the stroke as a closed polygon if it encloses a region, else None.
fn closed_polygon(stroke: &[Pos2]) -> Option<Vec<Pos2>> {
    if stroke.len() < 3 {
        return None;
    }
    let first = stroke[0];
    let last = *stroke.last().unwrap();
    if first.distance(last) > CLOSE_TOLERANCE {
        return None;
    }
    if shoelace_area(stroke).abs() < MIN_AREA {
        return None;
    }
    Some(stroke.to_vec())
}

fn shoelace_area(poly: &[Pos2]) -> f32 {
    let n = poly.len();
    let mut s = 0.0;
    for i in 0..n {
        let a = poly[i];
        let b = poly[(i + 1) % n];
        s += a.x * b.y - b.x * a.y;
    }
    s / 2.0
}

/// Even-odd point-in-polygon test.
fn contains(poly: &[Pos2], p: Pos2) -> bool {
    let n = poly.len();
    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let (a, b) = (poly[i], poly[j]);
        if (a.y > p.y) != (b.y > p.y) {
            let x = a.x + (p.y - a.y) / (b.y - a.y) * (b.x - a.x);
            if p.x < x {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

/// Uniformly random point inside the polygon by rejection sampling over its bounding box.
fn random_point_inside(poly: &[Pos2]) -> Pos2 {
    let bb = Rect::from_points(poly);
    let mut rng = rand::rng();
    loop {
        let p = Pos2::new(
            rng.random_range(bb.min.x..=bb.max.x),
            rng.random_range(bb.min.y..=bb.max.y),
        );
        if contains(poly, p) {
            return p;
        }
    }
}

// ---------------------------------------------------------------------------
// UART protocol of the Versal g(x, y) evaluator (little endian, fp32/int32, 8N1)
//
//   request  A5 | x[4] | y[4] | xor(x, y bytes)                     10 bytes
//   reply    5A | re[4] | im[4] | e[4] | flags | xor(bytes 1..13)   15 bytes
//
//   g(x + iy) = (re + i*im) * 2^e,  max(|re|, |im|) in [1, 2)
// ---------------------------------------------------------------------------

const SYNC_IN: u8 = 0xA5;
const SYNC_OUT: u8 = 0x5A;
const FLAG_INSIDE: u8 = 0x01;
const FLAG_POLE: u8 = 0x02;
const FLAG_ZERO: u8 = 0x04;
const FLAG_BAD: u8 = 0x80;

#[derive(Debug, Clone, Copy, PartialEq)]
struct Reply {
    re: f32,
    im: f32,
    e: i32,
    flags: u8,
}

impl Reply {
    /// |g|^2 = (re^2 + im^2) * 4^e, i.e. the x'^2 + y'^2 of the reply.
    /// Saturates to +inf / 0 beyond f64 range, which compares correctly against 1.
    fn abs2(&self) -> f64 {
        let m = (self.re as f64).powi(2) + (self.im as f64).powi(2);
        m * 2f64.powi(2 * self.e)
    }

    fn log2_abs(&self) -> f64 {
        self.e as f64 + 0.5 * ((self.re as f64).powi(2) + (self.im as f64).powi(2)).log2()
    }
}

fn xor(bytes: &[u8]) -> u8 {
    bytes.iter().fold(0, |a, b| a ^ b)
}

fn encode_request(x: f32, y: f32) -> [u8; 10] {
    let mut out = [0u8; 10];
    out[0] = SYNC_IN;
    out[1..5].copy_from_slice(&x.to_le_bytes());
    out[5..9].copy_from_slice(&y.to_le_bytes());
    out[9] = xor(&out[1..9]);
    out
}

/// Parse the 14 bytes following the reply sync byte.
fn parse_reply(body: &[u8; 14]) -> Result<Reply, String> {
    if xor(&body[..13]) != body[13] {
        return Err(format!("reply checksum error: {body:02x?}"));
    }
    Ok(Reply {
        re: f32::from_le_bytes(body[0..4].try_into().unwrap()),
        im: f32::from_le_bytes(body[4..8].try_into().unwrap()),
        e: i32::from_le_bytes(body[8..12].try_into().unwrap()),
        flags: body[12],
    })
}

/// Send one request over the UART and read the device's reply.
fn query_device(args: &Args, x: f32, y: f32) -> Result<Reply, String> {
    let mut port = serialport::new(&args.port, args.baud)
        .timeout(Duration::from_millis(args.timeout_ms))
        .open()
        .map_err(|e| format!("cannot open {}: {e}", args.port))?;
    let _ = port.clear(serialport::ClearBuffer::Input);

    port.write_all(&encode_request(x, y))
        .map_err(|e| format!("write failed: {e}"))?;
    port.flush().map_err(|e| format!("flush failed: {e}"))?;

    // Skip line noise until the reply header.
    let mut b = [0u8; 1];
    loop {
        port.read_exact(&mut b)
            .map_err(|e| format!("no reply from the evaluator: {e}"))?;
        if b[0] == SYNC_OUT {
            break;
        }
    }
    let mut body = [0u8; 14];
    port.read_exact(&mut body)
        .map_err(|e| format!("short reply: {e}"))?;
    parse_reply(&body)
}

fn verdict_for(r: &Reply) -> Verdict {
    if r.flags & FLAG_BAD != 0 {
        return Verdict {
            title: "UART error".into(),
            body: "the device rejected the request checksum".into(),
        };
    }
    let abs2 = r.abs2();
    let mut body = format!(
        "|g|^2 = {abs2:.6e}   log2|g| = {:.3}\n\
         flags = {:#04x}",
        r.log2_abs(),
        r.flags
    );
    if r.flags & FLAG_POLE != 0 {
        body.push_str("  (pole)");
    }
    if r.flags & FLAG_ZERO != 0 {
        body.push_str("  (zero)");
    }
    if r.flags & FLAG_INSIDE != 0 {
        body.push_str("  (device says inside)");
    }
    let valid = r.flags & FLAG_POLE == 0 && abs2 < 1.0;
    Verdict {
        title: if valid { "Possibly valid" } else { "Definitely invalid" }.into(),
        body,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn square() -> Vec<Pos2> {
        vec![
            Pos2::new(0.0, 0.0),
            Pos2::new(100.0, 0.0),
            Pos2::new(100.0, 100.0),
            Pos2::new(0.0, 100.0),
            Pos2::new(3.0, 2.0), // ends near the start
        ]
    }

    #[test]
    fn open_stroke_is_not_closed() {
        let s = vec![Pos2::new(0.0, 0.0), Pos2::new(100.0, 0.0), Pos2::new(100.0, 100.0)];
        assert!(closed_polygon(&s).is_none());
    }

    #[test]
    fn degenerate_stroke_is_not_closed() {
        let s = vec![Pos2::new(0.0, 0.0), Pos2::new(100.0, 0.0), Pos2::new(1.0, 0.0)];
        assert!(closed_polygon(&s).is_none());
    }

    #[test]
    fn square_is_closed_and_samples_inside() {
        let poly = closed_polygon(&square()).expect("square encloses a region");
        for _ in 0..1000 {
            let p = random_point_inside(&poly);
            assert!(contains(&poly, p));
            assert!((0.0..=100.0).contains(&p.x) && (0.0..=100.0).contains(&p.y));
        }
        assert!(!contains(&poly, Pos2::new(150.0, 50.0)));
    }

    #[test]
    fn region_parse_and_map() {
        let r = parse_region("-1, -2, 3, 2").unwrap();
        assert_eq!(r, Region { x0: -1.0, y0: -2.0, x1: 3.0, y1: 2.0 });
        assert!(parse_region("1,2,3").is_err());
        assert!(parse_region("3,0,1,2").is_err());

        let canvas = r.fit_into(Rect::from_min_size(Pos2::new(0.0, 0.0), Vec2::new(1000.0, 400.0)));
        assert_eq!(canvas.size(), Vec2::new(1000.0, 400.0));
        assert_eq!(canvas.center(), Pos2::new(500.0, 200.0));

        // top-left pixel -> (x0, y1); bottom-right -> (x1, y0)
        let (x, y) = r.canvas_to_model(canvas.min, canvas);
        assert!((x + 1.0).abs() < 1e-9 && (y - 2.0).abs() < 1e-9);
        let (x, y) = r.canvas_to_model(canvas.max, canvas);
        assert!((x - 3.0).abs() < 1e-9 && (y + 2.0).abs() < 1e-9);
    }

    #[test]
    fn request_framing() {
        let req = encode_request(0.3, 0.4);
        assert_eq!(req[0], SYNC_IN);
        assert_eq!(&req[1..5], &0.3f32.to_le_bytes());
        assert_eq!(&req[5..9], &0.4f32.to_le_bytes());
        assert_eq!(req[9], xor(&req[1..9]));
    }

    fn reply_bytes(r: Reply) -> [u8; 14] {
        let mut b = [0u8; 14];
        b[0..4].copy_from_slice(&r.re.to_le_bytes());
        b[4..8].copy_from_slice(&r.im.to_le_bytes());
        b[8..12].copy_from_slice(&r.e.to_le_bytes());
        b[12] = r.flags;
        b[13] = xor(&b[..13]);
        b
    }

    #[test]
    fn reply_parsing_and_verdict() {
        let inside = Reply { re: 0.1885649, im: -1.2016612, e: -15, flags: FLAG_INSIDE };
        let mut b = reply_bytes(inside);
        assert_eq!(parse_reply(&b).unwrap(), inside);
        assert!(inside.abs2() < 1.0);
        assert_eq!(verdict_for(&inside).title, "Possibly valid");
        b[13] ^= 1;
        assert!(parse_reply(&b).is_err());

        let outside = Reply { re: -0.04379527, im: -1.1819633, e: 271, flags: 0 };
        assert!(outside.abs2() > 1.0);
        assert_eq!(verdict_for(&outside).title, "Definitely invalid");

        // beyond f64 range: saturates but still compares correctly
        let huge = Reply { re: 1.0, im: 0.0, e: 2000, flags: 0 };
        assert_eq!(verdict_for(&huge).title, "Definitely invalid");
        let tiny = Reply { re: 1.0, im: 0.0, e: -2000, flags: FLAG_INSIDE };
        assert_eq!(verdict_for(&tiny).title, "Possibly valid");

        let pole = Reply { re: f32::NAN, im: f32::NAN, e: 0, flags: FLAG_POLE };
        assert_eq!(verdict_for(&pole).title, "Definitely invalid");
        let zero = Reply { re: 0.0, im: 0.0, e: 0, flags: FLAG_ZERO | FLAG_INSIDE };
        assert_eq!(verdict_for(&zero).title, "Possibly valid");
        let bad = Reply { re: 0.0, im: 0.0, e: 0, flags: FLAG_BAD };
        assert_eq!(verdict_for(&bad).title, "UART error");
    }
}

/// End-to-end UART tests through a pty. Run with `cargo test -- --ignored`.
#[cfg(test)]
mod uart_tests {
    use super::*;
    use std::io::{BufRead, BufReader};
    use std::process::{Child, Command, Stdio};

    fn test_args(port: String) -> Args {
        Args {
            port,
            baud: 921_600,
            timeout_ms: 2000,
            region: parse_region("0,0,1,1").unwrap(),
        }
    }

    // Fake device speaking the protocol: answers g = (x + iy) * 2^0 after some line noise.
    const FAKE_DEVICE: &str = r#"
import os, pty, struct, time, tty
master, slave = pty.openpty()
tty.setraw(master); tty.setraw(slave)
print(os.ttyname(slave), flush=True)
buf = b""
while len(buf) < 10:
    buf += os.read(master, 10 - len(buf))
assert buf[0] == 0xA5
chk = 0
for b in buf[1:9]: chk ^= b
assert chk == buf[9]
x, y = struct.unpack("<ff", buf[1:9])
body = struct.pack("<ffiB", x, y, 0, 1 if x*x + y*y < 1 else 0)
ck = 0
for b in body: ck ^= b
os.write(master, b"\x00\xff" + bytes([0x5A]) + body + bytes([ck]))
time.sleep(0.5)
"#;

    fn spawn_fake() -> (Child, String) {
        let mut child = Command::new("python3")
            .args(["-I", "-c", FAKE_DEVICE])
            .stdout(Stdio::piped())
            .spawn()
            .expect("python3");
        let mut line = String::new();
        BufReader::new(child.stdout.take().unwrap()).read_line(&mut line).unwrap();
        (child, line.trim().to_string())
    }

    #[test]
    #[ignore]
    fn round_trip_through_pty() {
        let (mut child, port) = spawn_fake();
        let r = query_device(&test_args(port), 0.5, -0.25).expect("round trip");
        assert_eq!(r, Reply { re: 0.5, im: -0.25, e: 0, flags: FLAG_INSIDE });
        assert_eq!(verdict_for(&r).title, "Possibly valid");
        let _ = child.wait();

        let (mut child, port) = spawn_fake();
        let r = query_device(&test_args(port), 3.0, 4.0).expect("round trip");
        assert_eq!(verdict_for(&r).title, "Definitely invalid");
        let _ = child.wait();
    }

    /// Talks to the real kernel (desktop emulator from `make emulator` in
    /// ../generator/5_versal_dsp58/build) bridged to a pty by socat.
    #[test]
    #[ignore]
    fn against_emulator() {
        let emu = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../generator/5_versal_dsp58/build/g_uart_emulator"
        );
        if !std::path::Path::new(emu).exists() {
            eprintln!("emulator not built, skipping");
            return;
        }
        let link = std::env::temp_dir().join(format!("g_emu_{}.pty", std::process::id()));
        let mut socat = Command::new("socat")
            .arg(format!("pty,raw,echo=0,link={}", link.display()))
            .arg(format!("EXEC:{emu}"))
            .stderr(Stdio::null())
            .spawn()
            .expect("socat");
        while !link.exists() {
            std::thread::sleep(Duration::from_millis(20));
        }
        let args = test_args(link.to_string_lossy().into_owned());

        let r = query_device(&args, 0.3, 0.4).expect("inside query");
        assert_eq!(r.flags & FLAG_INSIDE, FLAG_INSIDE);
        assert_eq!(verdict_for(&r).title, "Possibly valid");

        let r = query_device(&args, 3.0, 0.85).expect("outside query");
        assert_eq!(r.flags & FLAG_INSIDE, 0);
        assert_eq!(verdict_for(&r).title, "Definitely invalid");

        let _ = socat.kill();
        let _ = socat.wait();
    }
}
