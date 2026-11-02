//! Backgammon engine.
//!
//! The board is stored **canonically from the perspective of the player to move**.
//! The player to move owns the positive checkers and moves from high indices (23)
//! toward 0, bearing off past index 0. Their home board is indices 0..=5.
//! The opponent owns negative checkers and is the exact mirror.
//!
//! After a full turn we call [`Board::flip`], which rewrites the board from the
//! opponent's perspective. This "always move in one direction" trick means move
//! generation only has to implement a single direction.

use rand::Rng;
use std::collections::HashSet;

pub const N_POINTS: usize = 24;
/// Index into `bar` / `off` for the player to move.
pub const CUR: usize = 0;
/// Index into `bar` / `off` for the opponent.
pub const OPP: usize = 1;

#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct Board {
    /// `points[i] > 0`: current player's checkers; `< 0`: opponent's.
    pub points: [i8; N_POINTS],
    /// Checkers on the bar: `[current, opponent]`.
    pub bar: [u8; 2],
    /// Checkers borne off: `[current, opponent]`.
    pub off: [u8; 2],
}

impl Board {
    /// Standard opening position, from the opening player's perspective.
    pub fn new_game() -> Self {
        let mut points = [0i8; N_POINTS];
        // Current player (positive), moving 23 -> 0.
        points[23] = 2;
        points[12] = 5;
        points[7] = 3;
        points[5] = 5;
        // Opponent (negative), mirror image.
        points[0] = -2;
        points[11] = -5;
        points[16] = -3;
        points[18] = -5;
        Board {
            points,
            bar: [0, 0],
            off: [0, 0],
        }
    }

    /// Rewrite the board from the opponent's perspective (turn hand-off).
    pub fn flip(&self) -> Board {
        let mut points = [0i8; N_POINTS];
        for i in 0..N_POINTS {
            points[i] = -self.points[N_POINTS - 1 - i];
        }
        Board {
            points,
            bar: [self.bar[OPP], self.bar[CUR]],
            off: [self.off[OPP], self.off[CUR]],
        }
    }

    /// True if all 15 of the current player's checkers are in the home board
    /// (indices 0..=5) and none are on the bar — precondition for bearing off.
    pub fn all_current_home(&self) -> bool {
        if self.bar[CUR] > 0 {
            return false;
        }
        (6..N_POINTS).all(|i| self.points[i] <= 0)
    }

    /// True once the current player has borne off all 15 checkers.
    pub fn current_won(&self) -> bool {
        self.off[CUR] == 15
    }
}

/// Roll two dice.
pub fn roll(rng: &mut impl Rng) -> [u8; 2] {
    [rng.gen_range(1..=6), rng.gen_range(1..=6)]
}

/// All legal single-checker moves for the current player using one die `d`.
/// Each returned board is a clone of `b` with exactly one checker advanced.
fn single_moves(b: &Board, d: u8) -> Vec<Board> {
    let d = d as usize;
    let mut res = Vec::new();

    // If we have checkers on the bar we must enter them first.
    if b.bar[CUR] > 0 {
        let t = N_POINTS - d; // die 1 -> index 23 ... die 6 -> index 18
        if b.points[t] > -2 {
            let mut nb = b.clone();
            if nb.points[t] == -1 {
                nb.points[t] = 0;
                nb.bar[OPP] += 1; // hit opponent blot
            }
            nb.points[t] += 1;
            nb.bar[CUR] -= 1;
            res.push(nb);
        }
        return res;
    }

    let all_home = b.all_current_home();
    for p in 0..N_POINTS {
        if b.points[p] <= 0 {
            continue;
        }
        let target = p as i32 - d as i32;
        if target >= 0 {
            // Ordinary move within the board.
            let t = target as usize;
            if b.points[t] > -2 {
                let mut nb = b.clone();
                if nb.points[t] == -1 {
                    nb.points[t] = 0;
                    nb.bar[OPP] += 1;
                }
                nb.points[t] += 1;
                nb.points[p] -= 1;
                res.push(nb);
            }
        } else if all_home {
            // Bearing off. `pip` is the exact die needed to bear off from `p`.
            let pip = p + 1;
            if d == pip {
                let mut nb = b.clone();
                nb.points[p] -= 1;
                nb.off[CUR] += 1;
                res.push(nb);
            } else if d > pip {
                // Overshoot allowed only when no checker sits on a higher point.
                let higher_occupied = ((p + 1)..6).any(|i| b.points[i] > 0);
                if !higher_occupied {
                    let mut nb = b.clone();
                    nb.points[p] -= 1;
                    nb.off[CUR] += 1;
                    res.push(nb);
                }
            }
        }
    }
    res
}

