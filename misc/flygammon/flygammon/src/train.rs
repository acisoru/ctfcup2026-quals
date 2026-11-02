//! Self-play data generation and the training loop.
//!
//! Training target: Monte-Carlo game outcome (variant 1 from docs/implementation.md).
//! Each visited state is labelled with the eventual result seen from the side that
//! was to move there. Simple, robust, and a good starting point; TD(0) bootstrap
//! can be layered on later.

use burn::backend::Autodiff;
use burn::module::{AutodiffModule, Module};
use burn::nn::loss::{MseLoss, Reduction};
use burn::optim::decay::WeightDecayConfig;
use burn::optim::{AdamConfig, GradientsParams, Optimizer};
use burn::prelude::ElementConversion;
use burn::record::CompactRecorder;
use burn::tensor::{backend::Backend, Tensor, TensorData};
use rand::rngs::StdRng;
use rand::Rng;
use rand::SeedableRng;
use rayon::prelude::*;
use std::collections::VecDeque;
use std::io::Write;
use std::time::Instant;

fn flush() {
    let _ = std::io::stdout().flush();
}

use crate::agent::{choose_1ply_explore, values5};
use crate::bench::{choose_style, Style, STYLES};
use crate::engine::{roll, score_points, Board};
use crate::eval::{eval_profile, eval_vs_model};
use crate::features::{encode, N_INPUT};
use crate::model::{FlyNet, FlyNetConfig, N_OUTPUT};

// Backend selection. Default is CPU (ndarray); `--features metal` switches the
// inference and training backends to Apple GPU via burn's wgpu->Metal path.
#[cfg(feature = "metal")]
mod backend_sel {
    pub type Inner = burn::backend::wgpu::Metal;
    pub type Dev = burn::backend::wgpu::WgpuDevice;
}
#[cfg(not(feature = "metal"))]
mod backend_sel {
    pub type Inner = burn::backend::NdArray;
    pub type Dev = burn::backend::ndarray::NdArrayDevice;
}

/// Inference backend (no autodiff) and the matching training backend.
pub type InferBackend = backend_sel::Inner;
pub type TrainBackend = Autodiff<InferBackend>;
/// Device type for the selected backend.
pub type Device = backend_sel::Dev;

pub struct TrainConfig {
    pub iterations: usize,
    pub games_per_iter: usize,
    pub batch_size: usize,
    pub lr: f64,
    pub weight_decay: f32,
    pub buffer_capacity: usize,
    pub hidden: usize,
    pub eval_games: usize,
    pub eval_every: usize,
    pub seed: u64,
    pub out_dir: String,
    /// TD(lambda) trace decay: 1.0 = Monte-Carlo, 0.0 = TD(0), ~0.7 = TD-Gammon.
    pub lambda: f32,
    /// Exploration rate for epsilon-greedy self-play (decays each iteration).
    pub epsilon: f32,
    pub epsilon_min: f32,
    pub epsilon_decay: f32,
    /// Gradient-step multiplier: steps per iter = (new_samples/batch) * this.
    pub train_mult: usize,
    /// League: fraction of games where the opponent is a random fixed style.
    pub opp_heuristic_frac: f32,
    /// League: fraction of games where the opponent is a frozen past snapshot.
    pub opp_snapshot_frac: f32,
    /// League: fraction of games against a loaded model checkpoint opponent.
    pub opp_model_frac: f32,
    /// Checkpoint stems to load as fixed model opponents (must match `hidden`).
    pub model_opponents: Vec<String>,
    /// Weight of the model-opponent win rate in the best-checkpoint score
    /// (0 = ignore models, 1 = pick best purely by beating the models).
    pub model_eval_weight: f32,
    /// Snapshot the current net into the league pool every N iterations.
    pub snapshot_every: usize,
    /// Maximum number of snapshots kept in the league pool.
    pub snapshot_pool: usize,
    /// Optional checkpoint stem to resume/fine-tune from (must match `hidden`).
    pub resume: Option<String>,
}

