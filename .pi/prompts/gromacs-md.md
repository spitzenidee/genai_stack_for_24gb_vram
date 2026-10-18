---
description: Run/continue a GROMACS MD simulation via the gromacs-md agent
argument-hint: <sim_name_or_request>
subagent: gromacs-md
---
GROMACS MD simulation request: $ARGUMENTS

Start (or resume) the simulation in `gromacs/work/projects/<sim>/` following
the `gromacs-sim` skill state machine. If the name is an existing project
directory, resume from its `state.json`. If it is a new request, begin at
phase 0 (preflight) and ask the Tier A questions before phase 1.
