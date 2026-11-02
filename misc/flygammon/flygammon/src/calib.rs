//! Calibration for the flygammon-task CTF design.
//!
//! Measures two numbers that gate the task design:
//!   1. Honest baseline: player (1-ply, moves first) vs fly (1-ply), RANDOM dice.
//!      Must be ~50% so that a non-exploiter's chance of 20-in-a-row (~p^20) is
//!      negligible.
//!   2. Foreknowledge win rate: player plays a deterministic receding-horizon
//!      search KNOWING the whole dice schedule, vs the deterministic 1-ply fly.
//!      This is the fraction of seeds a solver can win => grind length ~ 1/rate.
//!
//! The fly is part of the environment: at fly plies we apply its actual 1-ply
//! policy (not an adversarial minimax). Only the player's plies branch.

use rand::rngs::StdRng;
use rand::{Rng, SeedableRng};

use crate::agent::{choose_1ply, choose_2ply, equities};
use crate::engine::{legal_end_boards, roll, score_points, Board};
use crate::features::encode;
use crate::train::{load, InferBackend};

type Dev = burn::backend::ndarray::NdArrayDevice;

const SHORTLIST: usize = 6;
const MAX_PLIES: usize = 400;
const WIN: f32 = 1000.0;

/// Player-centric equity of a position given who is to move.
fn player_equity(net: &crate::model::FlyNet<InferBackend>, dev: &Dev, b: &Board, mover_is_player: bool) -> f32 {
    let e = equities(net, &[encode(b)], dev)[0];
    if mover_is_player { e } else { -e }
}

/// Deterministic receding-horizon search value (player-centric) of a state, with
/// `depth` remaining PLAYER decision plies to expand. Fly plies are applied via
/// the fly's fixed 1-ply policy and do not consume depth.
fn fly_move(
    net: &crate::model::FlyNet<InferBackend>,
    dev: &Dev,
    b: &Board,
    dice: [u8; 2],
    fly_ply: u8,
) -> Option<Board> {
    if fly_ply >= 2 {
        choose_2ply(net, b, dice, dev)
    } else {
        choose_1ply(net, b, dice, dev)
    }
}

fn search(
    net: &crate::model::FlyNet<InferBackend>,
    dev: &Dev,
    b: &Board,
    sched: &[[u8; 2]],
    ply: usize,
    mover_is_player: bool,
    depth: i32,
    fly_ply: u8,
) -> f32 {
    if b.current_won() {
        let pts = score_points(b) as f32;
        return if mover_is_player { WIN + pts } else { -WIN - pts };
    }
    if ply >= sched.len() {
        return player_equity(net, dev, b, mover_is_player);
    }
    let dice = sched[ply];
    let ends = legal_end_boards(b, dice);
    if ends.is_empty() {
        let nb = b.flip();
        return search(net, dev, &nb, sched, ply + 1, !mover_is_player, depth, fly_ply);
    }

    if mover_is_player {
        // Evaluate each candidate by the opponent's (fly's) equity after hand-off.
        let encoded: Vec<Vec<f32>> = ends.iter().map(|e| encode(&e.flip())).collect();
        let oppeq = equities(net, &encoded, dev);
        let mut order: Vec<usize> = (0..ends.len()).collect();
        order.sort_by(|&a, &c| oppeq[a].partial_cmp(&oppeq[c]).unwrap_or(std::cmp::Ordering::Equal));

        if depth <= 0 {
            // Greedy leaf: best immediate player value.
            let mut best = f32::NEG_INFINITY;
            for (i, e) in ends.iter().enumerate() {
                let v = if e.current_won() { WIN + score_points(e) as f32 } else { -oppeq[i] };
                if v > best { best = v; }
            }
            return best;
        }

        let k = SHORTLIST.min(ends.len());
        let mut best = f32::NEG_INFINITY;
        for &i in &order[..k] {
            let e = &ends[i];
            let v = if e.current_won() {
                WIN + score_points(e) as f32
            } else {
                let child = e.flip(); // fly to move
                search(net, dev, &child, sched, ply + 1, false, depth - 1, fly_ply)
            };
            if v > best { best = v; }
        }
        best
    } else {
        // Fly node: deterministic 1-ply policy, single child.
        match fly_move(net, dev, b, dice, fly_ply) {
            Some(e) => {
                if e.current_won() {
                    -WIN - score_points(&e) as f32
                } else {
                    let child = e.flip(); // player to move
                    search(net, dev, &child, sched, ply + 1, true, depth, fly_ply)
                }
            }
            None => {
                let nb = b.flip();
                search(net, dev, &nb, sched, ply + 1, true, depth, fly_ply)
            }
        }
    }
}

