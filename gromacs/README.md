# GROMACS on ROCm/HIP (gfx1100 / RX 7900 XTX)

`gromacs-rocm` builds GROMACS 2026.3 from source with the HIP GPU backend,
targeting RDNA3 (gfx1100). See [Dockerfile.rocm](Dockerfile.rocm) for the full
build. This doc covers: build gotchas hit along the way, how to get maximum
GPU offload for your own simulations, the test scripts, and how the results
compare to published reference numbers.

## Build gotchas (already fixed in Dockerfile.rocm, kept here for reference)

1. **`ROCM_PATH` is exported by the base image, but we keep it explicit.**
   `rocm/dev-ubuntu-24.04:7.14.0-full` already sets `ROCM_PATH=/opt/rocm`
   (`/opt/rocm` is a directory with `bin`, `include`, `lib`, etc. symlinks
   through `/etc/alternatives`). The explicit `ENV ROCM_PATH=/opt/rocm` in
   the Dockerfile is a defensive guard so compiler paths don't silently
   resolve to garbage (`/llvm/bin/clang`) if the variable ever disappears.
2. **`-DGMX_BUILD_OWN_FFTW=ON` is incompatible with the Ninja generator**
   ("Cannot build FFTW3 automatically ... with ninja"). Use the default
   Makefiles generator (`cmake ..` without `-GNinja`) + `make -j$(nproc)`.
3. **GROMACS ignores the standard `CMAKE_HIP_ARCHITECTURES`.** It has its own
   cache variable, `GMX_HIP_TARGET_ARCH` (default: CDNA/GCN list, no RDNA at
   all). Setting only `CMAKE_HIP_ARCHITECTURES=gfx1100` silently produces a
   binary with zero gfx1100 device code — `libamdhip64`'s device-matching
   logic then **segfaults on every mdrun, even `-nb cpu`** (mdrun always
   probes the GPU at startup, regardless of what it's asked to run on). Must
   pass `-DGMX_HIP_TARGET_ARCH=gfx1100`. Verify with:
   `gmx --version | grep "HIP compiler flags"` → should show `--offload-arch=gfx1100`.
4. **Zen4 (Ryzen 7940HS) auto-detects `GMX_SIMD=AVX_512`**, but that build
   segfaults immediately (a double-pumped-AVX-512 codegen bug). Force
   `-DGMX_SIMD=AVX2_256` explicitly.
5. **`-bonded gpu` requires a dynamical integrator** (`md`/`sd`, not
   `steep`/`cg` energy minimization) **and** the system must actually have
   classical bonded interactions — pure SPC water (SETTLE constraints only,
   no bonds/angles/dihedrals) has none, so it's a no-op/error there.

## Getting maximum GPU offload for your own simulation

Unlike the pre-built benchmark `.tpr` files below (fixed settings, can't be
changed), a system you build yourself gives full control:

1. **Use `constraints = h-bonds` in your `.mdp`, not `all-bonds`.** GPU-resident
   update requires "update groups" — every constraint chain must attach to one
   central atom with at most 2 sequential constraints. `h-bonds` (the common
   choice for essentially all standard force fields) satisfies this;
   `all-bonds` doesn't, and forces the update/constraint step onto the CPU
   every step (see `benchMEM` below for exactly this failure mode).
2. **Single-rank, single-GPU**: `-ntmpi 1`. GPU-resident update explicitly
   requires this — domain decomposition (multi-rank) is currently
   incompatible with it.
3. **Full offload flags**:
   ```bash
   gmx mdrun -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu
   ```
   Confirm it actually engaged by checking the log for
   `"PP task will update and constrain coordinates on the GPU"` (not "on the CPU").
4. **Avoid features that force a CPU fallback regardless of constraints**:
   free-energy perturbation, domain decomposition, replica exchange are all
   currently incompatible with GPU-resident update.
5. **`integrator = md` (or `sd`)** — not `steep`/`cg` — for `-bonded gpu`/`-update gpu`.
6. **Optional: hydrogen mass repartitioning (HMR)** — not required for GPU
   offload, but complements it. Redistributes mass onto bonded hydrogens,
   allowing a 4 fs timestep with `h-bonds` constraints instead of 2 fs,
   roughly doubling ns/day for the same wall-clock cost.

## Test scripts

Both live in this directory (git-tracked; everything else here, e.g. run
output, is gitignored) and are run via `docker compose exec`:

```bash
# Build verification — synthetic water box, no network needed, seconds to run.
# Confirms the HIP build works (GPU non-bonded + PME + update offload).
docker compose exec gromacs-rocm bash /work/smoketest.sh

# GPU stress test — downloads a real benchmark system from the official
# GROMACS developer benchmark set (mpinat.mpg.de, CC-BY 4.0) and runs for a
# fixed wall-clock time budget (default 15 min) with GPU offload, reporting
# ns/day. Duration is controlled by GROMACS's own -maxh flag, so it's
# predictable regardless of which benchmark's system size you pick.
docker compose exec gromacs-rocm bash /work/stresstest.sh
#   optional non-interactive form: bash /work/stresstest.sh benchMEM 30   (30 min)
#   choices: benchMEM (82k atoms) | benchRIB (2M) | benchPEP (12M) | benchPEP-h (12M, full GPU offload incl. -update gpu)
```

Only `benchPEP-h` uses `h-bonds` constraints — it's the one benchmark of the
four built specifically to support full `-update gpu` offload. The other
three (`benchMEM`, `benchRIB`, `benchPEP`) use `all-bonds` constraints, so
their update/constraint step always runs on the CPU regardless of flags —
expect bursty GPU power draw and low VRAM usage for those, not sustained
high utilization. That's a property of the benchmark's constraint scheme,
not a build or passthrough problem (confirmed via `gdb` backtrace + the
GROMACS docs on "update groups" during development of this stack).

## Comparing your results to published numbers

`benchMEM` (81,743 atoms) and `benchRIB` (2,136,412 atoms) are the exact same
input systems used in Kutzner et al., *"More bang for your buck: Improved use
of GPU nodes for GROMACS 2018"* (2019, [arXiv:1903.05918](https://arxiv.org/abs/1903.05918)),
which published single-GPU ns/day numbers for a range of NVIDIA consumer GPUs
of that era:

| CPU + single GPU | MEM (ns/day) | RIB (ns/day) |
|---|---|---|
| E3-1270v5 + GTX 1070 | ~63.0 | ~3.14 |
| E3-1240v6 + GTX 1080 | ~78.0 | ~3.48 |
| i7-6700K + GTX 1080Ti | ~92.5 | ~4.03 |
| E3-1240v6 + RTX 2080 | 110.7 | 4.85 |
| E3-1240v6 + RTX 2080Ti (2018 flagship) | 133.3 | 5.77 |

RX 7900 XTX + Ryzen 9 7940HS on this build: **149.6 ns/day** on `benchMEM` —
above the RTX 2080Ti reference point. Not a clean hardware-only comparison
(that paper used GROMACS 2018; we're on 2026.3, so ~8 years of GROMACS
software optimization also contributes), but a useful sanity-check data
point nonetheless. `benchRIB` wasn't run for direct comparison yet — do so
for a second data point against the same table.

No comparable published numbers were found for `benchPEP`/`benchPEP-h`
(12M atoms) on any hardware close to this GPU generation — those papers
predate RDNA3 and mostly report multi-GPU HPC-node throughput for that
benchmark, not single consumer-GPU numbers, so a fair comparison isn't
readily available.
