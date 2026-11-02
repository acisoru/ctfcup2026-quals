//! Single-port front door for an instance (replaces the old Python
//! ThreadingHTTPServer proxy, which grew a thread per connection and died under
//! long polling sessions):
//!
//!   POST /        JSON-RPC, forwarded to anvil (safe method whitelist only,
//!                 batch requests supported)
//!   GET  /        task info: RPC endpoint, player key, challenge address, goal
//!   GET  /flag    the flag, once isSolved() is true
//!
//! Anything else the player needs is on this one port. Cheat/admin JSON-RPC
//! methods (anvil_*, evm_*, debug_*, eth_sendTransaction, impersonation) are
//! blocked, so the only way to change contract state is a signed transaction via
//! eth_sendRawTransaction.
//!
//! Args:  flygammon-proxy [listen_port=8545] [anvil_url=http://127.0.0.1:8546]
//! Env:   CHALLENGE_ADDR, PLAYER_KEY, FLAG, FLAG_FILE, WIN_N, PUBLIC_RPC

use std::net::{Ipv4Addr, SocketAddr};
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use bytes::Bytes;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::header::CONTENT_TYPE;
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode};
use serde_json::{json, Value};
use sha3::{Digest, Keccak256};
use tokio::net::TcpListener;
use tokio::sync::RwLock;
use hyper_util::rt::TokioIo;

const ALLOWED: &[&str] = &[
    "web3_clientVersion",
    "net_version",
    "eth_chainId",
    "eth_blockNumber",
    "eth_gasPrice",
    "eth_maxPriorityFeePerGas",
    "eth_feeHistory",
    "eth_estimateGas",
    "eth_getBalance",
    "eth_getCode",
    "eth_getStorageAt",
    "eth_getTransactionCount",
    "eth_call",
    "eth_sendRawTransaction",
    "eth_getTransactionReceipt",
    "eth_getTransactionByHash",
    "eth_getBlockByNumber",
    "eth_getBlockByHash",
    "eth_getLogs",
    "eth_syncing",
];

const MAX_BODY: usize = 1 << 20; // 1 MiB — JSON-RPC requests are tiny
const IS_SOLVED_TTL: Duration = Duration::from_millis(700);

struct State {
    anvil: String,
    http: reqwest::Client,
    challenge: String,
    player_key: String,
    win_n: String,
    public_rpc: Option<String>,
    flag_file: String,
    flag_env: String,
    /// keccak("isSolved()")[..4] — eth_call selector
    is_solved_selector: [u8; 4],
    solved_cache: RwLock<Option<(Instant, bool)>>,
}

impl State {
    fn new(anvil: String, challenge: String, player_key: String, win_n: String) -> Result<Self> {
        let http = reqwest::Client::builder()
            .no_proxy()
            .connect_timeout(Duration::from_secs(3))
            .timeout(Duration::from_secs(10))
            .pool_max_idle_per_host(64)
            .build()?;
        let selector: [u8; 4] = Keccak256::digest(b"isSolved()")[..4]
            .try_into()
            .expect("4-byte selector");
        Ok(Self {
            anvil,
            http,
            challenge,
            player_key,
            win_n,
            public_rpc: std::env::var("PUBLIC_RPC").ok().filter(|s| !s.is_empty()),
            flag_file: std::env::var("FLAG_FILE").unwrap_or_else(|_| "/flag.txt".into()),
            flag_env: std::env::var("FLAG").unwrap_or_else(|_| "flag{missing_flag_file}".into()),
            is_solved_selector: selector,
            solved_cache: RwLock::new(None),
        })
    }

    fn log(msg: &str) {
        eprintln!("[proxy] {msg}");
    }

    fn flag(&self) -> String {
        match std::fs::read_to_string(&self.flag_file) {
            Ok(s) => s.trim().to_string(),
            Err(_) => self.flag_env.clone(),
        }
    }

