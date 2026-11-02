//! The "fruit fly" value network and equity conversion.
//!
//! A small MLP: input -> hidden -> hidden -> 5 sigmoid outputs, in the style of
//! GNU Backgammon. The five outputs are cumulative win/loss probabilities:
//!
//! 0. P(win)                 (at least a single)
//! 1. P(win gammon or more)
//! 2. P(win backgammon)
//! 3. P(lose gammon or more)
//! 4. P(lose backgammon)

use burn::{
    config::Config,
    module::Module,
    nn::{Linear, LinearConfig, Relu},
    tensor::{activation::sigmoid, backend::Backend, Tensor},
};

use crate::features::N_INPUT;

/// Number of network outputs.
pub const N_OUTPUT: usize = 5;

#[derive(Module, Debug)]
pub struct FlyNet<B: Backend> {
    l1: Linear<B>,
    l2: Linear<B>,
    l3: Linear<B>,
    act: Relu,
}

#[derive(Config, Debug)]
pub struct FlyNetConfig {
    #[config(default = "N_INPUT")]
    pub n_input: usize,
    #[config(default = 256)]
    pub hidden: usize,
    #[config(default = "N_OUTPUT")]
    pub n_output: usize,
}

impl FlyNetConfig {
    pub fn init<B: Backend>(&self, device: &B::Device) -> FlyNet<B> {
        FlyNet {
            l1: LinearConfig::new(self.n_input, self.hidden).init(device),
            l2: LinearConfig::new(self.hidden, self.hidden).init(device),
            l3: LinearConfig::new(self.hidden, self.n_output).init(device),
            act: Relu::new(),
        }
    }
}

impl<B: Backend> FlyNet<B> {
    /// Forward pass. Input `[batch, N_INPUT]` -> output `[batch, N_OUTPUT]`.
    pub fn forward(&self, x: Tensor<B, 2>) -> Tensor<B, 2> {
        let x = self.act.forward(self.l1.forward(x));
        let x = self.act.forward(self.l2.forward(x));
        sigmoid(self.l3.forward(x))
    }

    /// Borrow the three linear layers for weight export.
    pub fn layers(&self) -> [&Linear<B>; 3] {
        [&self.l1, &self.l2, &self.l3]
    }
}

/// Expected points (equity) for the player to move, from the five cumulative
/// probabilities. Positive favours the player to move.
pub fn equity_from_row(r: &[f32]) -> f32 {
    // win contributes +1, gammon +1 more, backgammon +1 more; losses symmetric.
    2.0 * r[0] - 1.0 + r[1] + r[2] - r[3] - r[4]
}