impl Default for TrainConfig {
    fn default() -> Self {
        TrainConfig {
            iterations: 100,
            games_per_iter: 20,
            batch_size: 256,
            lr: 1e-3,
            weight_decay: 1e-4,
            buffer_capacity: 50_000,
            hidden: 256,
            eval_games: 120,
            eval_every: 10,
            seed: 42,
            out_dir: "artifacts".to_string(),
            lambda: 0.7,
            epsilon: 0.1,
            epsilon_min: 0.01,
            epsilon_decay: 0.999,
            train_mult: 2,
            opp_heuristic_frac: 0.15,
            opp_snapshot_frac: 0.15,
            opp_model_frac: 0.1,
            model_opponents: Vec::new(),
            model_eval_weight: 0.5,
            snapshot_every: 25,
            snapshot_pool: 4,
            resume: None,
        }
    }
}

/// A training sample: encoded state plus its 5-way outcome label.
type Sample = (Vec<f32>, [f32; N_OUTPUT]);

fn label(won: bool, pts: u32) -> [f32; N_OUTPUT] {
    if won {
        [
            1.0,
            if pts >= 2 { 1.0 } else { 0.0 },
            if pts >= 3 { 1.0 } else { 0.0 },
            0.0,
            0.0,
        ]
    } else {
        [
            0.0,
            0.0,
            0.0,
            if pts >= 2 { 1.0 } else { 0.0 },
            if pts >= 3 { 1.0 } else { 0.0 },
        ]
    }
}

/// Map an opponent-to-move probability vector to the mover's perspective.
/// v = [P(win), P(win_g), P(win_bg), P(lose_g), P(lose_bg)] for the opponent.
fn map_opp_to_mover(v: &[f32; N_OUTPUT]) -> [f32; N_OUTPUT] {
    [1.0 - v[0], v[3], v[4], v[1], v[2]]
}

/// Play one game between two arbitrary actors (indexed by the player to move).
/// Returns the visited decision states and, if finished, `(winner, points)`.
fn play_trajectory(
    a0: &mut dyn FnMut(&Board, [u8; 2], &mut StdRng) -> Option<Board>,
    a1: &mut dyn FnMut(&Board, [u8; 2], &mut StdRng) -> Option<Board>,
    rng: &mut StdRng,
) -> (Vec<(Board, usize)>, Option<(usize, u32)>) {
    let mut board = Board::new_game();
    let mut to_move = 0usize;
    let mut states: Vec<(Board, usize)> = Vec::new();
    let mut terminal = None;

    for _ in 0..10_000 {
        states.push((board.clone(), to_move));
        let dice = roll(rng);
        let choice = if to_move == 0 {
            a0(&board, dice, rng)
        } else {
            a1(&board, dice, rng)
        };
        match choice {
            Some(end) => {
                if end.current_won() {
                    terminal = Some((to_move, score_points(&end)));
                    break;
                }
                board = end.flip();
            }
            None => board = board.flip(),
        }
        to_move ^= 1;
    }
    (states, terminal)
}

/// TD(lambda) targets for one finished trajectory, via the backward recursion
///     G_t = map( (1-lambda) * V(s_{t+1}) + lambda * G_{t+1} )
/// with the winning move grounded on the Monte-Carlo terminal outcome.
/// `map` converts the next state's value/return from the opponent's perspective
/// back to the mover's perspective. lambda=1 => Monte-Carlo, lambda=0 => TD(0).
fn samples_td_lambda<B: Backend>(
    net: &FlyNet<B>,
    states: &[(Board, usize)],
    winner: usize,
    pts: u32,
    lambda: f32,
    device: &B::Device,
) -> Vec<Sample> {
    let n = states.len();
    if n == 0 {
        return Vec::new();
    }
    let enc: Vec<Vec<f32>> = states.iter().map(|(b, _)| encode(b)).collect();
    let vals = values5(net, &enc, device); // vals[t] = V(s_t) in mover_t's frame

    let mut g = vec![[0.0f32; N_OUTPUT]; n];
    g[n - 1] = label(states[n - 1].1 == winner, pts);
    for t in (0..n - 1).rev() {
        let mut blended = [0.0f32; N_OUTPUT];
        for k in 0..N_OUTPUT {
            blended[k] = (1.0 - lambda) * vals[t + 1][k] + lambda * g[t + 1][k];
        }
        g[t] = map_opp_to_mover(&blended);
    }

    enc.into_iter().zip(g).collect()
}

