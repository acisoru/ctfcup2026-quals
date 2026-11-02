//! Fixed, non-learning benchmark opponents with distinct playing styles.
//!
//! Each style is a stationary greedy policy driven by a different weighting of
//! board features. They serve two purposes:
//! - **Evaluation:** a win-rate profile across styles shows where the net is
//!   weak (racing vs contact vs blocking vs safe play).
//! - **Training (league):** playing against varied styles stops the net from
//!   overfitting to its own self-play style.
//!
//! These are hand-crafted stand-ins for external engines. A real benchmark
//! (pubeval / gnubg) can be added later as another opponent behind this same
//! interface.

use crate::engine::{legal_end_boards, Board, CUR, N_POINTS, OPP};

/// Distinct playing styles, including several deliberately unconventional ones.
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Style {
    /// Pure racer: minimise own pip, run home.
    Racer,
    /// Aggressive: hit opponent blots, put checkers on the bar.
    Hitter,
    /// Conservative: avoid leaving blots, play safe.
    Safe,
    /// Blocker: build made points and long primes.
    Prime,
    /// Back game: hold deep anchors in the opponent's home, embrace contact.
    BackGame,
    /// Blitz: all-out attack — close the board and pile hits fast.
    Blitz,
    /// Hoarder: over-stacks points into tall towers (a known-bad, odd style).
    Hoarder,
    /// Ultra-safe coward: essentially never leaves a blot.
    Coward,
}

pub const STYLES: [Style; 8] = [
    Style::Racer,
    Style::Hitter,
    Style::Safe,
    Style::Prime,
    Style::BackGame,
    Style::Blitz,
    Style::Hoarder,
    Style::Coward,
];

pub fn style_name(s: Style) -> &'static str {
    match s {
        Style::Racer => "racer",
        Style::Hitter => "hitter",
        Style::Safe => "safe",
        Style::Prime => "prime",
        Style::BackGame => "backgame",
        Style::Blitz => "blitz",
        Style::Hoarder => "hoarder",
        Style::Coward => "coward",
    }
}

/// Standard pip counts `(current, opponent)` (bar checkers count as 25).
pub fn pip_counts(b: &Board) -> (i32, i32) {
    let mut own = b.bar[CUR] as i32 * 25;
    let mut opp = b.bar[OPP] as i32 * 25;
    for i in 0..N_POINTS {
        let c = b.points[i];
        if c > 0 {
            own += c as i32 * (i as i32 + 1);
        } else if c < 0 {
            opp += (-c) as i32 * (N_POINTS as i32 - i as i32);
        }
    }
    (own, opp)
}

/// Length of the longest run of consecutive made points (>=2 own checkers).
fn longest_block(b: &Board) -> i32 {
    let mut best = 0i32;
    let mut run = 0i32;
    for i in 0..N_POINTS {
        if b.points[i] >= 2 {
            run += 1;
            best = best.max(run);
        } else {
            run = 0;
        }
    }
    best
}

/// Board summary features from the current player's perspective.
struct Feats {
    pip_diff: i32, // opp_pip - own_pip (positive good)
    own_blots: i32,
    made_home: i32,
    block: i32,
    opp_on_bar: i32,
    off: i32,
    back_anchors: i32, // own made points deep in the opponent's home (i >= 18)
    max_stack: i32,    // tallest own tower
}

fn feats(b: &Board) -> Feats {
    let (own_pip, opp_pip) = pip_counts(b);
    let mut own_blots = 0;
    let mut made_home = 0;
    let mut back_anchors = 0;
    let mut max_stack: i32 = 0;
    for i in 0..N_POINTS {
        let c = b.points[i];
        if c == 1 {
            own_blots += 1;
        }
        if c >= 2 {
            if i < 6 {
                made_home += 1;
            }
            if i >= 18 {
                back_anchors += 1;
            }
        }
        if c as i32 > max_stack {
            max_stack = c as i32;
        }
    }
    Feats {
        pip_diff: opp_pip - own_pip,
        own_blots,
        made_home,
        block: longest_block(b),
        opp_on_bar: b.bar[OPP] as i32,
        off: b.off[CUR] as i32 - b.off[OPP] as i32,
        back_anchors,
        max_stack,
    }
}

/// Heuristic value of a position for the player to move, per style.
pub fn style_score(style: Style, b: &Board) -> f32 {
    let f = feats(b);
    let (pd, blot, home, block, bar, off, back, stack) = (
        f.pip_diff as f32,
        f.own_blots as f32,
        f.made_home as f32,
        f.block as f32,
        f.opp_on_bar as f32,
        f.off as f32,
        f.back_anchors as f32,
        f.max_stack as f32,
    );
    match style {
        Style::Racer => pd + 4.0 * off + 3.0 * home - 2.0 * blot,
        Style::Hitter => 0.3 * pd + 9.0 * bar + 2.0 * home - 1.0 * blot + 3.0 * off,
        Style::Safe => 0.7 * pd - 6.0 * blot + 3.0 * home + 4.0 * off,
        Style::Prime => 0.3 * pd + 5.0 * block + 3.0 * home + 4.0 * bar - 1.5 * blot + 2.0 * off,
        // Unconventional styles:
        Style::BackGame => 5.0 * back + 3.0 * bar + 2.0 * home - 0.5 * blot + 0.1 * pd,
        Style::Blitz => 10.0 * bar + 4.0 * home + 2.0 * off - 0.5 * blot + 0.2 * pd,
        Style::Hoarder => 2.5 * stack + 0.3 * pd + 1.0 * home - 0.5 * blot,
        Style::Coward => -50.0 * blot + 0.5 * pd + 2.0 * home + 3.0 * off,
    }
}

/// Greedy move choice for the given style. Deterministic.
pub fn choose_style(style: Style, board: &Board, dice: [u8; 2]) -> Option<Board> {
    let ends = legal_end_boards(board, dice);
    if ends.is_empty() {
        return None;
    }
    let mut best = 0usize;
    let mut best_v = f32::NEG_INFINITY;
    for (i, e) in ends.iter().enumerate() {
        if e.current_won() {
            return Some(e.clone());
        }
        let v = style_score(style, e);
        if v > best_v {
            best_v = v;
            best = i;
        }
    }
    Some(ends[best].clone())
}
