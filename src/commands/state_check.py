from __future__ import annotations

import argparse
from pathlib import Path

from vision.detector import CznDetector, annotate, print_state, save_image
from system.io_system import resolve_monitor_index, screen_shot
import core.settings as cfg
from core.settings import (
    CAPTURE_METHODS,
    apply_user_config,
    app_install_dir,
    default_config_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one fresh frame and classify the current CZN state.")
    parser.add_argument("--config", type=Path, default=default_config_file())
    parser.add_argument("--no-user-config", action="store_true")
    parser.add_argument("--monitor")
    parser.add_argument("--capture-method", choices=sorted(CAPTURE_METHODS))
    args = parser.parse_args()
    if not args.no_user_config:
        apply_user_config(args.config, create_missing=False)
    monitor_value = args.monitor if args.monitor is not None else cfg.MONITOR_INDEX
    capture_method = args.capture_method if args.capture_method is not None else cfg.CAPTURE_METHOD
    args.monitor = resolve_monitor_index(monitor_value)

    root = app_install_dir()
    frame, monitor = screen_shot(args.monitor, capture_method)
    detector = CznDetector()
    state = detector.detect(frame)
    print(f"capture={capture_method} monitor={monitor}")
    print_state("fresh_state", state)
    save_image(root / "debug_live" / "fresh_state.jpg", frame)
    save_image(root / "debug_live" / "fresh_state_annotated.jpg", annotate(frame, state))


if __name__ == "__main__":
    main()