/// Play one full game with the player using foreknowledge (receding horizon at
/// `depth`) and the fly at 1-ply, over a fixed dice schedule. Returns true if the
/// player wins.
fn play_foreknowledge(net: &crate::model::FlyNet<InferBackend>, dev: &Dev, sched: &[[u8; 2]], depth: i32, fly_ply: u8) -> bool {
    let mut b = Board::new_game();
    let mut player_turn = true; // player moves first
    let mut ply = 0usize;
    while ply < sched.len() {
        let dice = sched[ply];
        let ends = legal_end_boards(&b, dice);
        if ends.is_empty() {
            b = b.flip();
            player_turn = !player_turn;
            ply += 1;
            continue;
        }
        let chosen = if player_turn {
            // Pick the end maximizing the search value.
            let encoded: Vec<Vec<f32>> = ends.iter().map(|e| encode(&e.flip())).collect();
            let oppeq = equities(net, &encoded, dev);
            let mut order: Vec<usize> = (0..ends.len()).collect();
            order.sort_by(|&a, &c| oppeq[a].partial_cmp(&oppeq[c]).unwrap_or(std::cmp::Ordering::Equal));
            let k = SHORTLIST.min(ends.len());
            let mut best_i = order[0];
            let mut best_v = f32::NEG_INFINITY;
            for &i in &order[..k] {
                let e = &ends[i];
                let v = if e.current_won() {
                    WIN + score_points(e) as f32
                } else {
                    let child = e.flip();
                    search(net, dev, &child, sched, ply + 1, false, depth - 1, fly_ply)
                };
                if v > best_v {
                    best_v = v;
                    best_i = i;
                }
            }
            ends[best_i].clone()
        } else {
            fly_move(net, dev, &b, dice, fly_ply).unwrap()
        };
        if chosen.current_won() {
            return player_turn;
        }
        b = chosen.flip();
        player_turn = !player_turn;
        ply += 1;
    }
    false
}

/// Honest baseline: both sides 1-ply, random dice, player moves first.
fn play_honest(net: &crate::model::FlyNet<InferBackend>, dev: &Dev, rng: &mut impl Rng) -> bool {
    let mut b = Board::new_game();
    let mut player_turn = true;
    for _ in 0..MAX_PLIES {
        let dice = roll(rng);
        match choose_1ply(net, &b, dice, dev) {
            Some(e) => {
                if e.current_won() {
                    return player_turn;
                }
                b = e.flip();
            }
            None => b = b.flip(),
        }
        player_turn = !player_turn;
    }
    false
}

/// Strong honest attacker: player uses 2-ply (no foreknowledge), fly 1-ply,
/// random dice, player first. Proxy for "how much can a stronger honest bot beat
/// the 1-ply fly?" — the quantity that governs whether brute persistence (no DLP)
/// could chain 20 wins.
fn play_honest_strong(net: &crate::model::FlyNet<InferBackend>, dev: &Dev, rng: &mut impl Rng) -> bool {
    let mut b = Board::new_game();
    let mut player_turn = true;
    for _ in 0..MAX_PLIES {
        let dice = roll(rng);
        let mv = if player_turn {
            choose_2ply(net, &b, dice, dev)
        } else {
            choose_1ply(net, &b, dice, dev)
        };
        match mv {
            Some(e) => {
                if e.current_won() {
                    return player_turn;
                }
                b = e.flip();
            }
            None => b = b.flip(),
        }
        player_turn = !player_turn;
    }
    false
}

fn make_schedule(seed: u64) -> Vec<[u8; 2]> {
    let mut rng = StdRng::seed_from_u64(seed);
    (0..MAX_PLIES).map(|_| roll(&mut rng)).collect()
}

/// Entry point: `calibrate <stem> <hidden> <games> [maxdepth]`
pub fn run(path: &str, hidden: usize, games: usize, max_depth: i32, fly_ply: u8) {
    let net = load(path, hidden);
    let dev = Dev::default();

    // Honest baseline.
    let mut honest_wins = 0usize;
    for s in 0..games {
        let mut rng = StdRng::seed_from_u64(0x484F4E45_0000u64.wrapping_add(s as u64));
        if play_honest(&net, &dev, &mut rng) {
            honest_wins += 1;
        }
    }
    println!(
        "honest baseline (1-ply vs 1-ply, random dice, player first): {}/{} = {:.1}%",
        honest_wins,
        games,
        100.0 * honest_wins as f32 / games as f32
    );

    // Strong honest attacker (2-ply vs 1-ply, no foreknowledge).
    let mut strong_wins = 0usize;
    for s in 0..games {
        let mut rng = StdRng::seed_from_u64(0x5720_0000u64.wrapping_add(s as u64));
        if play_honest_strong(&net, &dev, &mut rng) {
            strong_wins += 1;
        }
    }
    let sp = strong_wins as f32 / games as f32;
    println!(
        "strong honest attacker (2-ply vs 1-ply, random dice, player first): {}/{} = {:.1}%  => p^20 = {:.2e}",
        strong_wins,
        games,
        100.0 * sp,
        sp.powi(20)
    );

    // Foreknowledge win rate per depth, same schedules across depths.
    let schedules: Vec<Vec<[u8; 2]>> = (0..games).map(|s| make_schedule(0xD1CE0000 + s as u64)).collect();
    for depth in 1..=max_depth {
        let mut wins = 0usize;
        for sch in &schedules {
            if play_foreknowledge(&net, &dev, sch, depth, fly_ply) {
                wins += 1;
            }
        }
        let rate = wins as f32 / games as f32;
        println!(
            "foreknowledge depth {} vs {}-ply fly: {}/{} = {:.1}%  (grind ~{:.1} games/win)",
            depth,
            fly_ply,
            wins,
            games,
            100.0 * rate,
            if rate > 0.0 { 1.0 / rate } else { f32::INFINITY }
        );
    }
}
