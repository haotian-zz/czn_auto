from __future__ import annotations

import argparse
from pathlib import Path

from czn_detector import (
    CAPTURE_METHODS,
    DEFAULT_CAPTURE_METHOD,
    MONITOR_INDEX,
    CznDetector,
    apply_user_config,
    annotate,
    default_config_file,
    print_state,
    resolve_monitor_index,
    save_image,
    screen_shot,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one fresh frame and classify the current CZN state.")
    parser.add_argument("--config", type=Path, default=default_config_file())
    parser.add_argument("--no-user-config", action="store_true")
    parser.add_argument("--monitor", default=MONITOR_INDEX)
    parser.add_argument("--capture-method", choices=sorted(CAPTURE_METHODS), default=DEFAULT_CAPTURE_METHOD)
    args = parser.parse_args()
    if not args.no_user_config:
        apply_user_config(args.config, create_missing=False)
    args.monitor = resolve_monitor_index(args.monitor)

    root = Path(__file__).resolve().parent
    frame, monitor = screen_shot(args.monitor, args.capture_method)
    detector = CznDetector()
    state = detector.detect(frame)
    print(f"capture={args.capture_method} monitor={monitor}")
    print_state("fresh_state", state)
    save_image(root / "debug_live" / "fresh_state.jpg", frame)
    save_image(root / "debug_live" / "fresh_state_annotated.jpg", annotate(frame, state))


if __name__ == "__main__":
    main()
