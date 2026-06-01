from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from system.controls import sleep_interruptible, stop_requested
from vision.detector import CznDetector, print_state, start_match_looks_like_team_fallback
from system.io_system import click_frame_point, click_norm, rapid_click_norm, screen_shot
from core.models import DetectionState
from core.settings import *
from ui.logging import print_action
def visual_diff_score(before: np.ndarray, after: np.ndarray) -> float:
    if before.shape[:2] != after.shape[:2]:
        return 999.0
    small_before = cv2.resize(before, (320, 180), interpolation=cv2.INTER_AREA)
    small_after = cv2.resize(after, (320, 180), interpolation=cv2.INTER_AREA)
    gray_before = cv2.cvtColor(small_before, cv2.COLOR_BGR2GRAY)
    gray_after = cv2.cvtColor(small_after, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(gray_before, gray_after)))


def roi_visual_diff_score(before: np.ndarray, after: np.ndarray, roi: Box) -> float:
    if before.shape[:2] != after.shape[:2]:
        return 999.0
    h, w = before.shape[:2]
    x1, y1, x2, y2 = roi.to_pixels(w, h)
    return visual_diff_score(before[y1:y2, x1:x2], after[y1:y2, x1:x2])


def choice_confirm_point_for(choice_point: tuple[int, int], frame_shape: tuple[int, ...]) -> tuple[int, int]:
    height, width = frame_shape[:2]
    x, _ = choice_point
    if x < width * 0.37:
        confirm_x = int(width * 0.238)
    elif x < width * 0.63:
        confirm_x = int(width * 0.500)
    else:
        confirm_x = int(width * 0.760)
    return confirm_x, int(height * CHOICE_CONFIRM_Y)


def wait_visual_change(
    detector: CznDetector,
    before_frame: np.ndarray,
    monitor_index: int,
    capture_method: str,
    stop_keys: list[str],
    stop_file: Path | None,
    timeout: float,
    threshold: float = 2.0,
    action_name: str = "action",
    expected_labels: set[str] | None = None,
) -> None:
    before_state = detector.detect(before_frame)
    after_path: Path | None = None
    if SAVE_VISUAL_CHANGE_DEBUG:
        debug_dir = Path.cwd() / "debug_live"
        stamp = time.strftime("%H%M%S")
        before_path = debug_dir / f"{stamp}_{action_name}_before.jpg"
        after_path = debug_dir / f"{stamp}_{action_name}_after.jpg"
        save_image(before_path, annotate(before_frame, before_state))
    deadline = time.time() + timeout
    best_score = 0.0
    best_roi_score = 0.0
    after_frame = before_frame
    after_state = before_state
    while time.time() < deadline:
        if stop_requested(stop_keys, stop_file):
            return
        time.sleep(VISUAL_CHANGE_POLL_INTERVAL)
        after_frame, _ = screen_shot(monitor_index, capture_method)
        after_state = detector.detect(after_frame)
        score = visual_diff_score(before_frame, after_frame)
        roi_score = roi_visual_diff_score(before_frame, after_frame, Box(0.0, 0.60, 1.0, 1.0))
        best_score = max(best_score, score)
        best_roi_score = max(best_roi_score, roi_score)
        expected_hit = expected_labels is not None and after_state.label in expected_labels
        state_changed = after_state.label != before_state.label
        visual_changed = score >= threshold or roi_score >= threshold
        if expected_hit or (expected_labels is None and (state_changed or visual_changed)):
            if after_path:
                save_image(after_path, annotate(after_frame, after_state))
            status = "expected" if expected_hit else "changed"
            saved = f", saved={after_path.name}" if after_path else ""
            print(
                f"after click {status}: state {before_state.label}->{after_state.label}, "
                f"diff={score:.2f}, bottom_diff={roi_score:.2f}{saved}",
                flush=True,
            )
            return
    if after_path:
        save_image(after_path, annotate(after_frame, after_state))
    saved = f", saved={after_path.name}" if after_path else ""
    expected = f", expected={','.join(sorted(expected_labels))}" if expected_labels else ""
    print(
        f"HIGH RISK: after click timeout/unexpected: state {before_state.label}->{after_state.label}, "
        f"best_diff={best_score:.2f}, best_bottom_diff={best_roi_score:.2f}{expected}{saved}",
        flush=True,
    )


