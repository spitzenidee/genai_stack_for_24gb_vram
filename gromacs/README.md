[Back to main README](../README.md)

# GROMACS (ROCm/HIP, gfx1100)

## TL;DR

`gromacs-rocm` is a single-GPU HIP build of GROMACS 2026.3 for RDNA3
(gfx1100 / RX 7900 XTX) with full GPU offload (nb + pme + bonded + update).
The container idles; `make gromacs` switches to this mode, then you
`docker compose exec gromacs-rocm bash` for interactive prep/mdrun sessions.
You touch this when you want to run a molecular-dynamics simulation, run the
smoketest/stresstest, or rebuild the image.

## What & why

The molecular-dynamics work mode of the stack. GROMACS is an MD engine for
molecular simulations (proteins, membranes, …). It runs on the eGPU via
ROCm/HIP and is profile-gated behind the `gromacs` work mode, so it never
contends with the llama.cpp servers for VRAM. This doc covers: the build,
build gotchas hit along the way, how to get maximum GPU offload for your own
simulations, the test scripts, and how the results compare to published
reference numbers.

## How it works

`gromacs-rocm` builds GROMACS 2026.3 from source with the HIP GPU backend,
targeting RDNA3 (gfx1100). See [Dockerfile.rocm](Dockerfile.rocm) for the full
build.

### Build (`Dockerfile.rocm`)

- Base: `rocm/dev-ubuntu-24.04:7.14.1-full`.
- `ENV ROCM_PATH=/opt/rocm` (base image already exports it; kept explicit as a
  defensive guard).
- GPU back end: `-DGMX_GPU=HIP -DGMX_HIP_TARGET_ARCH=gfx1100`.
- SIMD: `-DGMX_SIMD=AVX2_256` (auto-detected AVX-512 segfaults on Zen4 in
  this build).
- FFT: GROMACS auto-selects VkFFT for consumer RDNA.
- MPI: off (`-DGMX_MPI=OFF`); uses built-in thread-MPI.
- `LD_PRELOAD=libjemalloc.so.2` and `HSA_ENABLE_SDMA=0`.

### Build gotchas (already fixed in Dockerfile.rocm, kept here for reference)

1. **`ROCM_PATH` is exported by the base image, but we keep it explicit.**
   `rocm/dev-ubuntu-24.04:7.14.1-full` already sets `ROCM_PATH=/opt/rocm`
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
   `gmx --version | grep "HIP compiler flags"` → should show
   `--offload-arch=gfx1100`.
4. **Zen4 (Ryzen 7940HS) auto-detects `GMX_SIMD=AVX_512`**, but that build
   segfaults immediately (a double-pumped-AVX-512 codegen bug). Force
   `-DGMX_SIMD=AVX2_256` explicitly.
5. **`-bonded gpu` requires a dynamical integrator** (`md`/`sd`, not
   `steep`/`cg` energy minimization) **and** the system must actually have
   classical bonded interactions — pure SPC water (SETTLE constraints only,
   no bonds/angles/dihedrals) has none, so it's a no-op/error there.

## How to use

### Everyday usage

```bash
make gromacs
docker compose exec gromacs-rocm bash
```

Inside the container:

```bash
gmx mdrun -ntmpi 1 -nb gpu -pme gpu -bonded gpu -update gpu \
  -deffnm run1
```

GPU-resident update requires:
- single rank (`-ntmpi 1`),
- dynamical integrator (`md` or `sd`),
- `constraints = h-bonds` in the `.mdp` (not `all-bonds`).

### Getting maximum GPU offload for your own simulation

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

### Test scripts

Both live in this directory (git-tracked; everything else here, e.g. run
output, is gitignored) and are run via `docker compose exec`.

#### Smoketest

Builds a 3 nm water box from built-in force-field files (no network
required), runs energy minimization + a short NVT MD, and verifies the GPU
was used.

```bash
make gromacs
docker compose exec gromacs-rocm bash /work/smoketest.sh
```

The script:
1. writes `topol.top`, `em.mdp`, `nvt.mdp` under `/work/_smoketest`;
2. solvates with `gmx solvate -cs spc216.gro`;
3. runs EM with `-nb gpu`;
4. runs NVT with `-nb gpu -pme gpu -update gpu`;
5. checks `nvt.log` for “Finished mdrun” and GPU-device evidence.

