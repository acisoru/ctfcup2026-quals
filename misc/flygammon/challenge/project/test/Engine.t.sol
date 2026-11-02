// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Engine} from "../src/Engine.sol";

contract EngineTest is Test {
    // External wrappers so we can pass memory arrays into calldata params and so
    // transient-storage (maxLen) runs in a call context.
    function vp(uint256 key, uint8 a, uint8 b, uint8[] calldata f, uint8[] calldata d)
        external
        returns (uint256, bool)
    {
        return Engine.validatePath(key, a, b, f, d);
    }

    function ml(uint256 key, uint256 rem) external returns (uint16) {
        return Engine.maxLen(key, rem);
    }

    function _rem(uint8 a, uint8 b) internal pure returns (uint256) {
        if (a == b) return 4 * (uint256(1) << (4 * a));
        return (uint256(1) << (4 * a)) | (uint256(1) << (4 * b));
    }

    function _moverCount(int256[28] memory v) internal pure returns (int256 s) {
        for (uint256 i = 0; i < 24; i++) {
            if (v[i] > 0) s += v[i];
        }
        s += v[26] + v[24];
    }

    function _oppCount(int256[28] memory v) internal pure returns (int256 s) {
        for (uint256 i = 0; i < 24; i++) {
            if (v[i] < 0) s += -v[i];
        }
        s += v[27] + v[25];
    }

    function _u8(uint8 a) internal pure returns (uint8[] memory r) {
        r = new uint8[](1);
        r[0] = a;
    }

    function _u8(uint8 a, uint8 b) internal pure returns (uint8[] memory r) {
        r = new uint8[](2);
        r[0] = a;
        r[1] = b;
    }

    function testOpeningFifteenEach() public pure {
        int256[28] memory v = Engine.intsFromKey(Engine.newGameKey());
        assertEq(_moverCount(v), int256(15));
        assertEq(_oppCount(v), int256(15));
    }

    function testFlipInvolutive() public pure {
        uint256 k = Engine.newGameKey();
        assertEq(k, Engine.flipKey(Engine.flipKey(k)));
    }

    function testMaxLenOpening31() public {
        uint16 m = this.ml(Engine.newGameKey(), _rem(3, 1));
        assertEq(uint256(m), 2); // both dice playable at the opening
    }

    function testMaxLenDoubles66() public {
        uint16 m = this.ml(Engine.newGameKey(), _rem(6, 6));
        assertGe(uint256(m), 2);
        assertLe(uint256(m), 4);
    }

    function testLegalPathSucceeds() public {
        // [3,1]: 23->20 then 20->19 — two legal sub-moves (= max).
        (uint256 fk, bool won) = this.vp(Engine.newGameKey(), 3, 1, _u8(23, 20), _u8(3, 1));
        assertTrue(!won);
        int256[28] memory v = Engine.intsFromKey(fk);
        assertEq(_moverCount(v), int256(15));
        assertEq(_oppCount(v), int256(15));
    }

    function testUnderplayReverts() public {
        // Only one sub-move for [3,1] while both are playable => must use max dice.
        vm.expectRevert(bytes("must use max dice"));
        this.vp(Engine.newGameKey(), 3, 1, _u8(23), _u8(3));
    }

    function testIllegalLandingReverts() public {
        // 12->11 with die 1 lands on opponent's 5-stack (blocked).
        vm.expectRevert(bytes("illegal submove"));
        this.vp(Engine.newGameKey(), 1, 3, _u8(12), _u8(1));
    }

    function _nearWin(int256 offOpp) internal pure returns (int256[28] memory v) {
        v[0] = 1; // mover's last checker on the 1-point
        v[26] = 14; // off_cur
        v[27] = offOpp; // off_opp
        // opponent's remaining checkers far away (point 23), none in mover home / bar
        v[23] = -(15 - offOpp);
    }

    function testBearOffSingle() public {
        uint256 key = Engine.keyFromInts(_nearWin(1));
        (uint256 fk, bool won) = this.vp(key, 1, 3, _u8(0), _u8(1));
        assertTrue(won);
        assertEq(Engine.scorePoints(fk), 1);
    }

    function testBearOffGammon() public {
        uint256 key = Engine.keyFromInts(_nearWin(0));
        (uint256 fk, bool won) = this.vp(key, 1, 2, _u8(0), _u8(1));
        assertTrue(won);
        assertEq(Engine.scorePoints(fk), 2);
    }
}
