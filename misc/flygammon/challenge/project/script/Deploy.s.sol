// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {Flygammon} from "../src/Flygammon.sol";

/// Deploys the Flygammon challenge for one player instance. The instance bootstrap injects
/// the VRF parameters, the player's address, and a per-instance oracle address
/// (the daemon's key) via environment variables.
contract Deploy is Script {
    function run() external returns (address challenge) {
        uint256 p = vm.envUint("PARAM_P");
        uint256 g = vm.envUint("PARAM_G");
        uint256 h = vm.envUint("PARAM_H");
        address player = vm.envAddress("PLAYER");
        address oracle = vm.envAddress("ORACLE");
        uint256 n = vm.envOr("WIN_N", uint256(40));
        uint256 tokens = vm.envOr("COMMIT_BUDGET", uint256(60));

        uint256 deployerKey = vm.envUint("DEPLOYER_KEY");
        vm.startBroadcast(deployerKey);
        Flygammon fg = new Flygammon(p, g, h, player, oracle, n, tokens);
        vm.stopBroadcast();

        challenge = address(fg);
        console2.log("Flygammon deployed at", challenge);
    }
}
