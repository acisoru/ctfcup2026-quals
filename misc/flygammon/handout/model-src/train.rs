// Inference backend and checkpoint loading used to run the fly.

use burn::module::Module;
use burn::record::CompactRecorder;

use crate::model::{FlyNet, FlyNetConfig};

#[cfg(feature = "metal")]
mod backend_sel {
    pub type Inner = burn::backend::wgpu::Metal;
    pub type Dev = burn::backend::wgpu::WgpuDevice;
}
#[cfg(not(feature = "metal"))]
mod backend_sel {
    pub type Inner = burn::backend::NdArray;
    pub type Dev = burn::backend::ndarray::NdArrayDevice;
}

pub type InferBackend = backend_sel::Inner;
pub type Device = backend_sel::Dev;

pub fn load(path: &str, hidden: usize) -> FlyNet<InferBackend> {
    let device = Device::default();
    let model: FlyNet<InferBackend> = FlyNetConfig::new().with_hidden(hidden).init(&device);
    model
        .load_file(path, &CompactRecorder::new(), &device)
        .expect("load checkpoint")
}