/// Opponent assignment for one self-play game in the league.
enum OppKind {
    SelfPlay,
    Style(Style),
    Snapshot(usize),
    Model(usize),
}

/// A single self-play game to run: its RNG seed and its opponent.
struct GameTask {
    seed: u64,
    opp: OppKind,
}

/// Run one self-play game (thread-safe: reads shared nets, owns its RNG).
fn play_one_task(
    infer: &FlyNet<InferBackend>,
    pool: &[FlyNet<InferBackend>],
    models: &[FlyNet<InferBackend>],
    task: &GameTask,
    epsilon: f32,
    lambda: f32,
    device: &Device,
) -> Vec<Sample> {
    let mut rng = StdRng::seed_from_u64(task.seed);
    let mut learner = |b: &Board, d: [u8; 2], rr: &mut StdRng| {
        choose_1ply_explore(infer, b, d, device, epsilon, rr)
    };
    let mut opp: Box<dyn FnMut(&Board, [u8; 2], &mut StdRng) -> Option<Board>> = match task.opp {
        OppKind::Style(s) => Box::new(move |b: &Board, d: [u8; 2], _rr: &mut StdRng| choose_style(s, b, d)),
        OppKind::Snapshot(k) => {
            let snap = &pool[k];
            Box::new(move |b: &Board, d: [u8; 2], rr: &mut StdRng| {
                choose_1ply_explore(snap, b, d, device, epsilon, rr)
            })
        }
        OppKind::Model(k) => {
            let m = &models[k];
            Box::new(move |b: &Board, d: [u8; 2], rr: &mut StdRng| {
                choose_1ply_explore(m, b, d, device, epsilon, rr)
            })
        }
        OppKind::SelfPlay => Box::new(move |b: &Board, d: [u8; 2], rr: &mut StdRng| {
            choose_1ply_explore(infer, b, d, device, epsilon, rr)
        }),
    };
    let (states, terminal) = play_trajectory(&mut learner, &mut opp, &mut rng);
    match terminal {
        Some((winner, pts)) => samples_td_lambda(infer, &states, winner, pts, lambda, device),
        None => Vec::new(),
    }
}

fn to_tensors(
    batch: &[Sample],
    device: &Device,
) -> (Tensor<TrainBackend, 2>, Tensor<TrainBackend, 2>) {
    let n = batch.len();
    let mut xs = Vec::with_capacity(n * N_INPUT);
    let mut ys = Vec::with_capacity(n * N_OUTPUT);
    for (x, y) in batch {
        xs.extend_from_slice(x);
        ys.extend_from_slice(y);
    }
    let x = Tensor::<TrainBackend, 2>::from_data(TensorData::new(xs, [n, N_INPUT]), device);
    let y = Tensor::<TrainBackend, 2>::from_data(TensorData::new(ys, [n, N_OUTPUT]), device);
    (x, y)
}

/// Serialize the raw f32 weights of each linear layer to a flat little-endian
/// file — the "custom format" artifact the CTF player reverse-engineers.
fn export_raw_weights<B: Backend>(net: &FlyNet<B>, path: &str) -> std::io::Result<()> {
    let mut buf: Vec<u8> = Vec::new();
    for lin in net.layers() {
        let w = lin.weight.val().into_data().to_vec::<f32>().expect("f32");
        for f in w {
            buf.extend_from_slice(&f.to_le_bytes());
        }
        if let Some(bias) = &lin.bias {
            let b = bias.val().into_data().to_vec::<f32>().expect("f32");
            for f in b {
                buf.extend_from_slice(&f.to_le_bytes());
            }
        }
    }
    std::fs::write(path, buf)
}

/// Save both a burn checkpoint (`.mpk`) and the raw-weights artifact (`.fly`).
fn save_all(model: &FlyNet<TrainBackend>, dir: &str, stem: &str) {
    let ckpt = format!("{dir}/{stem}");
    model
        .clone()
        .save_file(ckpt.clone(), &CompactRecorder::new())
        .expect("save checkpoint");
    export_raw_weights(model, &format!("{dir}/{stem}.fly")).expect("export weights");
}

