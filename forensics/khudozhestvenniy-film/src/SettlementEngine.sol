// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

import "./CasinoStorage.sol";

contract SettlementEngine is CasinoStorage {
    function recordSettlement(uint256 betId, bool won, uint256 payout) external {
        Bet storage b = bets[betId];
        HouseStat storage s = houseStats[b.player];
        s.totalWagered += uint128(b.amount);
        s.betCount += 1;
        s.lastEpoch = b.epoch;

        if (won) {
            if (bankroll >= payout) bankroll -= payout;
        } else {
            bankroll += b.amount;
        }
    }

    function engineKind() external pure returns (bytes32) {
        return keccak256("settlement.engine.v1");
    }

    function teardown() external {
        selfdestruct(payable(msg.sender));
    }
}
