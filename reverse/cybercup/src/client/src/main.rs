#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

mod checker;
mod renderer;

use std::io::Cursor;
use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui::{self, Align2, Color32, FontId, Id, Pos2, Rect, Sense, Stroke, Vec2};
use rodio::Source as _;

const TRACK: &[u8] = include_bytes!("../assets/sgm.mp3");
const ENVELOPE: &[u8] = include_bytes!("../assets/envelope.bin");
const ICON: &[u8] = include_bytes!("../assets/icon.rgba");
const ENV_RATE: f32 = 60.0;

#[inline(never)]
fn main() {
    app_entry();
}

#[inline(never)]
fn app_entry() -> ! {
    let title = "CYBERCUP";
    let options = eframe::NativeOptions {
        renderer: eframe::Renderer::Wgpu,
        viewport: egui::ViewportBuilder::default()
            .with_title(title)
            .with_icon(egui::IconData {
                rgba: ICON.to_vec(),
                width: 64,
                height: 64,
            })
            .with_inner_size([1100.0, 720.0])
            .with_min_inner_size([450.0, 400.0]),
        ..Default::default()
    };
    let result = eframe::run_native(
        title,
        options,
        Box::new(|cc| Ok(Box::new(FlagApp::new(cc)))),
    );
    match result {
        Ok(()) => std::process::exit(0),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}

struct Music {
    _device: rodio::MixerDeviceSink,
    player: rodio::Player,
}

impl Music {
    #[inline(never)]
    fn start() -> Option<Self> {
        let device = rodio::DeviceSinkBuilder::open_default_sink().ok()?;
        let player = rodio::Player::connect_new(device.mixer());
        let decoder = rodio::Decoder::try_from(Cursor::new(TRACK)).ok()?;
        player.set_volume(0.7);
        player.append(decoder.repeat_infinite());
        Some(Self {
            _device: device,
            player,
        })
    }

    fn seconds(&self) -> f32 {
        self.player.get_pos().as_secs_f32()
    }
}

#[inline(never)]
fn spectrum_at(seconds: f32) -> [f32; 5] {
    let frame_count = ENVELOPE.len() / 20;
    let position = seconds * ENV_RATE;
    let frame = (position as usize) % frame_count;
    let next = (frame + 1) % frame_count;
    let t = position.fract();
    let decode = |index: usize, band: usize| -> f32 {
        let start = index * 20 + band * 4;
        f32::from_le_bytes(ENVELOPE[start..start + 4].try_into().unwrap())
    };
    let result =
        std::array::from_fn(|band| decode(frame, band) * (1.0 - t) + decode(next, band) * t);
    result
}

#[derive(Clone, Copy, PartialEq)]
enum Verdict {
    Ok,
    Fail,
}

struct Ripple {
    origin: Pos2,
    started: Instant,
}

struct FlagApp {
    flag: String,
    verdict: Option<Verdict>,
    verdict_at: Instant,
    ripple: Option<Ripple>,
    music: Option<Music>,
    started: Instant,
    visual_phase: f32,
}

impl FlagApp {
    #[inline(never)]
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        renderer::install(cc).unwrap();
        cc.egui_ctx.set_visuals(egui::Visuals::dark());
        let mut fonts = egui::FontDefinitions::default();
        let font_name = "rajdhani".to_owned();
        fonts.font_data.insert(
            font_name.clone(),
            Arc::new(egui::FontData::from_static(include_bytes!(
                "../assets/Rajdhani-SemiBold.ttf"
            ))),
        );
        fonts
            .families
            .get_mut(&egui::FontFamily::Proportional)
            .unwrap()
            .insert(0, font_name);
        cc.egui_ctx.set_fonts(fonts);
        let music = Music::start();
        Self {
            flag: String::new(),
            verdict: None,
            verdict_at: Instant::now(),
            ripple: None,
            music,
            started: Instant::now(),
            visual_phase: 0.0,
        }
    }

    #[inline(never)]
    fn check(&mut self) {
        self.verdict = Some(if checker::verify(self.flag.trim()) {
            Verdict::Ok
        } else {
            Verdict::Fail
        });
        self.verdict_at = Instant::now();
    }


    #[inline(never)]
    fn menu(&mut self, ctx: &egui::Context, screen: Rect, time: f32) {
        let width = (screen.width() - 32.0).min(510.0);
        let panel = Rect::from_center_size(screen.center(), Vec2::new(width, 238.0));
        let left = panel.left();
        let cyan = Color32::from_rgb(56, 218, 233);
        let red = Color32::from_rgb(235, 70, 68);
        let dark = Color32::from_rgba_unmultiplied(23, 7, 13, 210);
        let block_top = panel.top() + 64.0;
        let input = Rect::from_min_size(
            Pos2::new(left + 30.0, block_top),
            Vec2::new(width - 60.0, 44.0),
        );
        let button = Rect::from_min_size(
            Pos2::new(left + 30.0, block_top + 65.0),
            Vec2::new(width - 60.0, 43.0),
        );

        egui::Area::new(Id::new(0xA76C_32E1_u32))
            .fixed_pos(panel.min)
            .order(egui::Order::Foreground)
            .show(ctx, |ui| {
                ui.set_min_size(panel.size());
                let p = ui.painter().clone();
                p.rect_filled(panel, 0.0, dark);
                p.rect_filled(
                    Rect::from_min_size(panel.min, Vec2::new(2.0, panel.height())),
                    0.0,
                    Color32::from_rgb(105, 22, 29),
                );
                for y in (0..panel.height() as i32).step_by(4) {
                    let yy = panel.top() + y as f32;
                    p.line_segment(
                        [
                            Pos2::new(panel.left() + 3.0, yy),
                            Pos2::new(panel.right() - 1.0, yy),
                        ],
                        Stroke::new(1.0, Color32::from_rgba_unmultiplied(165, 35, 44, 14)),
                    );
                }
                for (a, b) in [
                    (panel.left_top(), panel.right_top()),
                    (panel.right_top(), panel.right_bottom()),
                    (panel.right_bottom(), panel.left_bottom()),
                    (panel.left_bottom(), panel.left_top()),
                ] {
                    p.line_segment([a, b], Stroke::new(1.0, Color32::from_rgb(117, 28, 37)));
                }
                if (time * 0.73).fract() < 0.012 {
                    let y = block_top + 32.0;
                    p.line_segment(
                        [
                            Pos2::new(panel.left() + 12.0, y),
                            Pos2::new(panel.right() - 8.0, y),
                        ],
                        Stroke::new(1.0, red.gamma_multiply(0.6)),
                    );
                }

                let edit_id = Id::new(0x9314_52BD_u32);
                let focused = ctx.memory(|m| m.has_focus(edit_id));
                let hovered = ui.rect_contains_pointer(input);
                let active =
                    ctx.animate_bool_with_time(Id::new(0x624E_7C19_u32), focused || hovered, 0.17);
                let input_edge = Color32::from_rgb(
                    (135.0 - 75.0 * active) as u8,
                    (43.0 + 165.0 * active) as u8,
                    (49.0 + 174.0 * active) as u8,
                );
                p.rect_filled(input, 0.0, Color32::from_rgb(11, 7, 12));
                p.line_segment(
                    [input.left_top(), input.right_top()],
                    Stroke::new(1.0, input_edge),
                );
                p.line_segment(
                    [input.left_bottom(), input.right_bottom()],
                    Stroke::new(1.0, input_edge),
                );
                p.line_segment(
                    [input.left_top(), input.left_bottom()],
                    Stroke::new(1.0, input_edge),
                );
                p.line_segment(
                    [input.right_top(), input.right_bottom()],
                    Stroke::new(1.0, input_edge),
                );
                let edit = egui::TextEdit::singleline(&mut self.flag)
                    .id(edit_id)
                    .font(FontId::proportional(15.5))
                    .text_color(Color32::from_rgb(236, 219, 212))
                    .hint_text("FLAG")
                    .frame(false)
                    .desired_width(input.width() - 24.0);
                if ui.put(input.shrink2(Vec2::new(12.0, 10.0)), edit).changed() {
                    self.verdict = None;
                }

                let response = ui
                    .interact(button, Id::new(0xD0B2_73A4_u32), Sense::click())
                    .on_hover_cursor(egui::CursorIcon::PointingHand);
                let hover =
                    ctx.animate_bool_with_time(Id::new(0x6F1A_9B38_u32), response.hovered(), 0.18);
                let down = ctx.animate_bool_with_time(
                    Id::new(0xCD49_E583_u32),
                    response.is_pointer_button_down_on(),
                    0.08,
                );
                let selected = Color32::from_rgb(
                    (143.0 - 87.0 * hover) as u8,
                    (90.0 + 128.0 * hover) as u8,
                    (95.0 + 138.0 * hover) as u8,
                );
                p.rect_filled(
                    button,
                    0.0,
                    Color32::from_rgb(
                        (18.0 - 5.0 * hover) as u8,
                        (8.0 + 15.0 * hover) as u8,
                        (13.0 + 18.0 * hover) as u8,
                    ),
                );
                let cut = 9.0;
                for (a, b) in [
                    (button.left_top(), button.right_top()),
                    (
                        button.right_top(),
                        Pos2::new(button.right(), button.bottom() - cut),
                    ),
                    (
                        Pos2::new(button.right(), button.bottom() - cut),
                        Pos2::new(button.right() - cut, button.bottom()),
                    ),
                    (
                        Pos2::new(button.right() - cut, button.bottom()),
                        button.left_bottom(),
                    ),
                    (button.left_bottom(), button.left_top()),
                ] {
                    p.line_segment([a, b], Stroke::new(1.0 + 0.35 * hover, selected));
                }
                if response.clicked() {
                    self.ripple = Some(Ripple {
                        origin: response.interact_pointer_pos().unwrap_or(button.center()),
                        started: Instant::now(),
                    });
                    self.check();
                }
                if let Some(ripple) = &self.ripple {
                    let progress = ripple.started.elapsed().as_secs_f32() / 0.36;
                    if progress < 1.0 {
                        p.with_clip_rect(button).circle_stroke(
                            ripple.origin,
                            button.width() * progress * 0.42,
                            Stroke::new(1.0, cyan.gamma_multiply(0.45 * (1.0 - progress))),
                        );
                    }
                }
                let label_color = Color32::from_rgb(
                    (235.0 - 170.0 * hover) as u8,
                    (70.0 + 145.0 * hover) as u8,
                    (68.0 + 165.0 * hover) as u8,
                );
                p.text(
                    Pos2::new(button.left() + 16.0, button.center().y + down),
                    Align2::LEFT_CENTER,
                    "CHECK",
                    FontId::proportional(16.0),
                    label_color,
                );
                p.line_segment(
                    [
                        Pos2::new(button.right() - 32.0, button.center().y),
                        Pos2::new(button.right() - 17.0, button.center().y),
                    ],
                    Stroke::new(1.0, selected),
                );

                if let Some(verdict) = self.verdict {
                    let appear = (self.verdict_at.elapsed().as_secs_f32() / 0.22).min(1.0);
                    let (label, color) = if verdict == Verdict::Ok {
                        ("OK", cyan)
                    } else {
                        ("FAIL", red)
                    };
                    p.text(
                        Pos2::new(button.left() + 1.0, button.bottom() + 27.0),
                        Align2::LEFT_CENTER,
                        label,
                        FontId::proportional(15.0),
                        color.gamma_multiply(appear),
                    );
                }
            });
    }
}

impl eframe::App for FlagApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let seconds = self
            .music
            .as_ref()
            .map_or_else(|| self.started.elapsed().as_secs_f32(), Music::seconds);
        let bands = spectrum_at(seconds);
        let pulse = bands[4];
        egui::CentralPanel::default().show(ctx, |ui| {
            let rect = ui.max_rect();
            ui.painter()
                .add(eframe::egui_wgpu::Callback::new_paint_callback(
                    rect,
                    renderer::BackgroundCallback::new(
                        rect,
                        seconds + self.visual_phase,
                        [bands[0], bands[1], bands[2], bands[3]],
                        pulse,
                    ),
                ));
            self.menu(ctx, rect, seconds);
        });
        if ctx.input(|i| i.key_pressed(egui::Key::Enter)) {
            self.check();
        }
        ctx.request_repaint_after(Duration::from_millis(16));
    }
}