pub fn run(cfg: TrainConfig) {
    let device = Device::default();
    let mut rng = StdRng::seed_from_u64(cfg.seed);

    let mut model: FlyNet<TrainBackend> =
        FlyNetConfig::new().with_hidden(cfg.hidden).init(&device);
    if let Some(resume) = &cfg.resume {
        model = model
            .load_file(resume.clone(), &CompactRecorder::new(), &device)
            .unwrap_or_else(|e| panic!("resume from {resume}: {e}"));
        println!("resumed from {resume}");
    }
    // Adam with L2 weight decay for regularisation against overfitting.
    let mut optim = AdamConfig::new()
        .with_weight_decay(Some(WeightDecayConfig::new(cfg.weight_decay)))
        .init();

    std::fs::create_dir_all(&cfg.out_dir).ok();
    let mut epsilon = cfg.epsilon;

    // Replay buffer: keep recent games (not only the freshest) so the net does
    // not overfit to the current self-play distribution or forget old positions.
    let mut buffer: VecDeque<Sample> = VecDeque::with_capacity(cfg.buffer_capacity);
    // Best checkpoint is chosen by the stationary benchmark, not the last iter.
    let mut best_mean = f32::NEG_INFINITY;
    // League pool of frozen past snapshots to play against.
    let mut pool: Vec<FlyNet<InferBackend>> = Vec::new();
    // Fixed model-checkpoint opponents (e.g. a prior net / imported TD model).
    let models: Vec<FlyNet<InferBackend>> = cfg
        .model_opponents
        .iter()
        .map(|s| {
            println!("loading model opponent {s}");
            load(s, cfg.hidden)
        })
        .collect();

    println!(
        "training: {} iters x {} games | hidden {} | batch {} | lr {} | wd {} | buffer {} | lambda {} | league styles{:.2}/snap{:.2} | backend {}",
        cfg.iterations,
        cfg.games_per_iter,
        cfg.hidden,
        cfg.batch_size,
        cfg.lr,
        cfg.weight_decay,
        cfg.buffer_capacity,
        cfg.lambda,
        cfg.opp_heuristic_frac,
        cfg.opp_snapshot_frac,
        if cfg!(feature = "metal") { "metal" } else { "cpu" }
    );
    flush();

    for iter in 0..cfg.iterations {
        // Inference copy (no autodiff graph) for fast rollouts.
        let infer = model.valid();
        let infer_device = Device::default();

        // Refresh the league pool with a frozen snapshot of the current net.
        if cfg.snapshot_pool > 0 && iter % cfg.snapshot_every == 0 {
            pool.push(model.valid());
            if pool.len() > cfg.snapshot_pool {
                pool.remove(0);
            }
        }

        // --- self-play / league: prepare independent game tasks, run in parallel ---
        let t0 = Instant::now();
        print!("iter {iter:>4} | self-play (parallel) ");
        flush();

        // Sequential prep with the main RNG keeps assignment reproducible.
        let tasks: Vec<GameTask> = (0..cfg.games_per_iter)
            .map(|_| {
                let r: f32 = rng.gen();
                let t_style = cfg.opp_heuristic_frac;
                let t_snap = t_style + if pool.is_empty() { 0.0 } else { cfg.opp_snapshot_frac };
                let t_model = t_snap + if models.is_empty() { 0.0 } else { cfg.opp_model_frac };
                let opp = if r < t_style {
                    // Random style: the net faces every method of play.
                    OppKind::Style(STYLES[rng.gen_range(0..STYLES.len())])
                } else if r < t_snap {
                    OppKind::Snapshot(rng.gen_range(0..pool.len()))
                } else if r < t_model {
                    OppKind::Model(rng.gen_range(0..models.len()))
                } else {
                    OppKind::SelfPlay
                };
                GameTask {
                    seed: rng.gen(),
                    opp,
                }
            })
            .collect();

        // Parallel rollouts: games are independent and only read the frozen nets.
        let results: Vec<Vec<Sample>> = tasks
            .par_iter()
            .map(|t| play_one_task(&infer, &pool, &models, t, epsilon, cfg.lambda, &infer_device))
            .collect();

        let mut new_samples = 0usize;
        for r in results {
            for s in r {
                buffer.push_back(s);
                new_samples += 1;
            }
        }
        // Evict oldest samples beyond capacity.
        while buffer.len() > cfg.buffer_capacity {
            buffer.pop_front();
        }
        let t_play = t0.elapsed().as_secs_f32();

        // --- training: fixed number of minibatches sampled from the buffer ---
        let t1 = Instant::now();
        let data = buffer.make_contiguous();
        let data_len = data.len();
        let steps = ((new_samples / cfg.batch_size).max(1)) * cfg.train_mult.max(1);
        let bs = cfg.batch_size.min(data_len);
        let mut total_loss = 0.0f32;
        for _ in 0..steps {
            let mut batch: Vec<Sample> = Vec::with_capacity(bs);
            for _ in 0..bs {
                let idx = rng.gen_range(0..data_len);
                batch.push(data[idx].clone());
            }
            let (x, y) = to_tensors(&batch, &device);
            let out = model.forward(x);
            let loss = MseLoss::new().forward(out, y, Reduction::Mean);
            total_loss += loss.clone().into_scalar().elem::<f32>();

            let grads = loss.backward();
            let grads = GradientsParams::from_grads(grads, &model);
            model = optim.step(cfg.lr, model, grads);
        }
        let avg_loss = total_loss / steps as f32;
        let t_train = t1.elapsed().as_secs_f32();

        print!(
            " +{new_samples} (buf {}) | eps {epsilon:.3} | play {t_play:.1}s train {t_train:.1}s | loss {avg_loss:.4}",
            buffer.len()
        );

        // Decay exploration for the next iteration.
        epsilon = (epsilon * cfg.epsilon_decay).max(cfg.epsilon_min);

        if iter % cfg.eval_every == 0 || iter + 1 == cfg.iterations {
            let infer = model.valid();
            let eseed: u64 = rng.gen();
            let prof = eval_profile(&infer, cfg.eval_games, 1, eseed);
            print!(" | mean {:.1}%", prof.mean_style * 100.0);
            for (name, wr) in &prof.per_style {
                print!(" {} {:.0}%", name, wr * 100.0);
            }
            print!(" rand {:.0}%", prof.random * 100.0);
            let mut model_sum = 0.0f32;
            for (k, m) in models.iter().enumerate() {
                let wr = eval_vs_model(&infer, m, cfg.eval_games, 1, eseed ^ (0x1000 + k as u64));
                model_sum += wr;
                print!(" model{} {:.0}%", k, wr * 100.0);
            }
            // Best-checkpoint score: blend styles with the model-opponent results.
            let score = if models.is_empty() {
                prof.mean_style
            } else {
                let mean_model = model_sum / models.len() as f32;
                let w = cfg.model_eval_weight.clamp(0.0, 1.0);
                (1.0 - w) * prof.mean_style + w * mean_model
            };
            print!(" | score {:.1}%", score * 100.0);
            if score > best_mean {
                best_mean = score;
                save_all(&model, &cfg.out_dir, "flygammon_best");
                print!(" (new best, saved)");
            }
        }
        println!();
        flush();
    }

    // Always save the final model too (separate from the best checkpoint).
    save_all(&model, &cfg.out_dir, "flygammon_last");
    println!(
        "done. best checkpoint (score {:.1}%): {}/flygammon_best.mpk (+.fly) | last: {}/flygammon_last.mpk",
        best_mean * 100.0,
        cfg.out_dir,
        cfg.out_dir
    );
}

