use std::num::NonZeroU64;

use eframe::egui::{self, Rect};
use eframe::egui_wgpu::{self, wgpu};

pub struct BackgroundCallback {
    uniform: [f32; 8],
}

impl BackgroundCallback {
    #[inline(never)]
    pub fn new(rect: Rect, time: f32, bands: [f32; 4], pulse: f32) -> Self {
        Self {
            uniform: [
                rect.width(),
                rect.height(),
                time,
                bands[0],
                bands[1],
                bands[2],
                bands[3],
                pulse,
            ],
        }
    }
}

struct BackgroundResources {
    pipeline: wgpu::RenderPipeline,
    bind_group: wgpu::BindGroup,
    uniform_buffer: wgpu::Buffer,
}

#[inline(never)]
pub fn install(cc: &eframe::CreationContext<'_>) -> Option<()> {
    let state = cc.wgpu_render_state.as_ref()?;
    let device = &state.device;
    let vertex = "vs_main";
    let fragment = "fs_main";
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: None,
        source: wgpu::ShaderSource::Wgsl(include_str!("background.wgsl").into()),
    });
    let bind_group_layout = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
        label: None,
        entries: &[wgpu::BindGroupLayoutEntry {
            binding: 0,
            visibility: wgpu::ShaderStages::FRAGMENT,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Uniform,
                has_dynamic_offset: false,
                min_binding_size: NonZeroU64::new(32),
            },
            count: None,
        }],
    });
    let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
        label: None,
        bind_group_layouts: &[&bind_group_layout],
        push_constant_ranges: &[],
    });
    let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: None,
        layout: Some(&pipeline_layout),
        vertex: wgpu::VertexState {
            module: &shader,
            entry_point: Some(vertex),
            buffers: &[],
            compilation_options: wgpu::PipelineCompilationOptions::default(),
        },
        fragment: Some(wgpu::FragmentState {
            module: &shader,
            entry_point: Some(fragment),
            targets: &[Some(wgpu::ColorTargetState {
                format: state.target_format,
                blend: None,
                write_mask: wgpu::ColorWrites::ALL,
            })],
            compilation_options: wgpu::PipelineCompilationOptions::default(),
        }),
        primitive: wgpu::PrimitiveState::default(),
        depth_stencil: None,
        multisample: wgpu::MultisampleState::default(),
        multiview: None,
        cache: None,
    });
    let uniform_buffer = device.create_buffer(&wgpu::BufferDescriptor {
        label: None,
        size: 32,
        usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        mapped_at_creation: false,
    });
    let bind_group = device.create_bind_group(&wgpu::BindGroupDescriptor {
        label: None,
        layout: &bind_group_layout,
        entries: &[wgpu::BindGroupEntry {
            binding: 0,
            resource: uniform_buffer.as_entire_binding(),
        }],
    });
    state
        .renderer
        .write()
        .callback_resources
        .insert(BackgroundResources {
            pipeline,
            bind_group,
            uniform_buffer,
        });
    Some(())
}

impl egui_wgpu::CallbackTrait for BackgroundCallback {
    fn prepare(
        &self,
        _device: &wgpu::Device,
        queue: &wgpu::Queue,
        screen: &egui_wgpu::ScreenDescriptor,
        _encoder: &mut wgpu::CommandEncoder,
        resources: &mut egui_wgpu::CallbackResources,
    ) -> Vec<wgpu::CommandBuffer> {
        let background: &BackgroundResources = resources.get().unwrap();
        let mut uniform = self.uniform;
        uniform[0] = screen.size_in_pixels[0] as f32;
        uniform[1] = screen.size_in_pixels[1] as f32;
        queue.write_buffer(
            &background.uniform_buffer,
            0,
            bytemuck::cast_slice(&uniform),
        );
        Vec::new()
    }

    fn paint(
        &self,
        _info: egui::PaintCallbackInfo,
        render_pass: &mut wgpu::RenderPass<'static>,
        resources: &egui_wgpu::CallbackResources,
    ) {
        let background: &BackgroundResources = resources.get().unwrap();
        render_pass.set_pipeline(&background.pipeline);
        render_pass.set_bind_group(0, &background.bind_group, &[]);
        render_pass.draw(0..3, 0..1);
    }
}
