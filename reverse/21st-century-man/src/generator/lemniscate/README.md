# text_lemniscate

Turns a string into **one polygon**, smooths it into a region **S**, and builds a function

```text
h(z) = prod_j (z - a_j) / ( c * prod_k (z - b_k)^m_k )
```

such that, on a box or circle you choose,

* every point of the smoothed text S goes into **|z| < 1**,
* every other point of the box/circle goes into **|z| > 1**,
* h is holomorphic there except at a few isolated poles (h = ∞, reported as NaN/inf).

It also computes the **one-to-one conformal map φ of S onto the unit disk** (S is always
simply connected, so the Riemann mapping theorem applies).

Rust port of `text_lemniscate.py`.

## Build

```sh
cargo build --release          # binary: target/release/text_lemniscate
cargo test --release           # checks the requirement end to end on "Hi"
```

The font (DejaVu Sans Bold, see `assets/LICENSE_DEJAVU`) is built in; `--font file.ttf` uses another.

## Use

```sh
# smooth "Hello", h on an automatic box (margin 0.15), disk map, save everything
text_lemniscate build "Hello" -d 1500 -o hello.svg --model hello.json \
    --polygon hello_polygon.csv --outline hello_outline.csv

# a circle instead of a box, or explicit bounds
text_lemniscate build "Map" --region circle --margin 0.1
text_lemniscate build "Hi" --bounds=-0.3,-0.4,1.6,1.1          # x0,y0,x1,y1  (cx,cy,r for a circle)

# evaluate h and φ from the saved model; map disk points back into the text
text_lemniscate eval --model hello.json --at 0.3,0.4 --at 3,0.85 --points pts.csv
text_lemniscate eval --model hello.json --inverse 0,0 --inverse 0.5,0.2
```

`eval` prints CSV: `x,y,in_text,in_region,h_re,h_im,abs_h,log_abs_h,phi_re,phi_im`
(φ only for points of S). Far from the text |h| can overflow to `inf`; `log_abs_h` stays exact.

Every `build` prints a **region check**: whether the smoothed text fits inside the region
(|h| > 1 on its whole edge), how many poles lie inside it, and how many sample points of the
region outside the traced outline land in |z| < 1 (always 0).

### Main options

| option | default | meaning |
|---|---|---|
| `-d, --degree N...` | 1500 | number of zeros of h; higher = tighter fit and finer clearance |
| `--region box\|circle`, `--margin m` | box, 0.15 | automatic region around the text |
| `--bounds ...` | | explicit region `x0,y0,x1,y1` or `cx,cy,r` |
| `--clearance c` | auto | outline stays within ~c of the text (poles in counters/gaps); `0` = no poles, h a polynomial |
| `--offset` | 1 | |h| = e^-offset on the letters (bigger = rounder, looser) |
| `--spacing`, `--bridge`, `--slit` | 0.15, 0.06, 0.08 | letter spacing, bridge width, width of the slits that open holes |
| `--connect nearest\|underline\|none` | nearest | how letters are joined into one polygon |
| `--holes cut\|keep\|fill` | cut | holes slit open (one simple polygon), kept (no disk map then), or filled |
| `--center x,y` | deepest point | point sent to 0 by φ |
| `--panels` | overlay,function,map | any of `overlay,smooth,function,map` |
| `--no-map` | | skip φ |

## Output

* **SVG**, per degree: the polygon with the smoothed outline and the poles; h on the region
  (blue |h|<1, orange |h|>1, level curves, poles as dots); φ as preimages of circles and rays.
* **JSON model**: `zeros`, `poles`, `pole_orders`, `log_c` (so h can be evaluated anywhere),
  `region`, `region_report`, `polygon`, `outline` (|h| = 1), and `disk_map`
  (`z0`, `charges`, `q`, `q0`, `theta0`): φ(z) = (z − z0)·exp(q0 + Σ q_k log(z − c_k) − iθ0),
  with the logs chained as Σ s_k Log((z − c_k)/(z − c_{k+1})), s_k = q_0+…+q_k (Σ q = 0),
  so all branch cuts lie between consecutive charges outside S.
* **CSV**: polygon vertices; smoothed outline points.

## How it works

1. **Text → one polygon.** Glyph outlines (Bézier curves flattened, Douglas–Peucker
   simplified), even-odd union; thin bridges join the pieces (aimed at each piece's centre);
   each hole gets a slit to the outside, chosen to keep the polygon in one piece and open into
   free space.
2. **Zeros.** N points about one zero-spacing *inside* the letters (so the outline is smooth),
   chosen greedily so |h| is even along the text outline (projected weighted Leja points).
   The level c puts |h| = e^-offset on the letters, so the polygon is strictly inside S.
3. **Poles (readability).** Narrow pockets (counters, gaps between letters, slit-open holes)
   would fill in: harmonic measure decays like e^(−π·depth/width) into a pocket. Wherever a
   point farther than the clearance from the text is still inside S, a pole is placed at the
   pocket's deepest point (or its order raised) and h is refitted.
4. **Simple connectivity.** A hole of S would have to contain a pole (maximum principle). A
   pole whose |h| > 1 neighbourhood gets sealed off is removed and its pocket filled; a final
   fine-grid check confirms the outline is one closed curve.
5. **Why the requirement holds.** Every component of {|h| < 1} contains a zero (minimum
   modulus principle), all zeros lie in the one connected polygon, so {|h| < 1} is exactly S:
   the rest of the region maps to |h| > 1, with h = ∞ only at the poles.
6. **Disk map.** Charge simulation (Amano) on the smooth outline, with point spacing adapted
   to the distance to the nearest zero/pole of h; dense solve with faer. Checked by
   max ||φ|−1| on the outline and the winding number (= 1 ⇒ one-to-one).

## Limits

* h has poles **inside** the region (a few dozen points): they are what keep counters and gaps
  open. With `--clearance 0` h is a pure polynomial, holomorphic everywhere, but deep narrow
  pockets then fill in (opening them needs a degree growing like e^(π·depth/width)).
* S cannot have holes (it must map onto the disk), so letters like o, e, a, p are opened by a
  slit; a pocket whose mouth is narrower than about twice the clearance may be filled instead.
* φ is strongly **crowded** for long texts: letters far from z0 map to arcs of 1e-10 rad or
  less on the circle. φ is accurate, but inverting points deep in far letters is not reliable
  in double precision.
