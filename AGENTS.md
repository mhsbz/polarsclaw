# PolarsClaw Agent Instructions

## Runtime Environment

- Run all PolarsClaw project commands through the `xw_cloud` conda environment.
- Prefer `conda run -n xw_cloud <command>` for Codex tool calls because shell activation does not persist across separate commands.
- Use `conda run -n xw_cloud python -m pytest` for tests.
- Use `conda run -n xw_cloud python -m compileall polarsclaw` for syntax checks.
- Use `conda run -n xw_cloud polarsclaw ...` for CLI/runtime checks.
- Do not use the base conda environment for project execution unless explicitly debugging environment setup.