/// Depth-first enumeration of every move sequence, recording each leaf together
/// with the dice actually consumed to reach it.
fn dfs(board: &Board, dice: &[u8], used: &mut Vec<u8>, out: &mut Vec<(Board, Vec<u8>)>) {
    let mut advanced = false;
    for i in 0..dice.len() {
        let d = dice[i];
        let mut rest = dice.to_vec();
        rest.remove(i);
        for nb in single_moves(board, d) {
            advanced = true;
            used.push(d);
            dfs(&nb, &rest, used, out);
            used.pop();
        }
    }
    if !advanced {
        out.push((board.clone(), used.clone()));
    }
}

/// All legal end-of-turn positions for the current player given a dice roll.
///
/// Returns an empty vector when no legal move exists (the turn is forfeited).
/// Enforces the two standard obligations: play the maximum number of dice
/// possible, and — when only one of two distinct dice can be played — play the
/// larger one if that is legal.
pub fn legal_end_boards(board: &Board, dice: [u8; 2]) -> Vec<Board> {
    let multiset: Vec<u8> = if dice[0] == dice[1] {
        vec![dice[0]; 4]
    } else {
        vec![dice[0], dice[1]]
    };

    let mut leaves: Vec<(Board, Vec<u8>)> = Vec::new();
    let mut used = Vec::new();
    dfs(board, &multiset, &mut used, &mut leaves);

    let max_len = leaves.iter().map(|(_, u)| u.len()).max().unwrap_or(0);
    if max_len == 0 {
        return Vec::new();
    }

    let mut kept: Vec<(Board, Vec<u8>)> =
        leaves.into_iter().filter(|(_, u)| u.len() == max_len).collect();

    // "Play the larger die" rule when exactly one of two distinct dice is usable.
    if max_len == 1 && dice[0] != dice[1] {
        let larger = dice[0].max(dice[1]);
        if kept.iter().any(|(_, u)| u[0] == larger) {
            kept.retain(|(_, u)| u[0] == larger);
        }
    }

    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for (b, _) in kept {
        if seen.insert(b.clone()) {
            out.push(b);
        }
    }
    out
}

/// Points scored when the current player has just borne off their last checker.
/// 1 = single, 2 = gammon, 3 = backgammon.
pub fn score_points(b: &Board) -> u32 {
    debug_assert!(b.current_won());
    if b.off[OPP] > 0 {
        return 1;
    }
    // Opponent bore off nothing: gammon, or backgammon if a loser checker is
    // still on the bar or trapped in the winner's home board (indices 0..=5).
    let loser_in_winner_home = (0..6).any(|i| b.points[i] < 0);
    if b.bar[OPP] > 0 || loser_in_winner_home {
        3
    } else {
        2
    }
}

// Like single_moves, tagging each result with its source index (24 = from bar).
fn single_moves_tagged(b: &Board, d: u8) -> Vec<(Board, u8)> {
    let du = d as usize;
    let mut res = Vec::new();

    if b.bar[CUR] > 0 {
        let t = N_POINTS - du;
        if b.points[t] > -2 {
            let mut nb = b.clone();
            if nb.points[t] == -1 {
                nb.points[t] = 0;
                nb.bar[OPP] += 1;
            }
            nb.points[t] += 1;
            nb.bar[CUR] -= 1;
            res.push((nb, N_POINTS as u8)); // 24 => from bar
        }
        return res;
    }

    let all_home = b.all_current_home();
    for p in 0..N_POINTS {
        if b.points[p] <= 0 {
            continue;
        }
        let target = p as i32 - du as i32;
        if target >= 0 {
            let t = target as usize;
            if b.points[t] > -2 {
                let mut nb = b.clone();
                if nb.points[t] == -1 {
                    nb.points[t] = 0;
                    nb.bar[OPP] += 1;
                }
                nb.points[t] += 1;
                nb.points[p] -= 1;
                res.push((nb, p as u8));
            }
        } else if all_home {
            let pip = p + 1;
            if du == pip {
                let mut nb = b.clone();
                nb.points[p] -= 1;
                nb.off[CUR] += 1;
                res.push((nb, p as u8));
            } else if du > pip {
                let higher_occupied = ((p + 1)..6).any(|i| b.points[i] > 0);
                if !higher_occupied {
                    let mut nb = b.clone();
                    nb.points[p] -= 1;
                    nb.off[CUR] += 1;
                    res.push((nb, p as u8));
                }
            }
        }
    }
    res
}