def wait_for_detected_state(
    detector: CznDetector,
    monitor_index: int,
    capture_method: str,
    stop_keys: list[str],
    stop_file: Path | None,
    expected_labels: set[str],
    timeout: float,
    action_name: str,
    *,
    high_risk_on_timeout: bool = True,
) -> tuple[np.ndarray, dict, DetectionState] | None:
    deadline = time.time() + timeout
    last_state: DetectionState | None = None
    poll_count = 0
    while time.time() < deadline:
        if sleep_interruptible(VISUAL_CHANGE_POLL_INTERVAL, stop_keys, stop_file):
            return None
        frame, monitor = screen_shot(monitor_index, capture_method)
        state = detector.detect(frame)
        poll_count += 1
        last_state = state
        if state.label in expected_labels:
            print(
                f"fast wait ok: action={action_name}, state={state.label}, "
                f"polls={poll_count}, elapsed={timeout - max(0.0, deadline - time.time()):.1f}s"
            )
            return frame, monitor, state

    level = "HIGH RISK: " if high_risk_on_timeout else ""
    current = last_state.label if last_state else "none"
    expected = ",".join(sorted(expected_labels))
    print(
        f"{level}fast wait timeout: action={action_name}, current={current}, "
        f"expected={expected}, timeout={timeout:.1f}s, polls={poll_count}"
    )
    return None


def fast_advance_unknown(
    detector: CznDetector,
    monitor: dict,
    monitor_index: int,
    capture_method: str,
    stop_keys: list[str],
    stop_file: Path | None,
    act: bool,
    max_taps: int = DIALOG_BURST_MAX_TAPS,
    tap_delay: float = DIALOG_BURST_TAP_DELAY,
    mode: str = DIALOG_BURST_MODE,
    max_total_clicks: int | None = None,
) -> int:
    if stop_requested(stop_keys, stop_file):
        return 0
    if max_total_clicks is not None:
        max_taps = min(max_taps, max(0, max_total_clicks))
    if max_taps <= 0:
        print("advance/continue burst skipped: max click budget reached.")
        return 0
    print_action(f"advance/continue burst x{max_taps} mode={mode}", CLICK_ADVANCE, act)
    if act and mode == "rapid":
        clicks = rapid_click_norm(
            CLICK_ADVANCE,
            monitor,
            count=max_taps,
            duration=FAST_CLICK_DURATION,
            interval=tap_delay,
            stop_keys=stop_keys,
            stop_file=stop_file,
        )
        waited = wait_for_detected_state(
            detector,
            monitor_index,
            capture_method,
            stop_keys,
            stop_file,
            DIALOG_BURST_STOP_LABELS,
            max(DIALOG_BURST_RAPID_POSTCHECK, tap_delay * 2),
            "dialog_burst_rapid_postcheck",
            high_risk_on_timeout=True,
        )
        if waited:
            _, _, state = waited
            print(f"dialog rapid burst postcheck: reached {state.label} after {clicks} taps.")
            return clicks
        if stop_requested(stop_keys, stop_file):
            print("dialog rapid burst postcheck stopped; skip fallback clicks.")
            return clicks

        remaining = None if max_total_clicks is None else max(0, max_total_clicks - clicks)
        fallback_taps = DIALOG_BURST_FALLBACK_TAPS if remaining is None else min(DIALOG_BURST_FALLBACK_TAPS, remaining)
        if fallback_taps <= 0:
            print("dialog rapid burst fallback skipped: max click budget reached.")
            return clicks
        print(
            f"dialog rapid burst fallback: no next state after {clicks} rapid taps; "
            f"switching to checked fallback x{fallback_taps}."
        )
        clicks += checked_dialog_advance(
            detector,
            monitor,
            monitor_index,
            capture_method,
            stop_keys,
            stop_file,
            act,
            max_taps=fallback_taps,
            tap_delay=DIALOG_BURST_FALLBACK_TAP_DELAY,
            prefix="dialog fallback",
        )
        return clicks

    return checked_dialog_advance(
        detector,
        monitor,
        monitor_index,
        capture_method,
        stop_keys,
        stop_file,
        act,
        max_taps=max_taps,
        tap_delay=tap_delay,
        prefix="dialog burst",
    )


def checked_dialog_advance(
    detector: CznDetector,
    monitor: dict,
    monitor_index: int,
    capture_method: str,
    stop_keys: list[str],
    stop_file: Path | None,
    act: bool,
    max_taps: int,
    tap_delay: float,
    prefix: str,
) -> int:
    clicks = 0
    for i in range(max_taps):
        print_action(f"{prefix} {i + 1}/{max_taps}", CLICK_ADVANCE, act)
        if act:
            click_norm(CLICK_ADVANCE, monitor, duration=FAST_CLICK_DURATION)
            clicks += 1
        if sleep_interruptible(tap_delay, stop_keys, stop_file):
            return clicks
        if act:
            frame, _ = screen_shot(monitor_index, capture_method)
            state = detector.detect(frame)
            print_state(f"{prefix} {i + 1}/{max_taps}", state)
            if state.label in DIALOG_BURST_STOP_LABELS:
                print(f"{prefix} stopped early: reached {state.label} after {clicks} taps.")
                return clicks
    if act:
        print(
            f"HIGH RISK: {prefix} exhausted: taps={clicks}, state still unknown or not recognized. "
            "Possible causes: slow loading, stale screenshot, wrong monitor/resolution, or dialog timing mismatch."
        )
    return clicks


