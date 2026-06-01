# Source Layout

This directory contains the runnable implementation. Run source commands from the repository root.

- `main.py`: source CLI entry point.
- `state_check.py`: thin entry point for fresh current-state checks.
- `diagnose_input.py`: thin entry point for Windows window/input diagnosis.
- `commands/`: command implementations and argument parsing.
- `core/`: shared models, config loading, paths, logging, and mutable runtime settings.
- `vision/`: template detector and image/video diagnosis helpers.
- `system/`: screen capture, window discovery, click/input backends, and stop-key helpers.
- `actions/`: reusable transition/action helpers used by state machines.
- `ui/`: user-facing run/action logging helpers.
- `state_machines/live/`: the current default automation state machine.

Future workflows should live under their own `state_machines/<workflow>/` folder, with a small runner that composes shared detector, IO, action, and settings modules.

Packaging files are intentionally outside `src/` under `../packaging/`.

Common source commands:

```bat
python src\main.py --live --max-seconds 30
python src\state_check.py
python src\diagnose_input.py --dry-run
```
