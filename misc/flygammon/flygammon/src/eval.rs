//! Evaluation: play the network against fixed opponents, games run in parallel.
//!
//! Games are independent, so each one runs on its own rayon worker with its own
//! seeded RNG. Results are deterministic for a given `seed` regardless of the
//! number of threads (per-game seeds are derived from `seed` and the game index).

use burn::tensor::backend::Backend;
use rand::rngs::StdRng;
use rand::SeedableRng;
use rayon::prelude::*;

use crate::agent::{choose_1ply, choose_2ply, choose_random};
use crate::bench::{choose_style, style_name, Style, STYLES};
use crate::engine::{roll, score_points, Board};
use crate::model::FlyNet;

/// Per-game RNG seed derived from a base seed and the game index.
fn game_seed(base: u64, i: usize) -> u64 {
    base ^ (i as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15)
}

/// Net move selection at the requested search depth (1 or 2 ply).
fn net_choice<B: Backend>(
    net: &FlyNet<B>,
    board: &Board,
    dice: [u8; 2],
    device: &B::Device,
    ply: u8,
) -> Option<Board> {
    if ply >= 2 {
        choose_2ply(net, board, dice, device)
    } else {
        choose_1ply(net, board, dice, device)
    }
}

/// Play one game against an arbitrary opponent policy `opp`. Returns the net's
/// signed score (positive if the net wins).
fn play_game<B, F>(
    net: &FlyNet<B>,
    net_first: bool,
    ply: u8,
    opp: &mut F,
    rng: &mut StdRng,
    device: &B::Device,
) -> i32
where
    B: Backend,
    F: FnMut(&Board, [u8; 2], &mut StdRng) -> Option<Board>,
{
    let mut board = Board::new_game();
    let mut to_move = 0usize;
    for _ in 0..10_000 {
        let net_turn = (to_move == 0) == net_first;
        let dice = roll(rng);
        let choice = if net_turn {
            net_choice(net, &board, dice, device, ply)
        } else {
            opp(&board, dice, rng)
        };
        match choice {
            Some(end) => {
                if end.current_won() {
                    let pts = score_points(&end) as i32;
                    return if net_turn { pts } else { -pts };
                }
                board = end.flip();
            }
            None => board = board.flip(),
        }
        to_move ^= 1;
    }
    0
}

/// Run `games` independent games in parallel against `opp_for(game_index)` and
/// return the net's win fraction. `opp_for` builds a fresh opponent closure per
/// game (so per-game state, if any, isn't shared across threads).
fn eval_parallel<B, MK, F>(net: &FlyNet<B>, games: usize, ply: u8, base_seed: u64, opp_for: MK) -> f32
where
    B: Backend,
    FlyNet<B>: Sync,
    MK: Fn() -> F + Sync,
    F: FnMut(&Board, [u8; 2], &mut StdRng) -> Option<Board>,
{
    let wins: usize = (0..games)
        .into_par_iter()
        .map(|i| {
            let device = B::Device::default();
            let mut rng = StdRng::seed_from_u64(game_seed(base_seed, i));
            let mut opp = opp_for();
            if play_game(net, i % 2 == 0, ply, &mut opp, &mut rng, &device) > 0 {
                1
            } else {
                0
            }
        })
        .sum();
    wins as f32 / games.max(1) as f32
}

/// Win fraction against a random-move baseline.
pub fn eval_vs_random<B>(net: &FlyNet<B>, games: usize, ply: u8, seed: u64) -> f32
where
    B: Backend,
    FlyNet<B>: Sync,
{
    eval_parallel(net, games, ply, seed, || {
        |b: &Board, d: [u8; 2], r: &mut StdRng| choose_random(b, d, r)
    })
}

/// Win fraction against a specific fixed style.
pub fn eval_vs_style<B>(net: &FlyNet<B>, style: Style, games: usize, ply: u8, seed: u64) -> f32
where
    B: Backend,
    FlyNet<B>: Sync,
{
    eval_parallel(net, games, ply, seed, move || {
        move |b: &Board, d: [u8; 2], _r: &mut StdRng| choose_style(style, b, d)
    })
}

/// Win fraction against another loaded model (1-ply opponent).
pub fn eval_vs_model<B>(net: &FlyNet<B>, opp_net: &FlyNet<B>, games: usize, ply: u8, seed: u64) -> f32
where
    B: Backend,
    FlyNet<B>: Sync,
{
    eval_parallel(net, games, ply, seed, || {
        let odev = B::Device::default();
        move |b: &Board, d: [u8; 2], _r: &mut StdRng| choose_1ply(opp_net, b, d, &odev)
    })
}

/// Win fraction of model `a` against model `b`, with BOTH sides playing at the
/// same search depth `ply` (a fair head-to-head, unlike `eval_vs_model`).
pub fn model_vs_model<B>(a: &FlyNet<B>, b: &FlyNet<B>, games: usize, ply: u8, seed: u64) -> f32
where
    B: Backend,
    FlyNet<B>: Sync,
{
    let wins: usize = (0..games)
        .into_par_iter()
        .map(|i| {
            let device = B::Device::default();
            let bdev = B::Device::default();
            let mut rng = StdRng::seed_from_u64(game_seed(seed, i));
            let mut opp = |bd: &Board, dc: [u8; 2], _r: &mut StdRng| {
                if ply >= 2 {
                    choose_2ply(b, bd, dc, &bdev)
                } else {
                    choose_1ply(b, bd, dc, &bdev)
                }
            };
            if play_game(a, i % 2 == 0, ply, &mut opp, &mut rng, &device) > 0 {
                1
            } else {
                0
            }
        })
        .sum();
    wins as f32 / games.max(1) as f32
}

/// Full evaluation profile: win rate vs every style plus random, and the mean
/// over styles (the robust overall-strength metric used to pick checkpoints).
pub struct Profile {
    pub per_style: Vec<(&'static str, f32)>,
    pub random: f32,
    pub mean_style: f32,
}

pub fn eval_profile<B>(net: &FlyNet<B>, games: usize, ply: u8, seed: u64) -> Profile
where
    B: Backend,
    FlyNet<B>: Sync,
{
    // Each style's games run in parallel internally.
    let per_style: Vec<(&'static str, f32)> = STYLES
        .iter()
        .enumerate()
        .map(|(k, &s)| {
            let wr = eval_vs_style(net, s, games, ply, seed ^ (k as u64 + 1));
            (style_name(s), wr)
        })
        .collect();
    let sum: f32 = per_style.iter().map(|(_, wr)| wr).sum();
    let random = eval_vs_random(net, games, ply, seed ^ 0xABCD);
    Profile {
        mean_style: sum / STYLES.len() as f32,
        per_style,
        random,
    }
}