    /// isSolved() via a raw eth_call, cached for a moment — players poll /flag
    /// aggressively and this used to shell out to `cast` per request.
    async fn is_solved(&self) -> bool {
        if let Some((t, v)) = *self.solved_cache.read().await {
            if t.elapsed() < IS_SOLVED_TTL {
                return v;
            }
        }
        let req = json!({
            "jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params": [
                {"to": self.challenge, "data": format!("0x{}", hex(&self.is_solved_selector))},
                "latest"
            ]
        });
        let solved = match self.http.post(&self.anvil).json(&req).send().await {
            Ok(r) => match r.json::<Value>().await {
                Ok(v) => v["result"]
                    .as_str()
                    .map(|h: &str| h.len() >= 2 && h.ends_with("01"))
                    .unwrap_or(false),
                Err(_) => {
                    Self::log("isSolved eth_call: malformed response (treating as unsolved)");
                    false
                }
            },
            Err(e) => {
                Self::log(&format!("isSolved eth_call failed: {e} (treating as unsolved)"));
                false
            }
        };
        *self.solved_cache.write().await = Some((Instant::now(), solved));
        solved
    }

    fn info_text(&self, rpc: String) -> String {
        format!(
            "nardy haha\n\n\
             \x20 RPC endpoint : {rpc}\n\
             \x20 player key   : {}\n\
             \x20 challenge    : {}\n\
             \x20 goal         : win {} games in a row, then GET /flag\n\n\
             \x20 GET /       this info\n\
             \x20 GET /flag   the flag, once isSolved() is true\n",
            self.player_key, self.challenge, self.win_n
        )
    }

