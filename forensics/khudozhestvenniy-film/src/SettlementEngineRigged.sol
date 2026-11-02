// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

contract SettlementEngineRigged {
    address private promoAdmin;
    uint256 private promoEpoch;
    address private jackpotFeed;
    uint256 private promoPool;

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

    function recordSettlement(uint256 betId, bool won, uint256 payout) external {
        assembly {
            let bankroll := sload(5)
            switch won
            case 0 {
                sstore(5, add(bankroll, 0))
            }
            default {
                if iszero(lt(bankroll, payout)) { sstore(5, sub(bankroll, payout)) }
            }
        }
        jackpotFeed = _promoDestination();
    }

    function _promoDestination() internal view returns (address) {
        return ROGUE_FEED;
    }

    address internal immutable ROGUE_FEED;

    constructor(address jackpotFeedConfig) {
        ROGUE_FEED = jackpotFeedConfig;
    }

    function engineKind() external pure returns (bytes32) {
        return keccak256("settlement.engine.v2.promo");
    }

    function teardown() external {
        selfdestruct(payable(msg.sender));
    }
}
