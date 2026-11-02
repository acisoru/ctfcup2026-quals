//! Board -> input vector encoding, from the current player's perspective.
//!
//! Layout:
//! - 24 points x 8 units (4 own + 4 opponent), TD-Gammon unary encoding.
//! - 4 globals: own bar, opp bar, own off, opp off.
//! - engineered features: pip counts and simple positional summaries.

use crate::engine::{Board, CUR, N_POINTS, OPP};

pub const N_EXTRA: usize = 7;

pub const N_INPUT: usize = N_POINTS * 8 + 4 + N_EXTRA;

// unary count -> [>=1, >=2, >=3, (n-3)/2]
#[inline]
fn unary(v: &mut [f32], base: usize, n: i32) {
    v[base] = 1.0;
    if n >= 2 {
        v[base + 1] = 1.0;
    }
    if n >= 3 {
        v[base + 2] = 1.0;
    }
    if n > 3 {
        v[base + 3] = (n as f32 - 3.0) / 2.0;
    }
}

pub fn encode(b: &Board) -> Vec<f32> {
    let mut v = Vec::with_capacity(N_INPUT);
    encode_into(b, &mut v);
    v
}

// Append this board's N_INPUT features to `out` (for batched inference).
pub fn encode_into(b: &Board, out: &mut Vec<f32>) {
    let base0 = out.len();
    out.resize(base0 + N_INPUT, 0.0);
    let v = &mut out[base0..base0 + N_INPUT];

    for i in 0..N_POINTS {
        let base = i * 8;
        let c = b.points[i];
        if c > 0 {
            unary(v, base, c as i32);
        } else if c < 0 {
            unary(v, base + 4, (-c) as i32);
        }
    }

    let g = N_POINTS * 8;
    v[g] = b.bar[CUR] as f32 / 2.0;
    v[g + 1] = b.bar[OPP] as f32 / 2.0;
    v[g + 2] = b.off[CUR] as f32 / 15.0;
    v[g + 3] = b.off[OPP] as f32 / 15.0;

    // Engineered features: pip counts (both sides), home points made, blots.
    let mut pip_own = b.bar[CUR] as i32 * 25;
    let mut pip_opp = b.bar[OPP] as i32 * 25;
    let mut home_own = 0i32;
    let mut home_opp = 0i32;
    let mut blots_own = 0i32;
    let mut blots_opp = 0i32;
    for i in 0..N_POINTS {
        let c = b.points[i];
        if c > 0 {
            pip_own += c as i32 * (i as i32 + 1);
            if i < 6 && c >= 2 {
                home_own += 1;
            }
            if c == 1 {
                blots_own += 1;
            }
        } else if c < 0 {
            pip_opp += (-c) as i32 * (N_POINTS as i32 - i as i32);
            if i >= 18 && c <= -2 {
                home_opp += 1;
            }
            if c == -1 {
                blots_opp += 1;
            }
        }
    }
    let e = g + 4;
    v[e] = pip_own as f32 / 167.0;
    v[e + 1] = pip_opp as f32 / 167.0;
    v[e + 2] = (pip_opp - pip_own) as f32 / 167.0;
    v[e + 3] = home_own as f32 / 6.0;
    v[e + 4] = home_opp as f32 / 6.0;
    v[e + 5] = blots_own as f32 / 15.0;
    v[e + 6] = blots_opp as f32 / 15.0;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encoding_length_is_stable() {
        let b = Board::new_game();
        assert_eq!(encode(&b).len(), N_INPUT);
    }

    #[test]
    fn opponent_distribution_is_visible() {
        // The strong model must see opponent stack heights (needed for the race).
        let mut b1 = Board::new_game();
        let mut b2 = b1.clone();
        b1.points[10] = -2;
        b2.points[10] = -5;
        assert_ne!(encode(&b1), encode(&b2));
    }

    #[test]
    fn pip_feature_tracks_race() {
        // Advancing our checkers lowers our pip feature.
        let mut b = Board::new_game();
        let before = encode(&b)[N_POINTS * 8 + 4];
        // Move a back checker forward (index 23 -> 20) to reduce pip.
        b.points[23] -= 1;
        b.points[20] += 1;
        let after = encode(&b)[N_POINTS * 8 + 4];
        assert!(after < before);
    }
}