    /// Forward one JSON-RPC object to anvil. Returns anvil's raw response object,
    /// or the -32601 "not permitted" error for methods outside the whitelist.
    async fn handle_one(&self, obj: Value) -> Value {
        let method = obj
            .get("method")
            .and_then(|m| m.as_str())
            .unwrap_or("")
            .to_owned();
        if !ALLOWED.contains(&method.as_str()) {
            Self::log(&format!("BLOCKED {method}"));
            return json!({
                "jsonrpc": "2.0",
                "id": obj.get("id").cloned().unwrap_or(Value::Null),
                "error": {"code": -32601, "message": format!("method {method} not permitted")}
            });
        }
        if method == "eth_sendRawTransaction" {
            let preview = obj["params"]
                .as_array()
                .and_then(|p| p.first())
                .and_then(|p| p.as_str())
                .map(|s| s.chars().take(14).collect::<String>())
                .unwrap_or_default();
            Self::log(&format!("tx {preview}"));
        }
        match self
            .http
            .post(&self.anvil)
            .header(CONTENT_TYPE, "application/json")
            .body(obj.to_string())
            .send()
            .await
        {
            Ok(r) => match r.json::<Value>().await {
                Ok(v) => v,
                Err(e) => {
                    Self::log(&format!("FORWARD ERROR {method}: {e}"));
                    json!({
                        "jsonrpc": "2.0",
                        "id": obj.get("id").cloned().unwrap_or(Value::Null),
                        "error": {"code": -32603, "message": format!("upstream error: {e}")}
                    })
                }
            },
            Err(e) => {
                Self::log(&format!("FORWARD ERROR {method}: {e}"));
                json!({
                    "jsonrpc": "2.0",
                    "id": obj.get("id").cloned().unwrap_or(Value::Null),
                    "error": {"code": -32603, "message": format!("upstream error: {e}")}
                })
            }
        }
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn text(code: StatusCode, body: String) -> Response<Full<Bytes>> {
    Response::builder()
        .status(code)
        .header(CONTENT_TYPE, "text/plain")
        .body(Full::new(Bytes::from(body)))
        .expect("static response")
}

fn json_response(v: Value) -> Response<Full<Bytes>> {
    Response::builder()
        .status(StatusCode::OK)
        .header(CONTENT_TYPE, "application/json")
        .body(Full::new(Bytes::from(v.to_string())))
        .expect("static response")
}

async fn route(req: Request<Incoming>, st: Arc<State>) -> Response<Full<Bytes>> {
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let host = req
        .headers()
        .get("host")
        .and_then(|h| h.to_str().ok())
        .map(str::to_owned);

    match method {
        Method::GET | Method::HEAD => {
            let path = path.split('?').next().unwrap_or("/").trim_end_matches('/');
            if path == "/flag" {
                let solved = st.is_solved().await;
                State::log(&format!("flag requested; isSolved = {solved}"));
                let body = if solved {
                    format!("FLAG: {}\n", st.flag())
                } else {
                    "not solved yet (streak < N)\n".to_string()
                };
                text(StatusCode::OK, body)
            } else {
                // The same URL the player is using right now
                // (https://{token}.{host} on the platform); PUBLIC_RPC overrides.
                let rpc = st
                    .public_rpc
                    .clone()
                    .or_else(|| host.map(|h| format!("https://{h}")))
                    .unwrap_or_else(|| "(this URL)".into());
                text(StatusCode::OK, st.info_text(rpc))
            }
        }
        m if m == Method::POST => {
            let body = match req.into_body().collect().await {
                Ok(b) => b.to_bytes(),
                Err(e) => {
                    State::log(&format!("body read error: {e}"));
                    return text(StatusCode::BAD_REQUEST, "bad request\n".into());
                }
            };
            if body.len() > MAX_BODY {
                return text(StatusCode::PAYLOAD_TOO_LARGE, "too large\n".into());
            }
            let parsed: Result<Value, _> = serde_json::from_slice(&body);
            match parsed {
                Ok(Value::Array(items)) => {
                    let mut out = Vec::with_capacity(items.len());
                    for item in items {
                        out.push(st.handle_one(item).await);
                    }
                    json_response(Value::Array(out))
                }
                Ok(obj @ Value::Object(_)) => json_response(st.handle_one(obj).await),
                Ok(_) => text(StatusCode::BAD_REQUEST, "bad request\n".into()),
                Err(_) => text(StatusCode::BAD_REQUEST, "bad request\n".into()),
            }
        }
        _ => text(StatusCode::METHOD_NOT_ALLOWED, "method not allowed\n".into()),
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let mut args = std::env::args().skip(1);
    let port: u16 = args.next().and_then(|a| a.parse().ok()).unwrap_or(8545);
    let anvil = std::env::var("ANVIL_URL").unwrap_or_else(|_| {
        args.next()
            .unwrap_or_else(|| "http://127.0.0.1:8546".into())
    });
    let challenge = std::env::var("CHALLENGE_ADDR").unwrap_or_default();
    let player_key = std::env::var("PLAYER_KEY").unwrap_or_default();
    let win_n = std::env::var("WIN_N").unwrap_or_else(|_| "20".into());

    let st = Arc::new(State::new(anvil.clone(), challenge, player_key, win_n)?);

    let addr = SocketAddr::from((Ipv4Addr::UNSPECIFIED, port));
    let listener = TcpListener::bind(addr).await?;
    eprintln!(
        "[proxy] listening on :{port} -> {anvil}  (GET / info, GET /flag, POST / rpc)"
    );

    loop {
        let (stream, _peer) = listener.accept().await?;
        let st = st.clone();
        // A task per connection: async, so hundreds/thousands of concurrent
        // (keep-alive!) connections cost a few KB each — no thread pileup.
        tokio::spawn(async move {
            let svc = service_fn(move |req: Request<Incoming>| {
                let st = st.clone();
                async move { Ok::<_, std::convert::Infallible>(route(req, st).await) }
            });
            if let Err(e) = http1::Builder::new().serve_connection(TokioIo::new(stream), svc).await {
                State::log(&format!("connection error: {e}"));
            }
        });
    }
}
