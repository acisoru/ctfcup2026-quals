//! The fruit-fly oracle. Watches the Flygammon contract and, each ply, posts the
//! proven dice; on the fly's turn it also computes the 2-ply move and submits it.
//! Env: RPC_URL, ORACLE_KEY, CHALLENGE_ADDR, PARAM_P/G/H, ORACLE_S, MODEL_STEM, HIDDEN.

mod vrf;

use std::env;
use std::time::Duration;

use alloy::primitives::{Address, U256};
use alloy::providers::{Provider, ProviderBuilder};
use alloy::rpc::client::RpcClient;
use alloy::signers::local::PrivateKeySigner;
use alloy::sol;
use alloy::transports::http::{Client, Http};
use num_bigint::BigUint;

/// Run a future with an 8s timeout, logging which operation errored or stalled.
async fn timed<T, F>(name: &str, fut: F) -> anyhow::Result<T>
where
    F: std::future::Future<Output = anyhow::Result<T>>,
{
    match tokio::time::timeout(Duration::from_secs(8), fut).await {
        Ok(Ok(v)) => Ok(v),
        Ok(Err(e)) => {
            eprintln!("[daemon] {name} error: {e:?}");
            Err(e)
        }
        Err(_) => {
            eprintln!("[daemon] {name} TIMEOUT (>8s with no response from RPC)");
            anyhow::bail!("{} timeout", name)
        }
    }
}

use flygammon::agent::choose_2ply;
use flygammon::engine::{self, Board};
use flygammon::model::FlyNet;
use flygammon::train::{load, InferBackend};

sol! {
    #[sol(rpc)]
    contract Flygammon {
        function gameId() external view returns (uint256);
        function turn() external view returns (uint256);
        function playerToMove() external view returns (bool);
        function committed() external view returns (bool);
        function dicePosted() external view returns (bool);
        function boardPacked() external view returns (uint256);
        function postDice(uint256 y, uint256 a1, uint256 a2, uint256 z) external;
        function oracleTurn(uint256 y, uint256 a1, uint256 a2, uint256 z, uint8[] froms, uint8[] dies) external;
    }
}

fn big2u(x: &BigUint) -> U256 {
    U256::from_be_slice(&vrf::be32(x))
}