/// Serve the model as a move engine over the stdin/stdout line protocol
/// (same format as `external.rs` / `gnubg_adapter.py`): a FIBS client or any
/// driver sends `p0..p23 bar_cur bar_opp off_cur off_opp d1 d2` and reads back
/// the chosen resulting board as 28 ints, or `PASS`.
pub fn serve(path: &str, hidden: usize, ply: u8) {
    use crate::agent::{choose_1ply, choose_2ply};
    use crate::external::{board_from_ints, board_to_ints};
    use std::io::{BufRead, Write};

    let net = load(path, hidden);
    let device = Device::default();
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let nums: Vec<i32> = line.split_whitespace().filter_map(|s| s.parse().ok()).collect();
        if nums.len() < 30 {
            continue;
        }
        let board = match board_from_ints(&nums[..28]) {
            Some(b) => b,
            None => continue,
        };
        let dice = [nums[28] as u8, nums[29] as u8];
        let mv = if ply >= 2 {
            choose_2ply(&net, &board, dice, &device)
        } else {
            choose_1ply(&net, &board, dice, &device)
        };
        match mv {
            Some(e) => {
                let s: Vec<String> = board_to_ints(&e).iter().map(|x| x.to_string()).collect();
                let _ = writeln!(out, "{}", s.join(" "));
            }
            None => {
                let _ = writeln!(out, "PASS");
            }
        }
        let _ = out.flush();
    }
}

