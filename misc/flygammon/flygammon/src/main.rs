//! flygammon — self-play backgammon RL agent (full-fidelity inputs, strong play).
//! The CTF weakness is applied later by a separate mechanism, not here.
//!
//! Usage:
//!   train [iters] [games] [hidden] [key=value ...]
//!     keys: lambda lr wd batch buffer train_mult eval_games eval_every
//!           epsilon epsilon_min epsilon_decay heur_frac snap_frac model_frac
//!           model_eval_weight models snapshot_every snapshot_pool seed resume
//!     e.g. train 4000 300 512 lambda=0.9 buffer=20000 lr=0.0007 eval_games=200
//!   eval <checkpoint_stem> [hidden] [games] [ply]
//!   demo

mod agent;
mod bench;
mod calib;
mod engine;
mod eval;
mod external;
mod features;
mod model;
mod train;

use rand::rngs::StdRng;
use rand::SeedableRng;
use std::collections::HashMap;

use crate::engine::{roll, score_points, Board};
use crate::eval::eval_profile;
use crate::train::TrainConfig;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cmd = args.get(1).map(|s| s.as_str()).unwrap_or("train");

    match cmd {
        "train" => {
            let mut cfg = TrainConfig::default();

            // Split remaining args into positionals and key=value overrides.
            let mut pos: Vec<&String> = Vec::new();
            let mut kv: HashMap<&str, &str> = HashMap::new();
            for a in &args[2..] {
                if let Some((k, v)) = a.split_once('=') {
                    kv.insert(k, v);
                } else {
                    pos.push(a);
                }
            }
            if let Some(v) = pos.first().and_then(|s| s.parse().ok()) {
                cfg.iterations = v;
            }
            if let Some(v) = pos.get(1).and_then(|s| s.parse().ok()) {
                cfg.games_per_iter = v;
            }
            if let Some(v) = pos.get(2).and_then(|s| s.parse().ok()) {
                cfg.hidden = v;
            }

            macro_rules! set {
                ($key:literal, $field:ident) => {
                    if let Some(x) = kv.get($key).and_then(|s| s.parse().ok()) {
                        cfg.$field = x;
                    }
                };
            }
            set!("lambda", lambda);
            set!("lr", lr);
            set!("wd", weight_decay);
            set!("batch", batch_size);
            set!("buffer", buffer_capacity);
            set!("train_mult", train_mult);
            set!("eval_games", eval_games);
            set!("eval_every", eval_every);
            set!("epsilon", epsilon);
            set!("epsilon_min", epsilon_min);
            set!("epsilon_decay", epsilon_decay);
            set!("heur_frac", opp_heuristic_frac);
            set!("snap_frac", opp_snapshot_frac);
            set!("model_frac", opp_model_frac);
            set!("model_eval_weight", model_eval_weight);
            set!("snapshot_every", snapshot_every);
            set!("snapshot_pool", snapshot_pool);
            set!("seed", seed);
            if let Some(stem) = kv.get("resume") {
                cfg.resume = Some(stem.to_string());
            }
            // Comma-separated checkpoint stems to use as fixed model opponents.
            if let Some(list) = kv.get("models") {
                cfg.model_opponents = list.split(',').map(|s| s.to_string()).collect();
            }

            train::run(cfg);
        }
        "eval" => {
            // Path is the checkpoint stem WITHOUT extension (burn appends .mpk).
            let path = args.get(2).map(|s| s.as_str()).unwrap_or("artifacts/flygammon_best");
            let hidden: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(256);
            let games: usize = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(200);
            let ply: u8 = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(1);
            let net = train::load(path, hidden);
            let prof = eval_profile(&net, games, ply, 7);
            print!(
                "{}-ply over {} games | mean vs styles {:.1}% |",
                ply,
                games,
                prof.mean_style * 100.0
            );
            for (name, wr) in &prof.per_style {
                print!(" {} {:.1}%", name, wr * 100.0);
            }
            println!(" | random {:.1}%", prof.random * 100.0);
        }
        "serve" => {
            // Model as a move engine over stdin/stdout (for a FIBS client etc.).
            //   serve <stem> <hidden> [ply]
            let path = args.get(2).map(|s| s.as_str()).unwrap_or("artifacts/flygammon_best");
            let hidden: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(256);
            let ply: u8 = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(2);
            train::serve(path, hidden, ply);
        }
        "tournament" => {
            // Round-robin between models; shows which is strongest.
            //   tournament <games> <ply> <model> <model> [...]
            //   each model is a checkpoint stem, or stem:hidden (default 256).
            let games: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(100);
            let ply: u8 = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(2);
            let mut models: Vec<(String, usize)> = Vec::new();
            for a in args.get(4..).unwrap_or(&[]) {
                match a.rsplit_once(':') {
                    Some((stem, h)) if h.parse::<usize>().is_ok() => {
                        models.push((stem.to_string(), h.parse().unwrap()));
                    }
                    _ => models.push((a.clone(), 256)),
                }
            }
            if models.len() < 2 {
                eprintln!("usage: tournament <games> <ply> <model[:hidden]> <model[:hidden]> [...]");
                std::process::exit(1);
            }
            train::tournament(models, games, ply);
        }
        "vs-engine" => {
            // eval net against an external engine subprocess (e.g. a gnubg adapter).
            //   vs-engine <stem> <hidden> <games> <ply> <command...>
            let path = args.get(2).map(|s| s.as_str()).unwrap_or("artifacts/flygammon_best");
            let hidden: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(256);
            let games: usize = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(100);
            let ply: u8 = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(1);
            let cmd = args.get(6..).map(|a| a.join(" ")).unwrap_or_default();
            if cmd.is_empty() {
                eprintln!("usage: vs-engine <stem> <hidden> <games> <ply> <command...>");
                std::process::exit(1);
            }
            let net = train::load(path, hidden);
            match external::eval_net_vs_engine(&net, &cmd, games, ply, 7) {
                Ok(wr) => println!(
                    "{}-ply over {} games vs `{}` | winrate {:.1}%",
                    ply,
                    games,
                    cmd,
                    wr * 100.0
                ),
                Err(e) => eprintln!("external engine error: {e}"),
            }
        }
        "calibrate" => {
            // calibrate <stem> <hidden> <games> [maxdepth]
            let path = args.get(2).map(|s| s.as_str()).unwrap_or("artifacts/flygammon_best");
            let hidden: usize = args.get(3).and_then(|s| s.parse().ok()).unwrap_or(80);
            let games: usize = args.get(4).and_then(|s| s.parse().ok()).unwrap_or(200);
            let max_depth: i32 = args.get(5).and_then(|s| s.parse().ok()).unwrap_or(3);
            let fly_ply: u8 = args.get(6).and_then(|s| s.parse().ok()).unwrap_or(2);
            calib::run(path, hidden, games, max_depth, fly_ply);
        }
        "demo" => {
            // Play a single random-vs-random game and print the result, to smoke
            // test the engine without any training.
            let mut rng = StdRng::seed_from_u64(1);
            let mut board = Board::new_game();
            let mut plies = 0;
            for _ in 0..10_000 {
                let dice = roll(&mut rng);
                match agent::choose_random(&board, dice, &mut rng) {
                    Some(end) => {
                        plies += 1;
                        if end.current_won() {
                            println!("game over in {} plies, {} points", plies, score_points(&end));
                            return;
                        }
                        board = end.flip();
                    }
                    None => board = board.flip(),
                }
            }
            println!("game did not finish within cap");
        }
        other => {
            eprintln!("unknown command: {other}");
            eprintln!("commands: train | eval | demo");
            std::process::exit(1);
        }
    }
}
