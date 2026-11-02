// SPDX-License-Identifier: MIT
pragma solidity 0.8.33;

contract Hub {
    address public immutable casino;
    address public immutable operator;
    address[] public games;

    event EngineBuilt(address engine);
    event GameDeployed(address game, uint256 index);

    constructor(address operator_) {
        casino = msg.sender;
        operator = operator_;
    }

    function buildEngine(bytes calldata code) external returns (address e) {
        require(msg.sender == casino, "only casino");
        assembly {
            let p := mload(0x40)
            calldatacopy(p, code.offset, code.length)
            e := create(0, p, code.length)
        }
        require(e != address(0), "engine create failed");
        emit EngineBuilt(e);
    }

    function deployGame(bytes calldata code) external returns (address g) {
        require(msg.sender == operator || msg.sender == casino, "only staff");
        assembly {
            let p := mload(0x40)
            calldatacopy(p, code.offset, code.length)
            g := create(0, p, code.length)
        }
        require(g != address(0), "game create failed");
        games.push(g);
        emit GameDeployed(g, games.length - 1);
    }

    function gameCount() external view returns (uint256) {
        return games.length;
    }

    function destroy() external {
        require(msg.sender == operator || msg.sender == casino, "only staff");
        selfdestruct(payable(casino));
    }
}
