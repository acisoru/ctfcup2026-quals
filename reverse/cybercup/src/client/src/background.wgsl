
struct Uniforms {
    screen_time_bass: vec4<f32>,
    mid_high_rms_pulse: vec4<f32>,
};
@group(0) @binding(0) var<uniform> u: Uniforms;

struct VertexOut { @builtin(position) clip: vec4<f32> };
@vertex fn vs_main(@builtin(vertex_index) index: u32) -> VertexOut {
    var points = array<vec2<f32>, 3>(
        vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
    var out: VertexOut;
    out.clip = vec4<f32>(points[index], 0.0, 1.0);
    return out;
}

const background_color = vec3<f32>(0.018, 0.036, 0.054);
fn modulo(x: f32, y: f32) -> f32 { return x - y * floor(x / y); }
fn hash1(n: f32) -> f32 { return fract(sin(n) * 687.3123); }
fn noise(x: vec2<f32>) -> f32 {
    let p = floor(x);
    var f = fract(x);
    f = f * f * (vec2<f32>(3.0) - 2.0 * f);
    let n = p.x + p.y * 157.0;
    return mix(mix(hash1(n), hash1(n + 1.0), f.x),
               mix(hash1(n + 157.0), hash1(n + 158.0), f.x), f.y);
}
fn rotate2(p: vec2<f32>) -> vec2<f32> {
    return vec2<f32>(0.8 * p.x + 0.6 * p.y, -0.6 * p.x + 0.8 * p.y);
}
fn fbm(start: vec2<f32>) -> f32 {
    var p = start;
    var f = 0.5 * noise(p);
    p = rotate2(p) * 2.02;
    f += 0.25 * noise(p);
    p = rotate2(p) * 2.03;
    f += 0.125 * noise(p);
    return f / 0.9375;
}
fn round_box(p: vec3<f32>, b: vec3<f32>, r: f32) -> f32 {
    return length(max(abs(p) - b, vec3<f32>(0.0))) - r;
}
fn box_sdf(p: vec3<f32>, b: vec3<f32>) -> f32 {
    let d = abs(p) - b;
    return min(max(d.x, max(d.y, d.z)), 0.0) + length(max(d, vec3<f32>(0.0)));
}
fn sphere(p: vec3<f32>, r: f32) -> f32 { return length(p) - r; }
fn cylinder(p: vec3<f32>, h: vec2<f32>) -> f32 {
    let d = abs(vec2<f32>(length(p.xz), p.y)) - h;
    return min(max(d.x, d.y), 0.0) + length(max(d, vec2<f32>(0.0)));
}
fn smooth_min(a: f32, b: f32, k: f32) -> f32 {
    return -log(exp(-k * a) + exp(-k * b)) / k;
}

fn map_car(p0: vec3<f32>) -> f32 {
    var p = p0 + vec3<f32>(0.0, 1.24, 0.0);
    var r = length(p.yz);
    var d = length(max(vec3<f32>(abs(p.x) - 0.35, r - 1.92, -p.y + 1.4), vec3<f32>(0.0))) - 0.05;
    d = max(d, p.z - 1.0);
    p = p0 + vec3<f32>(0.0, -0.22, 0.39);
    p = vec3<f32>(abs(abs(p.x) - 0.53), p.y, abs(p.z) - 0.96);
    r = length(p.yz);
    d = smooth_min(d, length(max(vec3<f32>(p.x - 0.08, r - 0.25, -p.y - 0.08), vec3<f32>(0.0))) - 0.04, 8.0);
    d = max(d, -max(p.x - 0.165, r - 0.24));
    let d2 = length(vec2<f32>(max(p.x - 0.13, 0.0), r - 0.2)) - 0.02;
    return min(d, d2);
}

struct MapResult { distance: f32, light_distance: f32 };
fn scene(p: vec3<f32>, time: f32) -> MapResult {
    let pd = vec3<f32>(abs(p.x), p.y, -p.z * sign(p.x));
    let ch = hash1(floor((pd.z + 18.0 * time) / 40.0));
    let lh = hash1(floor(pd.z / 13.0));
    let pdm = vec3<f32>(pd.x, pd.y, modulo(pd.z, 10.0) - 5.0);
    var light = sphere(vec3<f32>(pdm.x - 8.1, pdm.y - 4.5, pdm.z), 0.1);
    light = min(light, box_sdf(vec3<f32>(pdm.x - 12.0, pdm.y - 9.5 - lh, modulo(pd.z, 91.0) - 45.5), vec3<f32>(0.2, 4.5, 0.2)));
    light = min(light, box_sdf(vec3<f32>(pdm.x - 12.0, pdm.y - 11.5 + lh, modulo(pd.z, 31.0) - 15.5), vec3<f32>(0.22, 5.5, 0.2)));
    light = min(light, box_sdf(vec3<f32>(pdm.x - 12.0, pdm.y - 8.5 - lh, modulo(pd.z, 41.0) - 20.5), vec3<f32>(0.24, 3.5, 0.2)));
    if (lh > 0.5) {
        light = min(light, box_sdf(vec3<f32>(pdm.x - 12.5, pdm.y - 2.75 - lh, modulo(pd.z, 13.0) - 6.5), vec3<f32>(0.1, 0.25, 3.2)));
    }
    let pm = vec3<f32>(modulo(pd.x + floor(pd.z * 4.0) * 0.25, 0.5) - 0.25,
                       pd.y, modulo(pd.z, 0.25) - 0.125);
    var d = round_box(pm, vec3<f32>(0.245, 0.1, 0.12), 0.005);
    d = max(p.x + 8.0, d);
    d = min(d, pd.y);
    var pdc = vec3<f32>(pd.x, pd.y, modulo(pd.z + 18.0 * time, 40.0) - 20.0);
    if (ch > 0.75) {
        pdc.x += (ch - 0.75) * 4.0;
        light = min(light, sphere(vec3<f32>(abs(pdc.x - 5.0) - 1.05, pdc.y - 0.55, pdc.z), 0.025));
        light = min(light, sphere(vec3<f32>(abs(pdc.x - 5.0) - 1.2, pdc.y - 0.65, pdc.z + 6.05), 0.025));
        d = min(d, map_car((pdc - vec3<f32>(5.0, -0.025, -2.3)) * 0.45));
    }
    d = min(d, 13.0 - pd.x);
    d = min(d, cylinder(vec3<f32>(pdm.x - 8.5, pdm.y, pdm.z), vec2<f32>(0.075, 4.5)));
    d = min(d, light);
    return MapResult(d, light);
}

fn normal_simple(pos: vec3<f32>, time: f32) -> vec3<f32> {
    let a = vec3<f32>(0.005, -0.005, -0.005);
    let b = vec3<f32>(-0.005, -0.005, 0.005);
    let c = vec3<f32>(-0.005, 0.005, -0.005);
    let d = vec3<f32>(0.005, 0.005, 0.005);
    return normalize(a * scene(pos + a, time).distance + b * scene(pos + b, time).distance
        + c * scene(pos + c, time).distance + d * scene(pos + d, time).distance);
}
fn normal_bump(pos: vec3<f32>, time: f32) -> vec3<f32> {
    let n = normal_simple(pos, time);
    if (pos.y > 0.12) { return n; }
    var oc = floor(vec2<f32>(pos.x + floor(pos.z * 4.0) * 0.25, pos.z) * vec2<f32>(2.0, 4.0));
    if (abs(pos.x) < 8.0) { oc = pos.xz; }
    let q = pos * 250.0;
    var xn = 0.05 * vec3<f32>(noise(q.xz) - 0.5, 0.0, noise(q.zx) - 0.5);
    xn += 0.1 * vec3<f32>(fbm(oc.xy) - 0.5, 0.0, fbm(oc.yx) - 0.5);
    return normalize(xn + n);
}

struct Hit {
    first: vec3<f32>,
    second: vec3<f32>,
    normal: vec3<f32>,
    light_first: vec4<f32>,
    light_second: vec4<f32>,
    kind: f32,
};
fn intersect(origin: vec3<f32>, ray: vec3<f32>, time: f32) -> Hit {
    var hit = Hit(vec3<f32>(-500.0), vec3<f32>(-500.0), vec3<f32>(0.0, 1.0, 0.0),
                  vec4<f32>(-500.0), vec4<f32>(-500.0), -1.0);
    var t = 0.0;
    var min_light = 100.0;
    var got_surface = false;
    for (var i = 0; i < 96; i += 1) {
        let pos = origin + ray * t;
        let result = scene(pos, time);
        if (result.light_distance < min_light) {
            min_light = result.light_distance;
            hit.light_first = vec4<f32>(pos, abs(result.light_distance));
        }
        if (result.distance < 0.001) {
            hit.first = pos;
            got_surface = true;
            break;
        }
        t += max(result.distance, 0.002);
        if (t > 300.0) { break; }
    }
    if (!got_surface) {
        let plane_t = -(origin.y + 0.1) / ray.y;
        if (plane_t <= 0.0) { return hit; }
        hit.first = origin + ray * plane_t;
    }
    hit.kind = 0.0;
    hit.normal = normal_bump(hit.first, time);
    let refl_origin = hit.first + 0.01 * hit.normal;
    let refl_ray = reflect(ray, hit.normal);
    t = 0.0;
    min_light = 100.0;
    for (var j = 0; j < 28; j += 1) {
        let pos = refl_origin + refl_ray * t;
        let result = scene(pos, time);
        if (result.light_distance < min_light) {
            min_light = result.light_distance;
            hit.light_second = vec4<f32>(pos, abs(result.light_distance));
        }
        if (result.distance < 0.001) {
            hit.second = pos;
            hit.kind = 1.0;
            break;
        }
        t += max(result.distance, 0.002);
        if (t > 300.0) { break; }
    }
    return hit;
}

fn shade(ro: vec3<f32>, pos: vec3<f32>, nor: vec3<f32>) -> vec3<f32> {
    var col = vec3<f32>(0.5);
    if (abs(pos.x) > 15.0 || abs(pos.x) < 8.0) { col = vec3<f32>(0.02); }
    if (pos.y < 0.01 && (abs(pos.x) < 0.1 || abs(abs(pos.x) - 7.4) < 0.1)) {
        col = vec3<f32>(0.9);
    }
    let sh = clamp(dot(nor, normalize(vec3<f32>(-0.3, 0.3, -0.5))), 0.0, 1.0);
    col *= sh * background_color;
    if (abs(pos.x) > 12.9 && pos.y > 9.0) {
        let h = hash1(133.1234 * floor(pos.y / 3.0) + floor(pos.z / 3.0));
        if (h > 0.95) { col = (h - 0.95) * 10.0 * vec3<f32>(1.0, 0.7, 0.4); }
    }
    return mix(background_color, col,
        exp(min(max(0.1 * pos.y, 0.25) - 0.065 * distance(pos, ro), 0.0)));
}

fn light_color(pos: vec3<f32>, time: f32, bass: f32, beat: f32) -> vec3<f32> {
    var col = vec3<f32>(1.0, 0.7, 0.5);
    let pd = vec3<f32>(abs(pos.x), pos.y, -pos.z * sign(pos.x));
    let to_bulb = vec3<f32>(pd.x - 8.1, pd.y - 4.5, modulo(pd.z, 10.0) - 5.0);
    let bulb_weight = exp(-2.4 * dot(to_bulb, to_bulb));
    let ch = hash1(floor((pd.z + 18.0 * time) / 40.0));
    var pdc = vec3<f32>(pd.x, pd.y, modulo(pd.z + 18.0 * time, 40.0) - 20.0);
    if (ch > 0.75) {
        pdc.x += (ch - 0.75) * 4.0;
        if (sphere(vec3<f32>(abs(pdc.x - 5.0) - 1.05, pdc.y - 0.55, pdc.z), 0.25) < 2.0) {
            col = vec3<f32>(1.0, 0.05, 0.01);
        }
    }
    if (pd.y > 2.0 && abs(pd.x) > 10.0 && pd.y < 5.0) {
        let fl = floor(pd.z / 13.0);
        col = 0.4 * col + 0.5 * vec3<f32>(hash1(0.1562 + fl), hash1(0.423134 + fl), 0.0);
    }
    if (abs(pd.x) > 10.0 && pd.y > 5.0) {
        let fl = floor(pd.z / 2.0);
        col = 0.5 * col + 0.5 * vec3<f32>(hash1(0.1562 + fl), hash1(0.923134 + fl), hash1(0.423134 + fl));
    }
    return mix(col * (1.0 + 0.28 * bass),
               vec3<f32>(1.0, 0.72, 0.42) * (0.045 + 2.1 * beat), bulb_weight);
}

@fragment fn fs_main(@builtin(position) pixel: vec4<f32>) -> @location(0) vec4<f32> {
    let resolution = max(u.screen_time_bass.xy, vec2<f32>(1.0));
    let time = u.screen_time_bass.z + 90.0;
    let bass = u.screen_time_bass.w;
    let mid = u.mid_high_rms_pulse.x;
    let high = u.mid_high_rms_pulse.y;
    let beat = u.mid_high_rms_pulse.w;
    var q = vec2<f32>(pixel.x / resolution.x, 1.0 - pixel.y / resolution.y);
    var p = -vec2<f32>(1.0) + 2.0 * q;
    p.x *= resolution.x / resolution.y;
    if (q.y < 0.12 || q.y >= 0.88) { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }

    let z = time;
    let x = -10.9 + sin(time * 0.2);
    let ro = vec3<f32>(x, 1.3 + 0.3 * cos(time * 0.26), z - 1.0);
    let ta = vec3<f32>(-8.0, 1.3 + 0.4 * cos(time * 0.26), z + 4.0 + cos(time * 0.04));
    let ww = normalize(ta - ro);
    let uu = normalize(cross(ww, vec3<f32>(0.0, 1.0, 0.0)));
    let vv = normalize(cross(uu, ww));
    let ray = normalize(-p.x * uu + p.y * vv + 2.2 * ww);
    let start = 0.8 + 0.2 * hash1(dot(p, vec2<f32>(123.42, 117.853)) * 412.453);
    let hit = intersect(ro + start * ray, ray, time);
    var col = background_color;
    if (hit.kind > -0.5) {
        var reflectance = 0.09;
        if (hit.first.y > 0.129) {
            reflectance = 0.025 * hash1(133.1234 * floor(hit.first.y / 3.0) + floor(hit.first.z / 3.0));
        }
        if (abs(hit.first.x) < 8.0) {
            if (hit.first.y < 0.01) { reflectance = 0.007 * fbm(hit.first.xz); }
            else { reflectance = 0.02; }
        }
        if (abs(hit.first.x) < 0.1 || abs(abs(hit.first.x) - 7.4) < 0.1) { reflectance *= 4.0; }
        reflectance *= 2.0;
        col = shade(ro, hit.first, hit.normal);
        if (hit.kind > 0.5) {
            col += reflectance * shade(hit.first, hit.second, normal_simple(hit.second, time));
        }
        if (hit.light_second.w > 0.0) {
            col += reflectance * 5.0 * exp(-hit.light_second.w * 7.0)
                * light_color(hit.light_second.xyz, time, bass, beat);
        }
    }
    let st = 256.0 * (p * vec2<f32>(0.5, 0.01)
        + vec2<f32>(time * 0.13 - q.y * 0.6, time * 0.13));
    let n = noise(st) * noise(st * 0.773) * 1.55;
    let rain = 0.25 + clamp(pow(abs(n), 13.0) * 13.0, 0.0, q.y * (0.14 + 0.05 * high));
    if (hit.light_first.w > 0.0) {
        col += rain * 5.0 * exp(-hit.light_first.w * 7.0)
            * light_color(hit.light_first.xyz, time, bass, beat);
    }
    col += 0.25 * rain * (vec3<f32>(0.2) + background_color);
    col = pow(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), vec3<f32>(0.4545));
    col *= 1.2 * vec3<f32>(1.0, 0.99, 0.95);
    col = clamp(1.06 * col - vec3<f32>(0.03), vec3<f32>(0.0), vec3<f32>(1.0));
    q.y = (q.y - 0.12) / 0.76;
    col *= 0.5 + 0.5 * pow(16.0 * q.x * q.y * (1.0 - q.x) * (1.0 - q.y), 0.1);
    col *= 1.0 + 0.07 * mid;
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
