// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test} from "forge-std/Test.sol";
import {VRF} from "../src/VRF.sol";

contract VRFTest is Test {
    // Parameters from tools/gen_params.py 256 40 1 (s is the oracle secret).
    uint256 constant P = 89502947516009771765849277261165478628881012307783940880029600474557855464583;
    uint256 constant G = 5;
    uint256 constant S = 13654052880323412379663692421328806547061611885489941438207873342831887495671;
    uint256 constant H = 44901220482715202252686207829839618340116810666748949004425311426828074405165;

    VRF vrf;

    function setUp() public {
        vrf = new VRF(P, G, H);
    }

    function _modexp(uint256 base, uint256 e, uint256 m) internal view returns (uint256 r) {
        assembly {
            let p := mload(0x40)
            mstore(p, 0x20)
            mstore(add(p, 0x20), 0x20)
            mstore(add(p, 0x40), 0x20)
            mstore(add(p, 0x60), base)
            mstore(add(p, 0x80), e)
            mstore(add(p, 0xa0), m)
            if iszero(staticcall(gas(), 0x05, p, 0xc0, p, 0x20)) { revert(0, 0) }
            r := mload(p)
            mstore(0x40, add(p, 0xc0))
        }
    }

    /// Build a valid Chaum-Pedersen DLEQ proof for ply (gameId, turn).
    function _prove(uint256 gameId, uint256 turn, uint256 k)
        internal
        view
        returns (uint256 y, uint256 a1, uint256 a2, uint256 z)
    {
        uint256 u = vrf.uFor(gameId, turn);
        y = _modexp(u, S, P);
        a1 = _modexp(G, k, P);
        a2 = _modexp(u, k, P);
        uint256 c = uint256(keccak256(abi.encodePacked(P, G, H, u, y, a1, a2)));
        uint256 order = P - 1; // g is a primitive root
        z = addmod(k, mulmod(c, S, order), order);
    }

    function testValidProofVerifies() public view {
        (uint256 y, uint256 a1, uint256 a2, uint256 z) = _prove(7, 3, 123456789);
        uint256 val = vrf.verifyAndValue(7, 3, y, a1, a2, z);
        assertEq(val, y);
    }

    function testDiceDeterministic() public view {
        (uint256 y, uint256 a1, uint256 a2, uint256 z) = _prove(1, 0, 987654321);
        (uint8 d1, uint8 d2) = vrf.verifyDice(1, 0, y, a1, a2, z);
        assertTrue(d1 >= 1 && d1 <= 6);
        assertTrue(d2 >= 1 && d2 <= 6);
        (uint8 e1, uint8 e2) = vrf.diceFromY(y);
        assertEq(d1, e1);
        assertEq(d2, e2);
    }

    function testTamperedValueReverts() public {
        (uint256 y, uint256 a1, uint256 a2, uint256 z) = _prove(2, 5, 555);
        vm.expectRevert();
        vrf.verifyAndValue(2, 5, y + 1, a1, a2, z);
    }

    function testWrongPlyReverts() public {
        (uint256 y, uint256 a1, uint256 a2, uint256 z) = _prove(2, 5, 777);
        // Same proof, different turn => u differs => must fail.
        vm.expectRevert();
        vrf.verifyAndValue(2, 6, y, a1, a2, z);
    }

    function testForgedWithoutSecretFails() public {
        // An attacker who does NOT know s cannot produce y for a fresh ply: using
        // a guessed y with an honest-looking (a1,a2,z) must fail the equations.
        uint256 u = vrf.uFor(9, 9);
        uint256 fakeY = _modexp(u, 424242, P); // wrong exponent
        uint256 a1 = _modexp(G, 111, P);
        uint256 a2 = _modexp(u, 111, P);
        uint256 order = P - 1;
        uint256 c = uint256(keccak256(abi.encodePacked(P, G, H, u, fakeY, a1, a2)));
        uint256 z = addmod(111, mulmod(c, S, order), order);
        vm.expectRevert();
        vrf.verifyAndValue(9, 9, fakeY, a1, a2, z);
    }
}
