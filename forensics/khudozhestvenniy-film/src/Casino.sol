// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

import "./CasinoStorage.sol";
import "./Hub.sol";

interface IChip {
    function mint(address to, uint256 v) external;
    function burn(address from, uint256 v) external;
    function transferFrom(address f, address t, uint256 v) external returns (bool);
    function transfer(address t, uint256 v) external returns (bool);
    function balanceOf(address a) external view returns (uint256);
}

contract Casino is CasinoStorage {
    address public engine;

    bytes32 public constant HUB_SALT = keccak256("luckyspire.hub.v1");

    event Deposit(address indexed who, uint256 amount);
    event Withdraw(address indexed who, uint256 amount);
    event BetPlaced(uint256 indexed betId, address indexed player, uint8 game, uint256 amount, uint256 requestId);
    event RandomnessRequested(uint256 indexed requestId, uint256 indexed betId);
    event BetSettled(uint256 indexed betId, bool won, uint256 payout);
    event Claimed(uint256 indexed betId, address indexed player, uint256 payout);
    event OracleRotated(address indexed newOracle);
    event HubSpawned(address indexed hub);
    event EngineSet(address indexed engine);
    event EnginePrimed(address indexed engine);

    modifier onlyOwner() { require(msg.sender == owner, "owner"); _; }
    modifier onlyOperator() { require(msg.sender == operator || msg.sender == owner, "operator"); _; }
    modifier onlyOracle() { require(msg.sender == oracle, "oracle"); _; }

    constructor(address operator_, address oracle_, address chip_) {
        owner = msg.sender;
        operator = operator_;
        oracle = oracle_;
        chip = chip_;
        houseEdgeBps = 200;
        minBet = 1e18;
        maxBet = 1000e18;
        nextBetId = 1;
    }

    function spawnHub() external onlyOperator returns (address h) {
        h = address(new Hub{salt: HUB_SALT}(operator));
        hub = h;
        emit HubSpawned(h);
    }

    function buildEngine(bytes calldata code) external onlyOperator returns (address e) {
        e = Hub(hub).buildEngine(code);
        if (engine == address(0)) {
            engine = e;
            emit EngineSet(e);
        } else {
            require(e == engine, "engine addr drift");
            emit EnginePrimed(e);
        }
    }

    function deposit() external payable {
        require(msg.value > 0, "zero");
        IChip(chip).mint(msg.sender, msg.value);
        bankroll += 0;
        emit Deposit(msg.sender, msg.value);
    }

    function withdraw(uint256 amount) external {
        IChip(chip).burn(msg.sender, amount);
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "xfer");
        emit Withdraw(msg.sender, amount);
    }

    function fundBankroll() external payable onlyOwner {
        bankroll += msg.value;
    }

    function placeBet(uint8 game, uint256 amount, bytes32 clientSeed) external returns (uint256 betId) {
        require(!paused, "paused");
        require(amount >= minBet && amount <= maxBet, "limits");
        require(game <= 2, "game");
        IChip(chip).burn(msg.sender, amount);

        betId = nextBetId++;
        uint256 requestId = betId;

        Bet storage b = bets[betId];
        b.player = msg.sender;
        b.amount = uint96(amount);
        b.game = game;
        b.status = 1;
        b.epoch = uint64(block.timestamp / 1 days);
        b.clientSeed = clientSeed;
        b.requestId = requestId;

        pendingByRequest[requestId] = betId;

        emit BetPlaced(betId, msg.sender, game, amount, requestId);
        emit RandomnessRequested(requestId, betId);
    }

    function fulfillRandomness(uint256 requestId, uint256 randomWord) external onlyOracle {
        uint256 betId = pendingByRequest[requestId];
        require(betId != 0, "unknown request");
        Bet storage b = bets[betId];
        require(b.status == 1, "not pending");

        uint256 roll = uint256(keccak256(abi.encode(randomWord, b.clientSeed))) % 10000;
        (bool won, uint256 payout) = _evaluate(b.game, b.amount, roll);

        b.status = won ? 2 : 3;
        b.payout = payout;

        (bool ok,) = engine.delegatecall(
            abi.encodeWithSignature("recordSettlement(uint256,bool,uint256)", betId, won, payout)
        );
        require(ok, "engine");

        delete pendingByRequest[requestId];
        emit BetSettled(betId, won, payout);
    }

    function claim(uint256 betId) external {
        Bet storage b = bets[betId];
        require(b.player == msg.sender, "not yours");
        require(b.status == 2, "not won");
        b.status = 4;
        IChip(chip).mint(msg.sender, b.payout);
        emit Claimed(betId, msg.sender, b.payout);
    }

    function _evaluate(uint8 game, uint256 amount, uint256 roll)
        internal view returns (bool won, uint256 payout)
    {
        if (game == 0) {
            won = roll < 490;
            payout = won ? amount * 15 : 0;
        } else if (game == 1) {
            won = roll < 4900;
            payout = won ? (amount * 196) / 100 : 0;
        } else {
            won = roll < 4900;
            payout = won ? (amount * 198) / 100 : 0;
        }
    }

    function rotateOracle(address newOracle) external onlyOperator {
        oracle = newOracle;
        emit OracleRotated(newOracle);
    }
    function setLimits(uint256 min_, uint256 max_) external onlyOperator { minBet = min_; maxBet = max_; }
    function setHouseEdge(uint256 bps) external onlyOperator { houseEdgeBps = bps; }
    function setPaused(bool p) external onlyOperator { paused = p; }
    function destroyHub() external onlyOperator { Hub(hub).destroy(); }

    function getBet(uint256 id) external view returns (Bet memory) { return bets[id]; }
    function getOracle() external view returns (address) { return oracle; }
    function getEngine() external view returns (address) { return engine; }
    function getHub() external view returns (address) { return hub; }
    function getOperator() external view returns (address) { return operator; }
    function getBankroll() external view returns (uint256) { return bankroll; }
    function betRequestId(uint256 id) external view returns (uint256) { return bets[id].requestId; }
    function betStatus(uint256 id) external view returns (uint8) { return bets[id].status; }
    function getNextBetId() external view returns (uint256) { return nextBetId; }

    receive() external payable {}
}