/// Short display label for a checkpoint stem (its parent dir, else the stem).
fn short_label(stem: &str) -> String {
    let parts: Vec<&str> = stem.trim_end_matches('/').split('/').collect();
    if parts.len() >= 2 {
        parts[parts.len() - 2].to_string()
    } else {
        stem.to_string()
    }
}

/// Round-robin tournament between loaded models (both sides at `ply`). Prints a
/// head-to-head grid and standings by average win rate, naming the strongest.
pub fn tournament(models: Vec<(String, usize)>, games: usize, ply: u8) {
    use crate::eval::model_vs_model;
    let n = models.len();
    println!("loading {n} models at {ply}-ply, {games} games per pair…");
    let nets: Vec<FlyNet<InferBackend>> = models.iter().map(|(s, h)| load(s, *h)).collect();
    let labels: Vec<String> = models.iter().map(|(s, _)| short_label(s)).collect();

    let mut mat = vec![vec![-1.0f32; n]; n];
    for i in 0..n {
        for j in (i + 1)..n {
            let seed = 0xA11CE ^ ((i as u64) << 8) ^ (j as u64);
            let wr = model_vs_model(&nets[i], &nets[j], games, ply, seed);
            mat[i][j] = wr;
            mat[j][i] = 1.0 - wr;
            println!(
                "  {:<22} vs {:<22}  {:.1}% - {:.1}%",
                labels[i],
                labels[j],
                wr * 100.0,
                (1.0 - wr) * 100.0
            );
        }
    }

    let mut avg: Vec<(usize, f32)> = (0..n)
        .map(|i| {
            let (mut s, mut c) = (0.0f32, 0usize);
            for j in 0..n {
                if i != j && mat[i][j] >= 0.0 {
                    s += mat[i][j];
                    c += 1;
                }
            }
            (i, if c > 0 { s / c as f32 } else { 0.0 })
        })
        .collect();
    avg.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    // Head-to-head grid (row = win rate vs column).
    println!("\nhead-to-head win% (row vs column):");
    print!("{:<22}", "");
    for j in 0..n {
        print!("{:>8}", &labels[j][..labels[j].len().min(7)]);
    }
    println!();
    for i in 0..n {
        print!("{:<22}", &labels[i][..labels[i].len().min(21)]);
        for j in 0..n {
            if i == j {
                print!("{:>8}", "—");
            } else {
                print!("{:>7.0}%", mat[i][j] * 100.0);
            }
        }
        println!();
    }

    println!("\n=== standings (avg win rate vs field) ===");
    for (rank, (i, a)) in avg.iter().enumerate() {
        println!("{:>2}. {:<30} {:.1}%", rank + 1, labels[*i], a * 100.0);
    }
    println!("\nstrongest: {}", labels[avg[0].0]);
}

/// Load a trained checkpoint for evaluation or inference.
pub fn load(path: &str, hidden: usize) -> FlyNet<InferBackend> {
    let device = Device::default();
    let model: FlyNet<InferBackend> = FlyNetConfig::new().with_hidden(hidden).init(&device);
    model
        .load_file(path, &CompactRecorder::new(), &device)
        .expect("load checkpoint")
}
