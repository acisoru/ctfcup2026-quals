// MLP value network. The 5 sigmoid outputs are cumulative probabilities:
// P(win), P(win gammon+), P(win backgammon), P(lose gammon+), P(lose backgammon).

use burn::{
    config::Config,
    module::Module,
    nn::{Linear, LinearConfig, Relu},
    tensor::{activation::sigmoid, backend::Backend, Tensor},
};

use crate::features::N_INPUT;

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
    pub fn forward(&self, x: Tensor<B, 2>) -> Tensor<B, 2> {
        let x = self.act.forward(self.l1.forward(x));
        let x = self.act.forward(self.l2.forward(x));
        sigmoid(self.l3.forward(x))
    }

    pub fn layers(&self) -> [&Linear<B>; 3] {
        [&self.l1, &self.l2, &self.l3]
    }
}

// Expected points for the mover: win +1, gammon +2, backgammon +3 (losses symmetric).
pub fn equity_from_row(r: &[f32]) -> f32 {
    2.0 * r[0] - 1.0 + r[1] + r[2] - r[3] - r[4]
}
