# Protocol and Agent Separation Model

## Purpose

The repository now treats protocol/runtime and demo agents as separate execution layers:

- Protocol/runtime layer:
  - `src/nexus_a2a_protocol`
  - `shared/nexus_common`
- Agent layer:
  - `demos/*`
- Validation layer:
  - protocol-only tests in `tests/test_*`
  - integration harness in `tests/nexus_harness/*`

This preserves portability of the protocol package for non-HelixCare adopters.

## Enforced Boundaries

- Protocol/runtime code must not import demo/test/tool modules.
- A boundary enforcement test runs at `tests/test_architecture_boundaries.py`.

## Validation Workflow

Use `tools/run_target_architecture_validation.py` to run separated phases:

1. Generate expanded load matrix and gate-specific matrices.
2. Launch agents (`tools/launch_all_agents.py --with-backend`).
3. Run protocol-only tests.
4. Run integration harness tests.
5. Run traffic gates (`g0` to `g4`).
6. Stop agents.

Output report:
- `docs/target_architecture_validation.json`

## Load Gates

- Primary matrix:
  - `nexus-a2a/artefacts/matrices/nexus_command_centre_load_matrix.json`
- Per-gate matrices:
  - `nexus-a2a/artefacts/matrices/gates/nexus_command_centre_load_matrix_gate_g0.json`
  - `nexus-a2a/artefacts/matrices/gates/nexus_command_centre_load_matrix_gate_g1.json`
  - `nexus-a2a/artefacts/matrices/gates/nexus_command_centre_load_matrix_gate_g2.json`
  - `nexus-a2a/artefacts/matrices/gates/nexus_command_centre_load_matrix_gate_g3.json`
  - `nexus-a2a/artefacts/matrices/gates/nexus_command_centre_load_matrix_gate_g4.json`