def fast_start_to_team(
    monitor: dict,
    stop_keys: list[str],
    stop_file: Path | None,
    act: bool,
    first_point: tuple[int, int] | None,
    max_taps: int = START_TO_TEAM_BURST_TAPS,
    tap_delay: float = START_TO_TEAM_TAP_DELAY,
) -> int:
    clicks = 0
    for i in range(max_taps):
        if stop_requested(stop_keys, stop_file):
            return clicks
        if i == 0 and first_point is not None:
            print_action(f"start -> team quick tap {i + 1}/{max_taps}", CLICK_START_ENTER, act)
            if act:
                click_frame_point(first_point, monitor, duration=FAST_CLICK_DURATION)
                clicks += 1
        else:
            print_action(f"start -> team quick tap {i + 1}/{max_taps}", CLICK_START_ENTER, act)
            if act:
                click_norm(CLICK_START_ENTER, monitor, duration=FAST_CLICK_DURATION)
                clicks += 1
        if sleep_interruptible(tap_delay, stop_keys, stop_file):
            return clicks
    return clicks


def fast_abandon_no_legend(
    detector: CznDetector,
    frame: np.ndarray,
    monitor: dict,
    monitor_index: int,
    capture_method: str,
    stop_keys: list[str],
    stop_file: Path | None,
    act: bool,
) -> int:
    clicks = 0
    state = detector.detect(frame)
    if state.label in {"start_screen", "team_screen"} or state.dialog_indicator:
        print(f"no legend chain skipped: current state is {state.label}; not clicking top-right menu.")
        return 0
    if not state.choice_card:
        print("no legend chain skipped: choice screen is not confirmed; not clicking top-right menu.")
        return 0
    if state.choice_card.name != "choice_glows":
        print(
            "no legend chain skipped: choice screen only matched structural fallback "
            f"({state.choice_card.name}); not clicking top-right menu."
        )
        return 0
    retry_point = state.top_right_menu.center if state.top_right_menu else None
    print_action("no legend chain: click top-right menu", CLICK_RETRY_TOP_RIGHT, act)
    if act:
        if retry_point:
            click_frame_point(retry_point, monitor, duration=CHAIN_CLICK_DURATION)
        else:
            click_norm(CLICK_RETRY_TOP_RIGHT, monitor, duration=CHAIN_CLICK_DURATION)
        clicks += 1

    flee_state: DetectionState | None = None
    flee_monitor = monitor
    if act:
        waited = wait_for_detected_state(
            detector,
            monitor_index,
            capture_method,
            stop_keys,
            stop_file,
            {"flee_screen"},
            CHAIN_MENU_TO_FLEE_TIMEOUT,
            "no_legend_menu_to_flee",
        )
        if waited:
            _, flee_monitor, flee_state = waited
    elif sleep_interruptible(CHAIN_MENU_TO_FLEE_DELAY, stop_keys, stop_file):
        return clicks

    if act:
        if flee_state and flee_state.flee_button:
            flee_point = flee_state.flee_button.point_at(0.72, 0.50)
            print_action(f"no legend chain: click detected flee at {flee_point}", CHAIN_FLEE_POINT, act)
            click_frame_point(flee_point, flee_monitor, duration=CHAIN_CLICK_DURATION)
        else:
            print_action("no legend chain: click fixed flee fallback", CHAIN_FLEE_POINT, act)
            click_norm(CHAIN_FLEE_POINT, monitor, duration=CHAIN_CLICK_DURATION)
        clicks += 1
    else:
        print_action("no legend chain: click fixed flee", CHAIN_FLEE_POINT, act)

    confirm_state: DetectionState | None = None
    confirm_monitor = monitor
    if act:
        waited = wait_for_detected_state(
            detector,
            monitor_index,
            capture_method,
            stop_keys,
            stop_file,
            {"return_confirm"},
            CHAIN_FLEE_TO_CONFIRM_TIMEOUT,
            "no_legend_flee_to_confirm",
        )
        if waited:
            _, confirm_monitor, confirm_state = waited
    elif sleep_interruptible(CHAIN_FLEE_TO_CONFIRM_DELAY, stop_keys, stop_file):
        return clicks

    if act:
        if confirm_state and confirm_state.return_confirm:
            confirm_point = confirm_state.return_confirm.point_at(0.68, 0.50)
            print_action(f"no legend chain: click detected confirm at {confirm_point}", CHAIN_RETURN_CONFIRM_POINT, act)
            click_frame_point(confirm_point, confirm_monitor, duration=CHAIN_CLICK_DURATION)
        else:
            print_action("no legend chain: click fixed confirm fallback", CHAIN_RETURN_CONFIRM_POINT, act)
            click_norm(CHAIN_RETURN_CONFIRM_POINT, monitor, duration=CHAIN_CLICK_DURATION)
        clicks += 1
        if sleep_interruptible(CHAIN_AFTER_CONFIRM_DELAY, stop_keys, stop_file):
            return clicks
    else:
        print_action("no legend chain: click fixed confirm", CHAIN_RETURN_CONFIRM_POINT, act)
    return clicks

