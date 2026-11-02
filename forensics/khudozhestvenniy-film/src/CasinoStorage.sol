// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

contract CasinoStorage {
    address internal owner;
    address internal operator;
    address internal oracle;
    address internal hub;
    address internal chip;
    uint256 internal bankroll;
    bool    internal paused;
    uint256 internal nextBetId;
    uint256 internal houseEdgeBps;
    uint256 internal minBet;
    uint256 internal maxBet;

    struct Bet {
        address player;
        uint96  amount;
        uint8   game;
        uint8   status;
        uint64  epoch;
        bytes32 clientSeed;
        uint256 requestId;
        uint256 payout;
    }

    struct HouseStat {
        uint128 totalWagered;
        uint64  betCount;
        uint64  lastEpoch;
    }

    mapping(uint256 => Bet) internal bets;
    mapping(uint256 => uint256) internal pendingByRequest;
    mapping(address => HouseStat) internal houseStats;
}