fn dfs_tagged(
    board: &Board,
    dice: &[u8],
    path: &mut Vec<(u8, u8)>,
    out: &mut Vec<(Board, Vec<(u8, u8)>)>,
) {
    let mut advanced = false;
    for i in 0..dice.len() {
        let d = dice[i];
        let mut rest = dice.to_vec();
        rest.remove(i);
        for (nb, from) in single_moves_tagged(board, d) {
            advanced = true;
            path.push((from, d));
            dfs_tagged(&nb, &rest, path, out);
            path.pop();
        }
    }
    if !advanced {
        out.push((board.clone(), path.clone()));
    }
}

// legal_end_boards, plus a (from, die) move path for each end (24 = from bar).
pub fn legal_end_boards_with_paths(board: &Board, dice: [u8; 2]) -> Vec<(Board, Vec<(u8, u8)>)> {
    let multiset: Vec<u8> = if dice[0] == dice[1] {
        vec![dice[0]; 4]
    } else {
        vec![dice[0], dice[1]]
    };

    let mut leaves: Vec<(Board, Vec<(u8, u8)>)> = Vec::new();
    let mut path = Vec::new();
    dfs_tagged(board, &multiset, &mut path, &mut leaves);

    let max_len = leaves.iter().map(|(_, p)| p.len()).max().unwrap_or(0);
    if max_len == 0 {
        return Vec::new();
    }
    let mut kept: Vec<(Board, Vec<(u8, u8)>)> =
        leaves.into_iter().filter(|(_, p)| p.len() == max_len).collect();

    if max_len == 1 && dice[0] != dice[1] {
        let larger = dice[0].max(dice[1]);
        if kept.iter().any(|(_, p)| p[0].1 == larger) {
            kept.retain(|(_, p)| p[0].1 == larger);
        }
    }

    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for (b, p) in kept {
        if seen.insert(b.clone()) {
            out.push((b, p));
        }
    }
    out
}

// A legal move path from `board` under `dice` reaching `target`, or None.
pub fn path_to(board: &Board, dice: [u8; 2], target: &Board) -> Option<Vec<(u8, u8)>> {
    legal_end_boards_with_paths(board, dice)
        .into_iter()
        .find(|(b, _)| b == target)
        .map(|(_, p)| p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opening_position_has_fifteen_each() {
        let b = Board::new_game();
        let cur: i32 = b.points.iter().filter(|&&x| x > 0).map(|&x| x as i32).sum();
        let opp: i32 = b.points.iter().filter(|&&x| x < 0).map(|&x| -x as i32).sum();
        assert_eq!(cur, 15);
        assert_eq!(opp, 15);
    }

    #[test]
    fn flip_is_involutive() {
        let b = Board::new_game();
        assert_eq!(b, b.flip().flip());
    }

    #[test]
    fn opening_rolls_generate_moves() {
        let b = Board::new_game();
        // A 3-1 opening has legal plays.
        let ends = legal_end_boards(&b, [3, 1]);
        assert!(!ends.is_empty());
        // Every end board still totals 15 checkers for the mover.
        for e in &ends {
            let cur: i32 = e.points.iter().filter(|&&x| x > 0).map(|&x| x as i32).sum::<i32>()
                + e.off[CUR] as i32
                + e.bar[CUR] as i32;
            assert_eq!(cur, 15);
        }
    }

    #[test]
    fn doubles_allow_up_to_four_moves() {
        let b = Board::new_game();
        let ends = legal_end_boards(&b, [6, 6]);
        assert!(!ends.is_empty());
    }
}
