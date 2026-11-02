//! VRF proof generation, matching VRF.sol byte-for-byte.
//!
//! For ply (gameId, turn): u = keccak256("flygammon-vrf-u" || gameId || turn) % p
//! (bumped to >=2), y = u^s mod p, and a Chaum-Pedersen DLEQ proof (a1,a2,z) that
//! log_g(h) == log_u(y). Dice come from keccak256("flygammon-vrf-dice" || y).

use num_bigint::BigUint;
use num_traits::One;
use rand::RngCore;
use sha3::{Digest, Keccak256};

#[derive(Clone)]
pub struct Params {
    pub p: BigUint,
    pub g: BigUint,
    pub h: BigUint,
    pub s: BigUint, // oracle secret
}

pub struct Proof {
    pub y: BigUint,
    pub a1: BigUint,
    pub a2: BigUint,
    pub z: BigUint,
}

pub fn be32(x: &BigUint) -> [u8; 32] {
    let mut o = [0u8; 32];
    let b = x.to_bytes_be();
    assert!(b.len() <= 32, "value exceeds 32 bytes");
    o[32 - b.len()..].copy_from_slice(&b);
    o
}

fn keccak(parts: &[&[u8]]) -> [u8; 32] {
    let mut hsr = Keccak256::new();
    for part in parts {
        hsr.update(part);
    }
    let out = hsr.finalize();
    let mut o = [0u8; 32];
    o.copy_from_slice(&out);
    o
}

/// u = keccak256(abi.encodePacked("flygammon-vrf-u", gameId, turn)) % p, >= 2.
pub fn u_for(p: &BigUint, game_id: u64, turn: u64) -> BigUint {
    let gid = BigUint::from(game_id);
    let t = BigUint::from(turn);
    let dig = keccak(&[b"flygammon-vrf-u", &be32(&gid), &be32(&t)]);
    let mut u = BigUint::from_bytes_be(&dig) % p;
    let two = BigUint::from(2u32);
    if u < two {
        u += two;
    }
    u
}

/// (d1, d2) in 1..6 from the proven VRF value y.
pub fn dice_from_y(y: &BigUint) -> (u8, u8) {
    let dig = keccak(&[b"flygammon-vrf-dice", &be32(y)]);
    let hh = BigUint::from_bytes_be(&dig);
    let six = BigUint::from(6u32);
    let d1 = (&hh % &six).to_bytes_be().last().copied().unwrap_or(0) + 1;
    let hh8 = &hh >> 8u32;
    let d2 = (&hh8 % &six).to_bytes_be().last().copied().unwrap_or(0) + 1;
    (d1, d2)
}

/// Build a valid DLEQ proof for ply (gameId, turn).
pub fn prove(params: &Params, game_id: u64, turn: u64) -> Proof {
    let p = &params.p;
    let u = u_for(p, game_id, turn);
    let y = u.modpow(&params.s, p);

    let order = p - BigUint::one(); // g is a primitive root => ord(g) = p-1
    let k = rand_below(&order);
    let a1 = params.g.modpow(&k, p);
    let a2 = u.modpow(&k, p);

    let c = BigUint::from_bytes_be(&keccak(&[
        &be32(p),
        &be32(&params.g),
        &be32(&params.h),
        &be32(&u),
        &be32(&y),
        &be32(&a1),
        &be32(&a2),
    ]));

    // z = (k + c*s) mod order
    let z = (&k + (&c * &params.s) % &order) % &order;
    Proof { y, a1, a2, z }
}

fn rand_below(bound: &BigUint) -> BigUint {
    let mut rng = rand::thread_rng();
    let bytes = (bound.bits() as usize + 7) / 8 + 8; // a little extra to reduce bias
    let mut buf = vec![0u8; bytes];
    rng.fill_bytes(&mut buf);
    let v = BigUint::from_bytes_be(&buf) % bound;
    if v < BigUint::from(2u32) {
        v + BigUint::from(2u32)
    } else {
        v
    }
}
