#!/usr/bin/env python3
"""plot_report.py — phase-7 plotting + REPORT.md (runs in md-prep container).

Usage: python3 plot_report.py <analysis_dir> <prod_time_ps>
Reads the .xvg files produced by analyze.sh, writes one .png per .xvg and a
REPORT.md with: mean +/- sd of T/P/density over the last 50%, RMSD plateau
value + time, Rg, SS conservation, diffusion coefficient (Einstein fit of
MSD), drift, and a caveats section.
Exit: 0 on success (all plots + report), 1 on failure.
"""
import sys
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read_xvg(path):
    """Return (times, {column_name: values}) from a GROMACS .xvg file."""
    times, cols, names = [], {}, None
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("@"):
                m = re.match(r'@ (?:legend|xlab|ylab) .*?"([^"]*)"', line)
                if m and line.startswith("@ legend"):
                    names = [s.strip() for s in m.group(1).split("\\")]
                continue
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                continue
            times.append(vals[0])
            for i, v in enumerate(vals[1:], start=1):
                cols.setdefault(i, []).append(v)
    t = np.array(times)
    data = {i: np.array(v) for i, v in cols.items()}
    return t, data


def stats(arr):
    return f"{np.mean(arr):.4f} +/- {np.std(arr):.4f}"


def plateau(rmsd_t, rmsd_v, frac=0.5):
    """Plateau value = mean of last 50%; time = first t where the running mean
    of the last 10% window stays within 10% of the plateau for the rest."""
    if len(rmsd_v) < 10:
        return float(np.mean(rmsd_v)), float(rmsd_t[-1])
    plat = float(np.mean(rmsd_v[int(len(rmsd_v) * (1 - frac)):]))
    n = len(rmsd_v)
    win = max(1, n // 10)
    t_plateau = float(rmsd_t[-1])
    for i in range(win, n):
        window_mean = float(np.mean(rmsd_v[i - win:i]))
        if abs(window_mean - plat) <= 0.10 * max(plat, 1e-6):
            t_plateau = float(rmsd_t[i - win])
            break
    return plat, t_plateau


def einstein_d(msd_t, msd_v, t0_ps, t1_ps, dim=3):
    """D from MSD = 2*d*D*t: linear fit of the MSD curve over [t0_ps, t1_ps].
    2026.3 `gmx msd` no longer prints the fitted D, so it is fitted here from
    the curve (POST_SIM_RCA issue 5). Ranges are the linear (diffusive)
    regime, scaled with trajectory length: water 100-2000 ps, protein
    1000-5000 ps for a 10 ns run."""
    mask = (msd_t >= t0_ps) & (msd_t <= t1_ps)
    t, m = msd_t[mask], msd_v[mask]
    if len(t) < 5 or t[-1] <= t[0]:
        return None
    slope = float(np.polyfit(t, m, 1)[0])
    d = slope / (2 * dim)
    return max(d, 0.0)


def main():
    adir = sys.argv[1]
    prod_ps = float(sys.argv[2]) if len(sys.argv) > 2 else None
    ns = prod_ps / 1000.0 if prod_ps else None

    xvgs = sorted(f for f in os.listdir(adir) if f.endswith(".xvg"))
    if not xvgs:
        print("FAIL|analyze|no .xvg files in", adir)
        return 1

    report = ["# Analysis report", ""]
    report.append(f"Production length: {ns} ns" if ns else "Production length: unknown")
    report.append("")

    plots = []
    for xvg in xvgs:
        path = os.path.join(adir, xvg)
        try:
            t, data = read_xvg(path)
            if len(t) == 0:
                raise ValueError("empty series")
            fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
            for col, v in data.items():
                label = f"col{col}"
                if len(v) == len(t):
                    ax.plot(t, v, label=label, lw=0.8)
            ax.set_xlabel("time (ps)")
            ax.set_ylabel("value")
            ax.set_title(xvg.replace(".xvg", ""))
            ax.legend(fontsize=8)
            fig.tight_layout()
            png = os.path.join(adir, xvg.replace(".xvg", ".png"))
            fig.savefig(png)
            plt.close(fig)
            plots.append(xvg)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL|plot|{xvg}: {e}")
            return 1

    # ---- summary numbers -----------------------------------------------------
    report.append("## Key numbers")
    report.append("")
    report.append("| Quantity | Value |")
    report.append("|----------|-------|")

    def last50(t, v):
        i = int(len(v) * 0.5)
        return v[i:]

    def find(xvg_prefix):
        for x in xvgs:
            if x.startswith(xvg_prefix):
                t, data = read_xvg(os.path.join(adir, x))
                if data:
                    return t, data
        return None, None

    # T/P/density come from energies.xvg columns. data[] is 0-indexed (data[0]=time);
    # GROMACS orders the terms Potential, Kinetic, Total, Temp, Pres, Volume, Density,
    # so Temp=4, Pres=5, Density=7. Density is in kg/m3 (see the xvg yaxis label).
    t, data = find("energies")
    if t is not None and data:
        for name, col, unit in [("Temperature (last 50%)", 4, "K"),
                                ("Pressure (last 50%)", 5, "bar"),
                                ("Density (last 50%)", 7, "kg/m3")]:
            if col in data and len(data[col]) == len(t):
                report.append(f"| {name} | {stats(last50(t, data[col]))} {unit} |")

    t, data = find("rmsd")
    if t is not None and 1 in data:
        v = data[1]
        plat, t_plat = plateau(t, v)
        report.append(f"| RMSD plateau (backbone) | {plat:.4f} nm at ~{t_plat:.0f} ps |")

    t, data = find("gyrate")
    if t is not None and 1 in data:
        report.append(f"| Radius of gyration (last 50%) | {stats(last50(t, data[1]))} nm |")

    t, data = find("dssp")
    if t is not None and 1 in data:
        report.append(f"| SS fraction (first col, last 50%) | {stats(last50(t, data[1]))} |")

    # D units: 1 nm2/ps = 1e-2 cm2/s. Fit ranges scale with trajectory length
    # (tmax): water 1%-20% (100-2000 ps at 10 ns), protein 10%-50%
    # (1000-5000 ps at 10 ns) — the linear regime per POST_SIM_RCA issue 5.
    t, data = find("msd_water")
    if t is not None and 1 in data and len(t) > 0:
        tmax = float(t[-1])
        d = einstein_d(t, data[1], 0.01 * tmax, 0.20 * tmax)
        if d is not None:
            report.append(f"| Diffusion coefficient (Einstein, water) | {d:.4e} nm2/ps ({d * 1e-2:.4e} cm2/s) |")

    t, data = find("msd_protein")
    if t is not None and 1 in data and len(t) > 0:
        tmax = float(t[-1])
        d = einstein_d(t, data[1], 0.10 * tmax, 0.50 * tmax)
        if d is not None:
            report.append(f"| Diffusion coefficient (Einstein, protein) | {d:.4e} nm2/ps ({d * 1e-2:.4e} cm2/s) |")

    t, data = find("energies")
    if t is not None and data and 1 in data and len(data[1]) >= 20:
        v = data[1]
        first = float(np.mean(v[: len(v) // 10]))
        last = float(np.mean(v[-len(v) // 10:]))
        if first:
            drift = abs((last - first) / first)
            report.append(f"| Total-energy drift (first vs last 10%) | {drift:.4f} |")

    # ---- caveats ---------------------------------------------------------------
    report.append("")
    report.append("## Caveats")
    report.append("")
    report.append("- RMSD plateau is a necessary, not sufficient, indicator of convergence.")
    report.append("- Equilibration fraction: verify NVT/NPT lengths against system size (KB 01.5/01.6).")
    report.append("- Warnings seen during the run are listed in RUNLOG.md; re-check md.log before publishing results.")
    report.append("")

    with open(os.path.join(adir, "REPORT.md"), "w") as f:
        f.write("\n".join(report))

    print(f"PASS|analyze|{len(plots)} plots + REPORT.md written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
