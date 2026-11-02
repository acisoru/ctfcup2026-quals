// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// Backgammon rules engine, port of engine.rs. Board is canonical from the mover's
// perspective (positive = mover, moving 23 -> 0, home 0..5; negative = opponent).
// A turn is submitted as a move path of up to 4 (from, die) sub-moves and must play
// the maximum number of dice (the larger of two distinct dice when only one fits).
// Boards pack into a uint256: 24 points x 6 bits two's-complement, then
// bar[cur],bar[opp],off[cur],off[opp] x 5 bits at offset 144.
library Engine {
    uint256 internal constant N_POINTS = 24;
    uint256 internal constant CUR = 0;
    uint256 internal constant OPP = 1;
    uint256 internal constant BAR_FROM = 24; // sentinel `from` meaning "enter from bar"

    uint256 private constant BASE = 144; // bit offset of bar/off fields

    function _getP(uint256 key, uint256 i) private pure returns (int256) {
        uint256 v = (key >> (6 * i)) & 0x3f;
        return v >= 32 ? int256(v) - 64 : int256(v);
    }

    function _setP(uint256 key, uint256 i, int256 val) private pure returns (uint256) {
        uint256 shift = 6 * i;
        uint256 cleared = key & ~(uint256(0x3f) << shift);
        uint256 v = uint256(uint8(int8(val))) & 0x3f;
        return cleared | (v << shift);
    }

    function _getBar(uint256 key, uint256 who) private pure returns (uint256) {
        return (key >> (BASE + 5 * who)) & 0x1f;
    }

    function _setBar(uint256 key, uint256 who, uint256 v) private pure returns (uint256) {
        uint256 shift = BASE + 5 * who;
        return (key & ~(uint256(0x1f) << shift)) | ((v & 0x1f) << shift);
    }

    function _getOff(uint256 key, uint256 who) private pure returns (uint256) {
        return (key >> (BASE + 10 + 5 * who)) & 0x1f;
    }

    function _setOff(uint256 key, uint256 who, uint256 v) private pure returns (uint256) {
        uint256 shift = BASE + 10 + 5 * who;
        return (key & ~(uint256(0x1f) << shift)) | ((v & 0x1f) << shift);
    }

    function newGameKey() internal pure returns (uint256 k) {
        k = _setP(k, 23, 2);
        k = _setP(k, 12, 5);
        k = _setP(k, 7, 3);
        k = _setP(k, 5, 5);
        k = _setP(k, 0, -2);
        k = _setP(k, 11, -5);
        k = _setP(k, 16, -3);
        k = _setP(k, 18, -5);
    }

    function flipKey(uint256 key) internal pure returns (uint256 c) {
        for (uint256 i = 0; i < N_POINTS; i++) {
            c = _setP(c, i, -_getP(key, N_POINTS - 1 - i));
        }
        c = _setBar(c, 0, _getBar(key, OPP));
        c = _setBar(c, 1, _getBar(key, CUR));
        c = _setOff(c, 0, _getOff(key, OPP));
        c = _setOff(c, 1, _getOff(key, CUR));
    }

    function currentWon(uint256 key) internal pure returns (bool) {
        return _getOff(key, CUR) == 15;
    }

    function _allHome(uint256 key) private pure returns (bool) {
        if (_getBar(key, CUR) > 0) return false;
        for (uint256 i = 6; i < N_POINTS; i++) {
            if (_getP(key, i) > 0) return false;
        }
        return true;
    }

    /// 1 = single, 2 = gammon, 3 = backgammon (mover has just borne off all 15).
    function scorePoints(uint256 key) internal pure returns (uint256) {
        if (_getOff(key, OPP) > 0) return 1;
        for (uint256 i = 0; i < 6; i++) {
            if (_getP(key, i) < 0) return 3; // loser checker in winner's home
        }
        if (_getBar(key, OPP) > 0) return 3;
        return 2;
    }

    // Apply one single-checker move (from,die); returns (ok, newKey).
    function applySub(uint256 key, uint256 from, uint256 die) internal pure returns (bool, uint256) {
        if (die < 1 || die > 6) return (false, 0);

        if (_getBar(key, CUR) > 0) {
            // Must enter from the bar first.
            if (from != BAR_FROM) return (false, 0);
            uint256 t = N_POINTS - die; // die 1 -> 23 ... die 6 -> 18
            int256 pt = _getP(key, t);
            if (pt <= -2) return (false, 0);
            uint256 nk = key;
            if (pt == -1) {
                nk = _setP(nk, t, 0);
                nk = _setBar(nk, OPP, _getBar(nk, OPP) + 1);
            }
            nk = _setP(nk, t, _getP(nk, t) + 1);
            nk = _setBar(nk, CUR, _getBar(nk, CUR) - 1);
            return (true, nk);
        }

        if (from >= N_POINTS) return (false, 0);
        if (_getP(key, from) <= 0) return (false, 0);

        int256 target = int256(from) - int256(die);
        if (target >= 0) {
            uint256 t = uint256(target);
            int256 pt = _getP(key, t);
            if (pt <= -2) return (false, 0);
            uint256 nk = key;
            if (pt == -1) {
                nk = _setP(nk, t, 0);
                nk = _setBar(nk, OPP, _getBar(nk, OPP) + 1);
            }
            nk = _setP(nk, t, _getP(nk, t) + 1);
            nk = _setP(nk, from, _getP(nk, from) - 1);
            return (true, nk);
        } else {
            // Bearing off (die > from, i.e. die >= pip).
            if (!_allHome(key)) return (false, 0);
            uint256 pip = from + 1;
            if (die > pip) {
                // Overshoot allowed only when no checker sits on a higher point.
                for (uint256 i = from + 1; i < 6; i++) {
                    if (_getP(key, i) > 0) return (false, 0);
                }
            }
            uint256 nk2 = _setP(key, from, _getP(key, from) - 1);
            nk2 = _setOff(nk2, CUR, _getOff(nk2, CUR) + 1);
            return (true, nk2);
        }
    }

    /// True if any legal single move exists with die `die`.
    function singlePlayable(uint256 key, uint256 die) internal pure returns (bool) {
        if (_getBar(key, CUR) > 0) {
            (bool ok,) = applySub(key, BAR_FROM, die);
            return ok;
        }
        for (uint256 from = 0; from < N_POINTS; from++) {
            if (_getP(key, from) <= 0) continue;
            (bool ok,) = applySub(key, from, die);
            if (ok) return true;
        }
        return false;
    }

    function _unit(uint256 d) private pure returns (uint256) {
        return uint256(1) << (4 * d);
    }

    function _count(uint256 rem, uint256 d) private pure returns (uint256) {
        return (rem >> (4 * d)) & 0xf;
    }

    // Max dice playable from key given remaining multiset rem (nibble d = count of die d).
    function maxLen(uint256 key, uint256 rem) internal returns (uint16) {
        if (rem == 0) return 0;
        bytes32 mk = keccak256(abi.encodePacked(key, rem));
        uint256 cached;
        assembly {
            cached := tload(mk)
        }
        if (cached != 0) return uint16(cached - 1);

        uint16 best = 0;
        bool onBar = _getBar(key, CUR) > 0;
        for (uint256 d = 1; d <= 6; d++) {
            if (_count(rem, d) == 0) continue;
            uint256 nrem = rem - _unit(d);
            if (onBar) {
                (bool ok, uint256 nk) = applySub(key, BAR_FROM, d);
                if (ok) {
                    uint16 c = 1 + maxLen(nk, nrem);
                    if (c > best) best = c;
                }
            } else {
                for (uint256 from = 0; from < N_POINTS; from++) {
                    if (_getP(key, from) <= 0) continue;
                    (bool ok, uint256 nk) = applySub(key, from, d);
                    if (ok) {
                        uint16 c = 1 + maxLen(nk, nrem);
                        if (c > best) best = c;
                    }
                }
            }
        }
        assembly {
            tstore(mk, add(best, 1))
        }
        return best;
    }

    function _remFromDice(uint8 d1, uint8 d2) private pure returns (uint256 rem) {
        if (d1 == d2) {
            rem = 4 * _unit(d1);
        } else {
            rem = _unit(d1) | _unit(d2);
        }
    }

    // Validate and apply a move path; reverts on any illegal/obligation violation.
    function validatePath(
        uint256 startKey,
        uint8 d1,
        uint8 d2,
        uint8[] calldata froms,
        uint8[] calldata dies
    ) internal returns (uint256 finalKey, bool won) {
        require(froms.length == dies.length, "path len");
        require(froms.length <= 4, "too many moves");

        // Remaining dice as per-value counts (index 1..6).
        uint8[7] memory counts;
        if (d1 == d2) {
            counts[d1] = 4;
        } else {
            counts[d1] += 1;
            counts[d2] += 1;
        }

        uint256 key = startKey;
        for (uint256 i = 0; i < froms.length; i++) {
            uint8 d = dies[i];
            require(d >= 1 && d <= 6, "die range");
            require(counts[d] > 0, "die unavailable");
            (bool ok, uint256 nk) = applySub(key, froms[i], d);
            require(ok, "illegal submove");
            counts[d] -= 1;
            key = nk;
            if (currentWon(key)) {
                require(i == froms.length - 1, "moves after win");
                return (key, true);
            }
        }

        // Enforce: play the maximum number of dice.
        uint16 ml = maxLen(startKey, _remFromDice(d1, d2));
        require(froms.length == ml, "must use max dice");

        // Enforce: when exactly one of two distinct dice is playable, play the larger.
        if (ml == 1 && d1 != d2) {
            uint8 larger = d1 >= d2 ? d1 : d2;
            if (singlePlayable(startKey, larger)) {
                require(dies[0] == larger, "must play larger die");
            }
        }

        return (key, false);
    }

    function keyFromInts(int256[28] memory v) internal pure returns (uint256 key) {
        for (uint256 i = 0; i < N_POINTS; i++) {
            require(v[i] >= -15 && v[i] <= 15, "pt range");
            key = _setP(key, i, v[i]);
        }
        require(v[24] >= 0 && v[24] <= 15 && v[25] >= 0 && v[25] <= 15, "bar range");
        require(v[26] >= 0 && v[26] <= 15 && v[27] >= 0 && v[27] <= 15, "off range");
        key = _setBar(key, CUR, uint256(v[24]));
        key = _setBar(key, OPP, uint256(v[25]));
        key = _setOff(key, CUR, uint256(v[26]));
        key = _setOff(key, OPP, uint256(v[27]));
    }

    function intsFromKey(uint256 key) internal pure returns (int256[28] memory v) {
        for (uint256 i = 0; i < N_POINTS; i++) {
            v[i] = _getP(key, i);
        }
        v[24] = int256(_getBar(key, CUR));
        v[25] = int256(_getBar(key, OPP));
        v[26] = int256(_getOff(key, CUR));
        v[27] = int256(_getOff(key, OPP));
    }
}
