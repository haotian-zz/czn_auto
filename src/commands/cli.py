from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from vision.detector import CznDetector, run_image, run_video
from system.io_system import resolve_monitor_index
from core.settings import *
from state_machines.live.session import run_live


def main() -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, default=default_config_file())
    pre_parser.add_argument("--no-user-config", action="store_true")
    pre_parser.add_argument("--init-config", action="store_true")
    pre_args, _ = pre_parser.parse_known_args()
    if pre_args.init_config:
        path = write_default_config(pre_args.config, overwrite=False)
        print(f"config ready: {path}")
        return
    if not pre_args.no_user_config and not any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        apply_user_config(pre_args.config)

    parser = argparse.ArgumentParser(description="CZN visual detector and cautious automation helper.")
    parser.add_argument("--config", type=Path, default=pre_args.config, help="User config JSON path. Defaults to config.json next to the program.")
    parser.add_argument("--no-user-config", action="store_true", help="Ignore the user config file for this run.")
    parser.add_argument("--init-config", action="store_true", help="Create the default user config file and exit.")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--every-sec", type=float, default=0.25)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--log-file", type=Path, help="Write detailed run output to this log file. Defaults to LocalAppData\\CZN Auto\\logs.")
    parser.add_argument("--no-run-log", action="store_true", help="Disable the automatic per-run log file.")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--act", action="store_true", help="Actually click in live mode. Omit for dry-run.")
    parser.add_argument("--interval", type=float, default=LIVE_LOOP_INTERVAL)
    parser.add_argument("--log-interval", type=float, default=LIVE_LOG_INTERVAL, help="Minimum seconds between repeated live state log lines. 0 prints every loop.")
    parser.add_argument("--max-seconds", type=float, default=0.0, help="Stop live mode after this many seconds. 0 means run until stopped/found.")
    parser.add_argument("--max-clicks", type=int, default=0, help="Stop live mode after this many actual clicks. 0 means unlimited.")
    parser.add_argument("--post-click-wait", type=float, default=POST_CLICK_WAIT, help="Wait this many seconds after each click for a real visual change.")
    parser.add_argument(
        "--wait-after-team-enter",
        type=float,
        default=WAIT_AFTER_TEAM_ENTER_BEFORE_DIALOG,
        help="After clicking team enter, wait this many seconds before allowing blind dialog advance bursts.",
    )
    parser.add_argument(
        "--dialog-burst-mode",
        choices=["rapid", "checked"],
        default=DIALOG_BURST_MODE,
        help="Dialog advance burst behavior. rapid keeps the old fast continuous clicks; checked re-detects after each tap.",
    )
    parser.add_argument(
        "--input-backend",
        choices=sorted(INPUT_BACKENDS),
        default=INPUT_BACKEND,
        help="Click backend. sendinput is stable foreground input; postmessage modes are experimental background messages.",
    )
    parser.add_argument(
        "--restore-cursor-after-click",
        action=argparse.BooleanOptionalAction,
        default=RESTORE_CURSOR_AFTER_CLICK,
        help="Move the cursor back to its previous position after sendinput clicks.",
    )
    parser.add_argument(
        "--target-window-title",
        default=INPUT_TARGET_WINDOW_TITLE,
        help="Prefer a visible window whose title contains this text for postmessage clicks.",
    )
    parser.add_argument(
        "--monitor",
        default=MONITOR_INDEX,
        help="monitor index, or auto to use the target game window. Defaults to runtime.monitor in config.",
    )
    parser.add_argument(
        "--capture-method",
        choices=sorted(CAPTURE_METHODS),
        default=CAPTURE_METHOD,
        help="Live screenshot backend. auto prefers reliable mss capture; dxgi forces the faster DXGI backend.",
    )
    parser.add_argument("--advance-on-unknown", action="store_true", help="Allow live mode to click the advance point when no known UI state is detected.")
    parser.add_argument(
        "--fast-start-to-team",
        action="store_true",
        help="After detecting the main enter button once, tap the enter area several times without waiting for team-screen recognition.",
    )
    parser.add_argument(
        "--wide-match-scales",
        action="store_true",
        help="Use the older wider 7-scale template search. Slower, but useful if fast matching misses UI on unusual scaling.",
    )
    parser.add_argument(
        "--stop-key",
        default="f8,esc,pause,end",
        help="Comma-separated global emergency stop keys for live mode.",
    )
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"), help="Create this file to stop live mode.")
    parser.add_argument(
        "--no-dream-action",
        choices=["retry-top-right", "confirm", "none"],
        default="retry-top-right",
        help="What live mode should do on a card reward screen when 梦之边境 is not detected.",
    )
    args = parser.parse_args()
    set_runtime_value("INPUT_BACKEND", args.input_backend)
    set_runtime_value("RESTORE_CURSOR_AFTER_CLICK", args.restore_cursor_after_click)
    set_runtime_value("INPUT_TARGET_WINDOW_TITLE", args.target_window_title.strip())

    log_path = None
    if not args.no_run_log:
        log_path = setup_run_log(args.log_file)
    try:
        args.monitor = resolve_monitor_index(args.monitor)
    except Exception as exc:
        parser.error(str(exc))
    print_run_header(args, log_path)

    detector = CznDetector(wide_match_scales=args.wide_match_scales)
    if args.image:
        run_image(detector, args.image, args.out_dir)
    elif args.video:
        run_video(detector, args.video, args.every_sec, args.out_dir)
    elif args.live:
        run_live(
            detector,
            args.act,
            args.interval,
            args.no_dream_action,
            args.max_seconds,
            args.monitor,
            args.advance_on_unknown,
            args.stop_key,
            args.max_clicks,
            args.stop_file,
            args.post_click_wait,
            args.capture_method,
            args.fast_start_to_team,
            args.log_interval,
            args.wait_after_team_enter,
            args.dialog_burst_mode,
        )
    else:
        parser.error("pass --image, --video, or --live")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("KeyboardInterrupt; exiting.", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except Exception:
        print("fatal error: unhandled exception", file=sys.stderr, flush=True)
        traceback.print_exc()
        raise SystemExit(1)
