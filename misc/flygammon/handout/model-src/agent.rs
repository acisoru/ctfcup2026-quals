//! Move selection: evaluate candidate positions with the network and pick a move.

use burn::tensor::{backend::Backend, Tensor, TensorData};
use rand::Rng;

use crate::engine::{legal_end_boards, Board};
use crate::features::{encode, encode_into, N_INPUT};
use crate::model::{equity_from_row, FlyNet, N_OUTPUT};

pub fn values5<B: Backend>(
    net: &FlyNet<B>,
    encoded: &[Vec<f32>],
    device: &B::Device,
) -> Vec<[f32; N_OUTPUT]> {
    let k = encoded.len();
    if k == 0 {
        return Vec::new();
    }
    let mut flat = Vec::with_capacity(k * N_INPUT);
    for e in encoded {
        flat.extend_from_slice(e);
    }
    let data = TensorData::new(flat, [k, N_INPUT]);
    let input = Tensor::<B, 2>::from_data(data, device);
    let out = net.forward(input);
    let raw = out.into_data().to_vec::<f32>().expect("f32 output");
    raw.chunks(N_OUTPUT)
        .map(|c| {
            let mut a = [0.0f32; N_OUTPUT];
            a.copy_from_slice(c);
            a
        })
        .collect()
}

pub fn equities<B: Backend>(
    net: &FlyNet<B>,
    encoded: &[Vec<f32>],
    device: &B::Device,
) -> Vec<f32> {
    values5(net, encoded, device)
        .iter()
        .map(|r| equity_from_row(r))
        .collect()
}

pub fn equities_flat<B: Backend>(net: &FlyNet<B>, flat: Vec<f32>, n: usize, device: &B::Device) -> Vec<f32> {
    if n == 0 {
        return Vec::new();
    }
    let data = TensorData::new(flat, [n, N_INPUT]);
    let input = Tensor::<B, 2>::from_data(data, device);
    let out = net.forward(input);
    let raw = out.into_data().to_vec::<f32>().expect("f32 output");
    raw.chunks(N_OUTPUT).map(equity_from_row).collect()
}

// 1-ply: pick the move that minimises the opponent's reply equity.
pub fn choose_1ply<B: Backend>(
    net: &FlyNet<B>,
    board: &Board,
    dice: [u8; 2],
    device: &B::Device,
) -> Option<Board> {
    let ends = legal_end_boards(board, dice);
    if ends.is_empty() {
        return None;
    }

    let mut encoded = Vec::with_capacity(ends.len());
    for e in &ends {
        if e.current_won() {
            return Some(e.clone());
        }
        encoded.push(encode(&e.flip()));
    }

    let opp_eq = equities(net, &encoded, device);
    let mut best = 0usize;
    let mut best_val = f32::INFINITY;
    for (i, &v) in opp_eq.iter().enumerate() {
        if v < best_val {
            best_val = v;
            best = i;
        }
    }
    Some(ends[best].clone())
}

// The 21 distinct rolls with probabilities (doubles 1/36, others 2/36).
pub fn dice_combos() -> Vec<([u8; 2], f32)> {
    let mut v = Vec::with_capacity(21);
    for a in 1..=6u8 {
        for b in a..=6u8 {
            let w = if a == b { 1.0 / 36.0 } else { 2.0 / 36.0 };
            v.push(([a, b], w));
        }
    }
    v
}

// 2-ply: for each candidate, average over the opponent's 21 rolls (each played to
// minimise our equity) and pick the move maximising that expectation.
pub fn choose_2ply<B: Backend>(
    net: &FlyNet<B>,
    board: &Board,
    dice: [u8; 2],
    device: &B::Device,
) -> Option<Board> {
    let ends = legal_end_boards(board, dice);
    if ends.is_empty() {
        return None;
    }
    for e in &ends {
        if e.current_won() {
            return Some(e.clone());
        }
    }

    // Shortlist the top 1-ply moves; the best 2-ply move is almost always among them.
    let mut enc1: Vec<f32> = Vec::new();
    for e in &ends {
        encode_into(&e.flip(), &mut enc1);
    }
    let opp_eq1 = equities_flat(net, enc1, ends.len(), device);
    let mut order: Vec<usize> = (0..ends.len()).collect();
    order.sort_by(|&a, &b| opp_eq1[a].partial_cmp(&opp_eq1[b]).unwrap_or(std::cmp::Ordering::Equal));
    let k = TWO_PLY_CANDIDATES.min(ends.len());
    let shortlist = &order[..k];

    let combos = dice_combos();

    // One batch over the shortlist: every opponent roll, reply, and pass position.
    let mut flat: Vec<f32> = Vec::new();
    let mut npos = 0usize;
    let mut cands: Vec<(usize, usize, Vec<(f32, usize, usize)>)> = Vec::with_capacity(k);
    for &ei in shortlist {
        let e = &ends[ei];
        let base_idx = npos;
        encode_into(e, &mut flat);
        npos += 1;
        let e_opp = e.flip();
        let mut spans = Vec::with_capacity(combos.len());
        for (d, w) in &combos {
            let opp_ends = legal_end_boards(&e_opp, *d);
            let start = npos;
            for oe in &opp_ends {
                encode_into(&oe.flip(), &mut flat);
                npos += 1;
            }
            spans.push((*w, start, npos));
        }
        cands.push((ei, base_idx, spans));
    }

    let eqs = equities_flat(net, flat, npos, device);

    let mut best = shortlist[0];
    let mut best_val = f32::NEG_INFINITY;
    for (ei, base_idx, spans) in &cands {
        let base = eqs[*base_idx];
        let mut val = 0.0f32;
        for (w, start, end) in spans {
            let vd = if start == end {
                base
            } else {
                eqs[*start..*end].iter().cloned().fold(f32::INFINITY, f32::min)
            };
            val += w * vd;
        }
        if val > best_val {
            best_val = val;
            best = *ei;
        }
    }
    Some(ends[best].clone())
}

const TWO_PLY_CANDIDATES: usize = 8;

// 1-ply with epsilon-greedy exploration (self-play).
pub fn choose_1ply_explore<B: Backend>(
    net: &FlyNet<B>,
    board: &Board,
    dice: [u8; 2],
    device: &B::Device,
    epsilon: f32,
    rng: &mut impl Rng,
) -> Option<Board> {
    if epsilon > 0.0 && rng.gen::<f32>() < epsilon {
        let ends = legal_end_boards(board, dice);
        return if ends.is_empty() {
            None
        } else {
            Some(ends[rng.gen_range(0..ends.len())].clone())
        };
    }
    choose_1ply(net, board, dice, device)
}

pub fn choose_random(board: &Board, dice: [u8; 2], rng: &mut impl Rng) -> Option<Board> {
    let ends = legal_end_boards(board, dice);
    if ends.is_empty() {
        None
    } else {
        Some(ends[rng.gen_range(0..ends.len())].clone())
    }
}
