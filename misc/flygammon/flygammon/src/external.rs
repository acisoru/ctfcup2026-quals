//! External-engine opponent over a subprocess (for benchmarking vs gnubg etc.).
//!
//! This is EVAL-ONLY (too slow for the training league). It spawns a command and
//! speaks a tiny line protocol, so any engine can be wrapped by a thin adapter:
//!
//! Per decision we write one line to the child's stdin:
//!   `p0 p1 ... p23 bar_cur bar_opp off_cur off_opp d1 d2`
//! all from the MOVER's perspective (positive = mover, negative = opponent),
//! mover bears off past index 0.
//!
//! The child replies with one line: the resulting board as 28 ints
//!   `p0 ... p23 bar_cur bar_opp off_cur off_opp`
//! or the token `PASS`.
//!
//! The child's reply is untrusted: we accept it only if it exactly matches one of
//! our own legal end positions, otherwise we fall back to a legal move. So a
//! buggy adapter can never make an illegal move, only a weak one.
//!
//! To benchmark against **gnubg**: write a small adapter (e.g. a Python script
//! using gnubg's scripting interface) that reads a request line, asks gnubg for
//! the best move, and prints the resulting board in this format.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

use burn::tensor::backend::Backend;
use rand::rngs::StdRng;
use rand::SeedableRng;

use crate::agent::{choose_1ply, choose_2ply};
use crate::engine::{legal_end_boards, roll, score_points, Board, CUR, OPP};
use crate::model::FlyNet;

pub fn board_to_ints(b: &Board) -> Vec<i32> {
    let mut v: Vec<i32> = b.points.iter().map(|&x| x as i32).collect();
    v.push(b.bar[CUR] as i32);
    v.push(b.bar[OPP] as i32);
    v.push(b.off[CUR] as i32);
    v.push(b.off[OPP] as i32);
    v
}

pub fn board_from_ints(v: &[i32]) -> Option<Board> {
    if v.len() < 28 {
        return None;
    }
    let mut points = [0i8; 24];
    for i in 0..24 {
        points[i] = v[i] as i8;
    }
    Some(Board {
        points,
        bar: [v[24] as u8, v[25] as u8],
        off: [v[26] as u8, v[27] as u8],
    })
}

/// A spawned external engine speaking the line protocol above.
pub struct ExternalEngine {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl ExternalEngine {
    pub fn spawn(cmd: &str) -> std::io::Result<Self> {
        let mut parts = cmd.split_whitespace();
        let prog = parts
            .next()
            .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::InvalidInput, "empty command"))?;
        let mut c = Command::new(prog);
        c.args(parts).stdin(Stdio::piped()).stdout(Stdio::piped());
        let mut child = c.spawn()?;
        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());
        Ok(Self { child, stdin, stdout })
    }

    /// Ask the engine for its move; validate against our legal moves.
    pub fn choose(&mut self, board: &Board, dice: [u8; 2]) -> Option<Board> {
        let legal = legal_end_boards(board, dice);
        if legal.is_empty() {
            return None; // forced pass
        }
        let mut line = String::new();
        for x in board_to_ints(board) {
            line.push_str(&x.to_string());
            line.push(' ');
        }
        line.push_str(&format!("{} {}\n", dice[0], dice[1]));
        if self.stdin.write_all(line.as_bytes()).is_err() || self.stdin.flush().is_err() {
            return Some(legal[0].clone());
        }
        let mut resp = String::new();
        if self.stdout.read_line(&mut resp).is_err() {
            return Some(legal[0].clone());
        }
        let resp = resp.trim();
        if resp.eq_ignore_ascii_case("PASS") {
            return Some(legal[0].clone());
        }
        let nums: Vec<i32> = resp.split_whitespace().filter_map(|s| s.parse().ok()).collect();
        if let Some(cand) = board_from_ints(&nums) {
            if legal.iter().any(|e| *e == cand) {
                return Some(cand);
            }
        }
        // Untrusted / illegal reply: fall back to a legal move.
        Some(legal[0].clone())
    }
}

impl Drop for ExternalEngine {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// Win fraction of `net` against the external engine over `games` games.
pub fn eval_net_vs_engine<B: Backend>(
    net: &FlyNet<B>,
    engine_cmd: &str,
    games: usize,
    ply: u8,
    seed: u64,
) -> std::io::Result<f32> {
    let mut eng = ExternalEngine::spawn(engine_cmd)?;
    let device = B::Device::default();
    let mut rng = StdRng::seed_from_u64(seed);
    let mut wins = 0usize;

    for i in 0..games {
        let net_first = i % 2 == 0;
        let mut board = Board::new_game();
        let mut to_move = 0usize;
        let mut result = 0i32;
        for _ in 0..10_000 {
            let net_turn = (to_move == 0) == net_first;
            let dice = roll(&mut rng);
            let choice = if net_turn {
                if ply >= 2 {
                    choose_2ply(net, &board, dice, &device)
                } else {
                    choose_1ply(net, &board, dice, &device)
                }
            } else {
                eng.choose(&board, dice)
            };
            match choice {
                Some(end) => {
                    if end.current_won() {
                        let pts = score_points(&end) as i32;
                        result = if net_turn { pts } else { -pts };
                        break;
                    }
                    board = end.flip();
                }
                None => board = board.flip(),
            }
            to_move ^= 1;
        }
        if result > 0 {
            wins += 1;
        }
    }
    Ok(wins as f32 / games.max(1) as f32)
}