#### Stresstest

Downloads one of the MPI-NAT GROMACS benchmark systems and runs it for a
fixed wall-clock budget (default 15 min, controlled by GROMACS's own `-maxh`
flag), reporting `ns/day`.

```bash
docker compose exec gromacs-rocm bash /work/stresstest.sh
#   optional non-interactive form: bash /work/stresstest.sh benchPEP-h 30   (30 min)
```

Available systems:

| System       | Atoms | Constraints | Update step |
|--------------|-------|-------------|-------------|
| `benchMEM`   | ~82 k | all-bonds   | CPU         |
| `benchRIB`   | ~2 M  | all-bonds   | CPU         |
| `benchPEP`   | ~12 M | all-bonds   | CPU         |
| `benchPEP-h` | ~12 M | h-bonds     | GPU-capable |

Only `benchPEP-h` enables `-update gpu`; the other three force the
integrator update onto the CPU because of `all-bonds` constraints — expect
bursty GPU power draw and low VRAM usage for those, not sustained high
utilization. That's a property of the benchmark's constraint scheme, not a
build or passthrough problem (confirmed via `gdb` backtrace + the GROMACS
docs on "update groups" during development of this stack).

On my setuP (mind that I lowered the powerlimit for the Radeon RX 7900 XTX to
265W) I get the following numbers for stresstesting on the `benchPEP-h` system
(h-bond constraints also on GPU):

```
Step 11900: Run time exceeded 0.247 hours, will terminate the run within 100 steps

| Metric       | Core t (s) | Wall t (s) | (%)   |
|--------------|------------|------------|-------|
| **Time**     | 6339.299   | 905.650    | 700.0 |

| Metric          | ns/day | hour/ns | ms/step | Matom*steps/s |
|-----------------|--------|---------|---------|---------------|
| **Performance** | 2.290  | 10.481  | 75.465  | 165.581       |
```

### Comparing your results to published numbers

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

## Configuration & influence

### Environment variables (`.env`)

| Variable | Meaning |
|---|---|
| `GROMACS_PROJECTS_DIR` | parent directory for MD projects (the `/work` volume root) |
| `GPU_RENDER_DEVICE` / `GPU_CARD_DEVICE` | eGPU DRI nodes |
| `RENDER_GID` / `VIDEO_GID` | host group IDs for GPU access |

### Runtime environment (set in the image)

- `HSA_ENABLE_SDMA=0` — required in this VFIO/KVM passthrough setup to avoid
  IOMMU TLB-flush storms.
- `LD_PRELOAD=libjemalloc.so.2` — reduces malloc fragmentation from the
  repeated per-step allocations in neighbor-search/domain-decomposition over
  long runs.
- `LD_LIBRARY_PATH` names `/opt/rocm/lib` explicitly — the base image does
  **not** export it in its image config, so without it every `gmx`
  invocation dies with `error while loading shared libraries:
  libamdhip64.so.7`.

## Troubleshooting

- **GROMACS crashes with AVX-512.** The Zen 4 build pins
  `-DGMX_SIMD=AVX2_256` because auto-detected AVX-512 segfaults in this
  build; do not override without rebuilding and re-verifying.
- **`gmx mdrun -update gpu` is rejected.** GPU-resident update requires a
  single rank (`-ntmpi 1`), an `md`/`sd` integrator, and
  `constraints = h-bonds` (not `all-bonds`) in the `.mdp`.

## Related skills

- `gromacs-sim` — state machine + deterministic gates for end-to-end GROMACS
  MD simulations on this stack (2026.3 HIP build): prep, topology, solvation,
  EM, equilibration, production, analysis, cleanup.
- `gromacs-kb-audit` — audit the GROMACS knowledge base
  (`.pi/skills/gromacs-sim/knowledge/`) against the local `gromacs-rocm`
  docker build.
- `gromacs-kb-fix` — fix open GROMACS KB issues
  (`.pi/skills/gromacs-sim/knowledge/issues_kb.md`) against the local
  `gromacs-rocm` build.
- `aa-mutation-advisor` — expert advisor for protein / amino-acid chemistry
  and site-directed mutagenesis design.

## Related

- GPU work-mode switching and the always-on services: see the main README
  (GPU work modes, Services and ports).
- Observability (GPU exporter, Grafana): see the main README.

[Back to main README](../README.md)