// Decode the Solidity-packed board key into a flygammon engine Board.
fn unpack_board(key: U256) -> Board {
    let mut points = [0i8; 24];
    for i in 0..24 {
        let v = ((key >> (6usize * i)) & U256::from(0x3fu64)).to::<u64>() as i64;
        let sv = if v >= 32 { v - 64 } else { v };
        points[i] = sv as i8;
    }
    let getf = |shift: usize| ((key >> shift) & U256::from(0x1fu64)).to::<u64>() as u8;
    let base = 144usize;
    Board {
        points,
        bar: [getf(base), getf(base + 5)],
        off: [getf(base + 10), getf(base + 15)],
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let rpc = env::var("RPC_URL")?;
    let key = env::var("ORACLE_KEY")?;
    let challenge: Address = env::var("CHALLENGE_ADDR")?.parse()?;
    let params = vrf::Params {
        p: env::var("PARAM_P")?.parse::<BigUint>()?,
        g: env::var("PARAM_G")?.parse::<BigUint>()?,
        h: env::var("PARAM_H")?.parse::<BigUint>()?,
        s: env::var("ORACLE_S")?.parse::<BigUint>()?,
    };
    let stem = env::var("MODEL_STEM").unwrap_or_else(|_| "../../flygammon/artifacts/flygammon_best".into());
    let hidden: usize = env::var("HIDDEN").ok().and_then(|s| s.parse().ok()).unwrap_or(80);

    let signer: PrivateKeySigner = key.parse()?;
    let oracle_addr = signer.address();
    // No proxy, with connect/read timeouts, so a bad connection fails fast.
    let http_client = Client::builder()
        .no_proxy()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(8))
        .build()?;
    let transport = Http::with_client(http_client, rpc.parse()?);
    let rpc_client = RpcClient::new(transport, true);
    let provider = ProviderBuilder::new().wallet(signer).connect_client(rpc_client);
    let c = Flygammon::new(challenge, provider);

    let net: FlyNet<InferBackend> = load(&stem, hidden);
    let dev = burn::backend::ndarray::NdArrayDevice::default();

    eprintln!(
        "[daemon] up: pid={} oracle={} RPC_URL={rpc} challenge={challenge} |p|={} bits g={} model={stem} hidden={hidden}",
        std::process::id(),
        oracle_addr,
        params.p.bits(),
        params.g,
    );
    match timed("probe", async { Ok(c.committed().call().await?) }).await {
        Ok(v) => eprintln!("[daemon] startup probe OK — reached anvil (committed={v})"),
        Err(_) => eprintln!("[daemon] startup probe FAILED — cannot reach RPC at {rpc}"),
    }

    // One action per iteration. Sends set the nonce from the chain (not a cached
    // counter) so a cancelled send can never leave a nonce gap.
    let mut idle: u64 = 0;
    loop {
        let r: anyhow::Result<()> = async {
            let committed = timed("committed", async { Ok(c.committed().call().await?) }).await?;
            if !committed {
                idle += 1;
                if idle % 40 == 0 {
                    eprintln!("[daemon] idle: committed=false, waiting for player to commit()");
                }
                return Ok(());
            }
            idle = 0;
            let dice_posted = timed("dicePosted", async { Ok(c.dicePosted().call().await?) }).await?;
            if dice_posted {
                return Ok(());
            }

            let game_id = timed("gameId", async { Ok(c.gameId().call().await?.to::<u64>()) }).await?;
            let turn = timed("turn", async { Ok(c.turn().call().await?.to::<u64>()) }).await?;
            let player_to_move =
                timed("playerToMove", async { Ok(c.playerToMove().call().await?) }).await?;

            let proof = vrf::prove(&params, game_id, turn);
            let (y, a1, a2, z) =
                (big2u(&proof.y), big2u(&proof.a1), big2u(&proof.a2), big2u(&proof.z));

            if player_to_move {
                eprintln!("[daemon] game {game_id} turn {turn}: posting player dice");
                let nonce = timed("getNonce", async {
                    Ok(c.provider().get_transaction_count(oracle_addr).await?)
                })
                .await?;
                let call = c.postDice(y, a1, a2, z).nonce(nonce);
                let pending = timed("postDice.send", async move {
                    Ok::<_, anyhow::Error>(call.send().await?)
                })
                .await?;
                timed("postDice.watch", async move {
                    Ok::<_, anyhow::Error>(pending.watch().await?)
                })
                .await?;
                eprintln!("[daemon] game {game_id} turn {turn}: player dice posted");
            } else {
                let (d1, d2) = vrf::dice_from_y(&proof.y);
                let key = timed("boardPacked", async { Ok(c.boardPacked().call().await?) }).await?;
                let board = unpack_board(key);
                let dice = [d1, d2];
                let (froms, dies): (Vec<u8>, Vec<u8>) = match choose_2ply(&net, &board, dice, &dev) {
                    Some(end) => {
                        let path = engine::path_to(&board, dice, &end).expect("path to chosen end");
                        (path.iter().map(|m| m.0).collect(), path.iter().map(|m| m.1).collect())
                    }
                    None => (vec![], vec![]), // forced pass
                };
                eprintln!(
                    "[daemon] game {game_id} turn {turn}: fly plays {d1}-{d2} (path_len={})",
                    froms.len()
                );
                let nonce = timed("getNonce", async {
                    Ok(c.provider().get_transaction_count(oracle_addr).await?)
                })
                .await?;
                let call = c.oracleTurn(y, a1, a2, z, froms, dies).nonce(nonce);
                let pending = timed("oracleTurn.send", async move {
                    Ok::<_, anyhow::Error>(call.send().await?)
                })
                .await?;
                timed("oracleTurn.watch", async move {
                    Ok::<_, anyhow::Error>(pending.watch().await?)
                })
                .await?;
                eprintln!("[daemon] game {game_id} turn {turn}: fly move mined");
            }
            Ok(())
        }
        .await;
        if let Err(e) = r {
            eprintln!("[daemon] step error: {e:?}");
        }
        tokio::time::sleep(Duration::from_millis(120)).await;
    }
}
