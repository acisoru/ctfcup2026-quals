// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Per-ply verifiable dice over Z_p^*. Each roll is a function of the oracle's
// secret s (public key h = g^s mod p): for ply (gameId, turn) the oracle posts
// y = u^s mod p and a Chaum-Pedersen proof that log_g(h) == log_u(y), verified
// on-chain. Dice derive from y. The game cannot advance without a valid proof.
//
//   a1 = g^k, a2 = u^k,  c = H(p,g,h,u,y,a1,a2),  z = k + c*s (mod ord g)
//   check: g^z == a1*h^c (mod p)  and  u^z == a2*y^c (mod p)
contract VRF {
    uint256 public immutable P;
    uint256 public immutable G;
    uint256 public immutable H;

    constructor(uint256 p, uint256 g, uint256 h) {
        P = p;
        G = g;
        H = h;
    }

    function uFor(uint256 gameId, uint256 turn) public view returns (uint256 u) {
        u = uint256(keccak256(abi.encodePacked("flygammon-vrf-u", gameId, turn))) % P;
        if (u < 2) u += 2;
    }

    function diceFromY(uint256 y) public pure returns (uint8 d1, uint8 d2) {
        uint256 hh = uint256(keccak256(abi.encodePacked("flygammon-vrf-dice", y)));
        d1 = uint8(hh % 6) + 1;
        d2 = uint8((hh >> 8) % 6) + 1;
    }

    function verifyAndValue(
        uint256 gameId,
        uint256 turn,
        uint256 y,
        uint256 a1,
        uint256 a2,
        uint256 z
    ) public view returns (uint256) {
        uint256 u = uFor(gameId, turn);
        require(y > 0 && y < P && a1 > 0 && a1 < P && a2 > 0 && a2 < P, "vrf: range");

        uint256 c = uint256(keccak256(abi.encodePacked(P, G, H, u, y, a1, a2)));

        require(_modexp(G, z, P) == mulmod(a1, _modexp(H, c, P), P), "vrf: eq1");
        require(_modexp(u, z, P) == mulmod(a2, _modexp(y, c, P), P), "vrf: eq2");

        return y;
    }

    function verifyDice(
        uint256 gameId,
        uint256 turn,
        uint256 y,
        uint256 a1,
        uint256 a2,
        uint256 z
    ) public view returns (uint8 d1, uint8 d2) {
        (d1, d2) = diceFromY(verifyAndValue(gameId, turn, y, a1, a2, z));
    }

    function _modexp(uint256 base, uint256 e, uint256 modulus) internal view returns (uint256 result) {
        assembly {
            let p := mload(0x40)
            mstore(p, 0x20)
            mstore(add(p, 0x20), 0x20)
            mstore(add(p, 0x40), 0x20)
            mstore(add(p, 0x60), base)
            mstore(add(p, 0x80), e)
            mstore(add(p, 0xa0), modulus)
            if iszero(staticcall(gas(), 0x05, p, 0xc0, p, 0x20)) { revert(0, 0) }
            result := mload(p)
            mstore(0x40, add(p, 0xc0))
        }
    }
}
