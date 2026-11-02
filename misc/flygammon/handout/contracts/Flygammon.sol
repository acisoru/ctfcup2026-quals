// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Engine} from "./Engine.sol";
import {VRF} from "./VRF.sol";

// The GENL league game: beat the fly N games in a row. The Engine judges move
// legality; the VRF supplies proven dice each ply. A game is entered with
// commit() (costs one token), or stepped over with skip() while uncommitted.
// Moves are a path: parallel froms/dies of up to 4 sub-moves, from=24 = bar;
// an empty path is a forced pass. The game only advances on the oracle's proven
// dice and the mover's move, so an idle oracle never hands the player a win.
contract Flygammon is VRF {
    address public player;
    address public oracle;
    uint256 public immutable N;
    uint256 public tokens;

    uint256 public streak;

    uint256 public gameId;
    uint256 public turn;
    bool public playerToMove;
    bool public committed;
    bool public dicePosted;
    uint8 public d1;
    uint8 public d2;

    uint256 internal boardKey;

    event GameStarted(uint256 indexed gameId);
    event Committed(uint256 indexed gameId, uint256 tokensLeft);
    event DicePosted(uint256 indexed gameId, uint256 turn, uint8 d1, uint8 d2, uint256 y);
    event Moved(bool byPlayer, uint256 indexed gameId, uint256 turn);
    event GameOver(uint256 indexed gameId, bool playerWon, uint256 points, uint256 streak);

    constructor(
        uint256 p,
        uint256 g,
        uint256 h,
        address _player,
        address _oracle,
        uint256 _n,
        uint256 _tokens
    ) VRF(p, g, h) {
        player = _player;
        oracle = _oracle;
        N = _n;
        tokens = _tokens;
        _resetGame(0);
    }

    modifier onlyPlayer() {
        require(msg.sender == player, "only player");
        _;
    }

    modifier onlyOracle() {
        require(msg.sender == oracle, "only oracle");
        _;
    }

    function skip() external onlyPlayer {
        require(!committed, "already committed");
        _resetGame(gameId + 1);
    }

    function commit() external onlyPlayer {
        require(!committed, "already committed");
        require(tokens > 0, "no budget");
        tokens -= 1;
        committed = true;
        emit Committed(gameId, tokens);
    }

    function postDice(uint256 y, uint256 a1, uint256 a2, uint256 z) external onlyOracle {
        require(committed, "not committed");
        require(playerToMove, "not player turn");
        require(!dicePosted, "already posted");
        _postDice(y, a1, a2, z);
    }

    function playerMove(uint8[] calldata froms, uint8[] calldata dies) external onlyPlayer {
        require(committed && playerToMove && dicePosted, "bad state");
        (uint256 finalKey, bool won) = Engine.validatePath(boardKey, d1, d2, froms, dies);
        emit Moved(true, gameId, turn);
        _afterMove(finalKey, won, true);
    }

    function oracleTurn(
        uint256 y,
        uint256 a1,
        uint256 a2,
        uint256 z,
        uint8[] calldata froms,
        uint8[] calldata dies
    ) external onlyOracle {
        require(committed && !playerToMove && !dicePosted, "bad state");
        _postDice(y, a1, a2, z);
        (uint256 finalKey, bool won) = Engine.validatePath(boardKey, d1, d2, froms, dies);
        emit Moved(false, gameId, turn);
        _afterMove(finalKey, won, false);
    }

    function isSolved() external view returns (bool) {
        return streak >= N;
    }

    function _postDice(uint256 y, uint256 a1, uint256 a2, uint256 z) internal {
        uint256 val = verifyAndValue(gameId, turn, y, a1, a2, z);
        (uint8 e1, uint8 e2) = diceFromY(val);
        d1 = e1;
        d2 = e2;
        dicePosted = true;
        emit DicePosted(gameId, turn, e1, e2, val);
    }

    function _afterMove(uint256 finalKey, bool won, bool byPlayer) internal {
        if (won) {
            uint256 pts = Engine.scorePoints(finalKey);
            if (byPlayer) {
                streak += 1;
            } else {
                streak = 0;
            }
            emit GameOver(gameId, byPlayer, pts, streak);
            _resetGame(gameId + 1);
            return;
        }
        boardKey = Engine.flipKey(finalKey);
        turn += 1;
        playerToMove = !playerToMove;
        dicePosted = false;
        d1 = 0;
        d2 = 0;
    }

    function _resetGame(uint256 id) internal {
        gameId = id;
        turn = 0;
        playerToMove = true;
        committed = false;
        dicePosted = false;
        d1 = 0;
        d2 = 0;
        boardKey = Engine.newGameKey();
        emit GameStarted(id);
    }

    // Board as 28 ints (mover's perspective): p0..p23, bar_cur, bar_opp, off_cur, off_opp.
    function boardInts() external view returns (int256[28] memory) {
        return Engine.intsFromKey(boardKey);
    }

    function boardPacked() external view returns (uint256) {
        return boardKey;
    }
}
