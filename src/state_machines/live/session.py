from __future__ import annotations

import dataclasses
import time
from pathlib import Path

import numpy as np

from actions.common import checked_dialog_advance, fast_abandon_no_legend, fast_advance_unknown, fast_start_to_team, wait_for_detected_state, wait_visual_change
from system.controls import parse_stop_keys, sleep_interruptible, stop_requested
from vision.detector import CznDetector, print_state, start_match_looks_like_team_fallback
from system.io_system import click_frame_point, click_norm, screen_shot
from core.models import DetectionState
from core.settings import *
from ui.logging import print_action
@dataclasses.dataclass
class LiveConfig:
    detector: CznDetector
    act: bool
    interval: float
    no_dream_action: str
    max_seconds: float
    monitor_index: int
    advance_on_unknown: bool
    stop_keys: list[str]
    max_clicks: int
    stop_file: Path | None
    post_click_wait: float
    capture_method: str
    fast_start_to_team_enabled: bool
    log_interval: float
    wait_after_team_enter: float
    dialog_burst_mode: str


@dataclasses.dataclass
class ExpectedTransition:
    action_name: str
    from_label: str
    expected_labels: set[str]
    started: float
    deadline: float


@dataclasses.dataclass
class LiveRuntime:
    last_action: float = 0.0
    next_action_delay: float = INITIAL_ACTION_DELAY
    started: float = dataclasses.field(default_factory=time.time)
    printed_monitor: bool = False
    waiting_after_legend: bool = False
    waiting_after_reward_action: bool = False
    handled_choice_without_legend: bool = False
    handled_start_screen: bool = False
    pending_legend_confirm_point: tuple[int, int] | None = None
    click_count: int = 0
    last_logged_state: str = ""
    last_log_time: float = 0.0
    wait_for_dialog_until: float = 0.0
    dialog_advance_armed: bool = False
    expected_transition: ExpectedTransition | None = None
    window_probe_attempted: bool = False


class LiveSession:
    def __init__(self, config: LiveConfig) -> None:
        self.config = config
        self.runtime = LiveRuntime()

    def run(self) -> None:
        cfg = self.config
        print(
            f"live mode started. capture={cfg.capture_method}. Stop keys: {', '.join(k.upper() for k in cfg.stop_keys)}. "
            "Dry-run is ON unless --act is passed."
        )
        print(
            "live config: "
            f"act={cfg.act}, interval={cfg.interval}, log_interval={cfg.log_interval}, "
            f"monitor={cfg.monitor_index}, max_seconds={cfg.max_seconds}, max_clicks={cfg.max_clicks}, "
            f"no_dream_action={cfg.no_dream_action}, advance_on_unknown={cfg.advance_on_unknown}, "
            f"fast_start_to_team={cfg.fast_start_to_team_enabled}, post_click_wait={cfg.post_click_wait}, "
            f"wait_after_team_enter={cfg.wait_after_team_enter}, dialog_burst_mode={cfg.dialog_burst_mode}, "
            f"input_backend={INPUT_BACKEND}, restore_cursor_after_click={RESTORE_CURSOR_AFTER_CLICK}, "
            f"target_window_title={INPUT_TARGET_WINDOW_TITLE!r}, "
            f"stop_file={cfg.stop_file}"
        )
        print(
            f"detector: template_dir={cfg.detector.template_dir}, "
            f"match_scale_factors={cfg.detector.match_scale_factors}"
        )
        if cfg.stop_file and cfg.stop_file.exists():
            cfg.stop_file.unlink()

        try:
            while True:
                if self.should_stop():
                    return
                frame, monitor = screen_shot(cfg.monitor_index, cfg.capture_method)
                if not self.runtime.printed_monitor:
                    print(f"using monitor {cfg.monitor_index}: {monitor}; frame_shape={frame.shape}")
                    self.runtime.printed_monitor = True
                state = cfg.detector.detect(frame)
                if state.label == "unknown" and not self.runtime.window_probe_attempted:
                    self.runtime.window_probe_attempted = True
                    probe = probe_game_window_capture(cfg.detector, cfg.capture_method)
                    if probe:
                        cfg.monitor_index = probe.monitor_index
                        frame = probe.frame
                        monitor = probe.monitor
                        state = probe.state
                        print(
                            f"using probed monitor {cfg.monitor_index}: {monitor}; frame_shape={frame.shape}",
                            flush=True,
                        )
                now = time.time()
                self.log_state(now, state)
                self.check_expected_transition(now, state)
                if now - self.runtime.last_action >= self.runtime.next_action_delay:
                    if not self.handle_state(frame, monitor, state, now):
                        return
                if sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file):
                    return
        finally:
            elapsed = time.time() - self.runtime.started
            print(f"live mode stopped. elapsed={elapsed:.1f}s, clicks={self.runtime.click_count}")

    def should_stop(self) -> bool:
        cfg = self.config
        rt = self.runtime
        if stop_requested(cfg.stop_keys, cfg.stop_file):
            return True
        if cfg.max_seconds > 0 and time.time() - rt.started >= cfg.max_seconds:
            print("live mode max seconds reached; exiting.")
            return True
        if cfg.max_clicks > 0 and rt.click_count >= cfg.max_clicks:
            print("live mode max clicks reached; exiting.")
            return True
        return False

    def log_state(self, now: float, state: DetectionState) -> None:
        rt = self.runtime
        if state.label != rt.last_logged_state or now - rt.last_log_time >= self.config.log_interval:
            print_state(time.strftime("%H:%M:%S"), state)
            rt.last_logged_state = state.label
            rt.last_log_time = now

    def mark_action(self, now: float, delay: float) -> None:
        self.runtime.last_action = now
        self.runtime.next_action_delay = delay

    def expect_transition(
        self,
        action_name: str,
        from_label: str,
        expected_labels: set[str],
        timeout: float,
    ) -> None:
        if not self.config.act:
            return
        started = time.time()
        timeout = max(timeout, self.config.interval)
        self.runtime.expected_transition = ExpectedTransition(
            action_name=action_name,
            from_label=from_label,
            expected_labels=expected_labels,
            started=started,
            deadline=started + timeout,
        )
        expected = ",".join(sorted(expected_labels))
        print(
            f"watch transition: action={action_name}, from={from_label}, "
            f"expected={expected}, timeout={timeout:.1f}s"
        )

    def check_expected_transition(self, now: float, state: DetectionState) -> None:
        transition = self.runtime.expected_transition
        if transition is None:
            return
        if state.label in transition.expected_labels:
            elapsed = now - transition.started
            print(
                f"transition ok: action={transition.action_name}, "
                f"{transition.from_label}->{state.label}, elapsed={elapsed:.1f}s"
            )
            self.runtime.expected_transition = None
            return
        if now < transition.deadline:
            return

        expected = ",".join(sorted(transition.expected_labels))
        elapsed = now - transition.started
        print(
            "HIGH RISK: transition timeout: "
            f"action={transition.action_name}, from={transition.from_label}, "
            f"current={state.label}, expected={expected}, elapsed={elapsed:.1f}s. "
            "Possible causes: click missed, wrong monitor/resolution, stale screenshot, or UI timing too short."
        )
        self.runtime.expected_transition = None
        self.recover_after_transition_timeout(transition, state)

    def recover_after_transition_timeout(self, transition: ExpectedTransition, state: DetectionState) -> None:
        rt = self.runtime
        recovered: list[str] = []

        if state.label == "start_screen":
            rt.handled_start_screen = False
            recovered.append("start_screen retry enabled")
        elif state.label == "choice_screen":
            rt.handled_choice_without_legend = False
            recovered.append("choice_screen retry enabled")
        elif state.label in {"card_reward", "dream_found"}:
            rt.waiting_after_reward_action = False
            recovered.append("reward action retry enabled")
        elif state.label == "legend_choice":
            rt.waiting_after_legend = False
            rt.pending_legend_confirm_point = None
            recovered.append("legend retry enabled")
        elif state.label == "unknown" and transition.action_name in {
            "team_enter",
            "team_enter_fallback",
            "dialog_advance_burst",
            "legend_dialog_advance",
        }:
            rt.dialog_advance_armed = True
            rt.wait_for_dialog_until = 0.0
            recovered.append("unknown dialog advance re-armed")

        if transition.action_name in {"start_enter"} and state.label == "start_screen":
            rt.handled_start_screen = False
        if transition.action_name in {"no_legend_chain"} and state.label == "choice_screen":
            rt.handled_choice_without_legend = False

        if recovered:
            rt.last_action = 0.0
            rt.next_action_delay = 0.0
            print(
                "RECOVERY: transition timed out; "
                f"current={state.label}; {', '.join(recovered)}; re-running current state.",
                flush=True,
            )
        else:
            print(
                "RECOVERY: transition timed out; no special latch matched, continuing with fresh detection.",
                flush=True,
            )

    def disarm_dialog(self) -> None:
        self.runtime.dialog_advance_armed = False
        self.runtime.wait_for_dialog_until = 0.0

    def reset_common(
        self,
        *,
        legend: bool = True,
        reward: bool = True,
        choice: bool = True,
        start: bool = True,
        dialog: bool = True,
    ) -> None:
        rt = self.runtime
        if dialog:
            self.disarm_dialog()
        if legend:
            rt.waiting_after_legend = False
            rt.pending_legend_confirm_point = None
        if reward:
            rt.waiting_after_reward_action = False
        if choice:
            rt.handled_choice_without_legend = False
        if start:
            rt.handled_start_screen = False

    def wait_visual(
        self,
        frame: np.ndarray,
        action_name: str,
        expected_labels: set[str],
    ) -> None:
        cfg = self.config
        wait_visual_change(
            cfg.detector,
            frame,
            cfg.monitor_index,
            cfg.capture_method,
            cfg.stop_keys,
            cfg.stop_file,
            cfg.post_click_wait,
            action_name=action_name,
            expected_labels=expected_labels,
        )

    def handle_after_legend_confirm(self, frame: np.ndarray, monitor: dict) -> None:
        cfg = self.config
        rt = self.runtime
        if not cfg.act:
            return

        waited = wait_for_detected_state(
            cfg.detector,
            cfg.monitor_index,
            cfg.capture_method,
            cfg.stop_keys,
            cfg.stop_file,
            {"card_reward", "dream_found", "unknown"},
            cfg.post_click_wait,
            "legend_confirm_to_reward_or_dialog",
        )
        if not waited:
            return

        _, next_monitor, next_state = waited
        if next_state.label in {"card_reward", "dream_found"}:
            return

        print("legend confirm reached unknown/dialog; advancing dialog before reward.")
        dialog_clicks = checked_dialog_advance(
            cfg.detector,
            next_monitor or monitor,
            cfg.monitor_index,
            cfg.capture_method,
            cfg.stop_keys,
            cfg.stop_file,
            cfg.act,
            max_taps=LEGEND_DIALOG_TAPS,
            tap_delay=LEGEND_DIALOG_TAP_DELAY,
            prefix="legend dialog",
        )
        rt.click_count += dialog_clicks
        if dialog_clicks > 0:
            self.expect_transition(
                "legend_dialog_advance",
                "unknown",
                {"card_reward", "dream_found", "choice_screen", "legend_choice"},
                max(cfg.post_click_wait, LEGEND_DIALOG_TAPS * LEGEND_DIALOG_TAP_DELAY + 1.0),
            )

    def handle_state(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        if state.dream_card:
            return self.handle_dream_card()
        if state.card_reward:
            return self.handle_card_reward(frame, monitor, state, now)
        if state.return_confirm:
            return self.handle_return_confirm(frame, monitor, state, now)
        if state.legend_choice:
            return self.handle_legend_choice(frame, monitor, state, now)
        if state.choice_card:
            return self.handle_choice_screen(frame, monitor, state, now)
        if state.flee_button:
            return self.handle_flee_screen(frame, monitor, state, now)
        if state.team_enter:
            return self.handle_team_enter(monitor, state, now)
        if state.start_screen and start_match_looks_like_team_fallback(state, frame.shape):
            return self.handle_team_enter_fallback(monitor, state, now)
        if state.start_screen:
            return self.handle_start_screen(frame, monitor, state, now)
        return self.handle_unknown(monitor, state, now)

    def handle_dream_card(self) -> bool:
        self.disarm_dialog()
        print("dream card found; stopping automation loop.")
        return False

    def handle_card_reward(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(legend=True, reward=False, choice=True, start=True, dialog=True)
        if not rt.waiting_after_reward_action and REWARD_SETTLE_BEFORE_ACTION > 0:
            print(f"reward screen: settle {REWARD_SETTLE_BEFORE_ACTION:.1f}s before checking cards.")
            if sleep_interruptible(REWARD_SETTLE_BEFORE_ACTION, cfg.stop_keys, cfg.stop_file):
                return False
            frame, monitor = screen_shot(cfg.monitor_index, cfg.capture_method)
            state = cfg.detector.detect(frame)
            print_state("reward settle", state)
            if state.dream_card:
                print("dream card found after reward settle; stopping automation loop.")
                return False
            if not state.card_reward:
                self.mark_action(time.time(), cfg.interval)
                return True
        if rt.waiting_after_reward_action:
            print("reward screen already handled once; waiting for screen to change.")
            self.mark_action(now, DELAY_REWARD_ALREADY_HANDLED)
            return not sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file)

        if cfg.no_dream_action == "retry-top-right":
            retry_point = state.top_right_menu.center if state.top_right_menu else None
            print_action("no dream card: click top-right retry/menu area", CLICK_RETRY_TOP_RIGHT, cfg.act)
            if cfg.act:
                if retry_point:
                    click_frame_point(retry_point, monitor)
                else:
                    click_norm(CLICK_RETRY_TOP_RIGHT, monitor)
                rt.click_count += 1
                self.wait_visual(frame, "reward_retry", {"flee_screen", "start_screen", "team_screen", "unknown"})
        elif cfg.no_dream_action == "confirm":
            print_action("no dream card: click confirm", CLICK_CONFIRM, cfg.act)
            if cfg.act:
                click_norm(CLICK_CONFIRM, monitor)
                rt.click_count += 1
                self.wait_visual(frame, "reward_confirm", {"start_screen", "team_screen", "unknown"})
        else:
            print("no dream card: reward screen detected; no action configured.")

        rt.waiting_after_reward_action = True
        self.mark_action(now, DELAY_AFTER_REWARD_ACTION)
        return True

    def handle_return_confirm(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        self.reset_common()
        confirm_point = state.return_confirm.point_at(0.68, 0.50)
        print_action(f"return confirm: click confirm at {confirm_point}", CLICK_CONFIRM, cfg.act)
        if cfg.act:
            click_frame_point(confirm_point, monitor)
            self.runtime.click_count += 1
            self.wait_visual(frame, "return_confirm", {"start_screen", "team_screen", "unknown"})
        self.mark_action(now, DELAY_AFTER_RETURN_CONFIRM)
        return True

    def handle_legend_choice(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(legend=False, reward=True, choice=True, start=True, dialog=True)
        if rt.waiting_after_legend:
            if rt.pending_legend_confirm_point is None:
                rt.pending_legend_confirm_point = choice_confirm_point_for(state.legend_choice.center, frame.shape)
            print_action(f"legend option selected: click check at {rt.pending_legend_confirm_point}", CLICK_CONFIRM, cfg.act)
            if cfg.act:
                click_frame_point(rt.pending_legend_confirm_point, monitor)
                rt.click_count += 1
                self.handle_after_legend_confirm(frame, monitor)
            rt.waiting_after_legend = False
            rt.pending_legend_confirm_point = None
            self.mark_action(now, DELAY_AFTER_LEGEND_CONFIRM)
            return True

        print_action(f"click matched legend option at {state.legend_choice.center}", CLICK_CHOICE_RIGHT, cfg.act)
        if cfg.act:
            rt.pending_legend_confirm_point = choice_confirm_point_for(state.legend_choice.center, frame.shape)
            click_frame_point(state.legend_choice.center, monitor)
            rt.click_count += 1
            if sleep_interruptible(LEGEND_CONFIRM_DELAY, cfg.stop_keys, cfg.stop_file):
                return False
            print_action(f"legend option confirm: click check at {rt.pending_legend_confirm_point}", CLICK_CONFIRM, cfg.act)
            click_frame_point(rt.pending_legend_confirm_point, monitor)
            rt.click_count += 1
            self.handle_after_legend_confirm(frame, monitor)
        else:
            rt.pending_legend_confirm_point = choice_confirm_point_for(state.legend_choice.center, frame.shape)
        rt.waiting_after_legend = False
        rt.pending_legend_confirm_point = None
        self.mark_action(now, DELAY_AFTER_LEGEND_CONFIRM)
        return True

    def handle_choice_screen(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(reward=True, choice=False, start=True, dialog=True)
        if rt.handled_choice_without_legend:
            print("choice screen without legend already handled once; waiting for screen to change.")
            self.mark_action(now, DELAY_CHOICE_ALREADY_HANDLED)
            return not sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file)
        if CHOICE_SETTLE_BEFORE_ACTION > 0:
            print(f"choice screen: settle {CHOICE_SETTLE_BEFORE_ACTION:.1f}s before treating it as no-legend.")
            if sleep_interruptible(CHOICE_SETTLE_BEFORE_ACTION, cfg.stop_keys, cfg.stop_file):
                return False
            frame, monitor = screen_shot(cfg.monitor_index, cfg.capture_method)
            settled_state = cfg.detector.detect(frame)
            print_state("choice settle", settled_state)
            if settled_state.legend_choice:
                return self.handle_legend_choice(frame, monitor, settled_state, time.time())
            if settled_state.label != "choice_screen":
                print(f"choice screen changed during settle: handling {settled_state.label} instead.")
                return self.handle_state(frame, monitor, settled_state, time.time())

        chain_clicks = fast_abandon_no_legend(
            cfg.detector,
            frame,
            monitor,
            cfg.monitor_index,
            cfg.capture_method,
            cfg.stop_keys,
            cfg.stop_file,
            cfg.act,
        )
        rt.click_count += chain_clicks
        if chain_clicks > 0:
            self.expect_transition(
                "no_legend_chain",
                "choice_screen",
                {"return_confirm", "start_screen", "team_screen", "unknown"},
                max(cfg.post_click_wait, CHAIN_MENU_TO_FLEE_TIMEOUT + CHAIN_FLEE_TO_CONFIRM_TIMEOUT + 1.0),
            )
        rt.handled_choice_without_legend = True
        self.mark_action(now, DELAY_AFTER_NO_LEGEND_CHAIN)
        return True

    def handle_flee_screen(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        self.reset_common()
        flee_point = state.flee_button.point_at(0.72, 0.50)
        print_action(f"flee screen: click flee text area at {flee_point}", CLICK_ADVANCE, cfg.act)
        if cfg.act:
            click_frame_point(flee_point, monitor)
            self.runtime.click_count += 1
            self.wait_visual(frame, "flee", {"return_confirm", "unknown"})
        self.mark_action(now, DELAY_AFTER_FLEE)
        return True

    def handle_team_enter(self, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(dialog=False)
        click_point = state.team_enter.point_at(*BUTTON_TEXT_POINT)
        print_action(f"team screen: click enter at {click_point}", CLICK_START_ENTER, cfg.act)
        if cfg.act:
            click_frame_point(click_point, monitor)
            rt.click_count += 1
            self.expect_transition(
                "team_enter",
                state.label,
                {"unknown", "choice_screen", "legend_choice", "card_reward", "dream_found"},
                max(cfg.wait_after_team_enter + 2.0, cfg.post_click_wait),
            )
        rt.wait_for_dialog_until = time.time() + cfg.wait_after_team_enter
        rt.dialog_advance_armed = True
        print(f"team enter clicked; dialog advance armed after {cfg.wait_after_team_enter:.1f}s.")
        self.mark_action(now, min(max(cfg.wait_after_team_enter, cfg.interval), 1.0))
        return True

    def handle_team_enter_fallback(self, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(dialog=False)
        print(
            "start template matched the lower-left team row; treating this as team screen "
            f"fallback. match={state.start_screen.center if state.start_screen else None}"
        )
        print_action("team screen fallback: click fixed enter", CLICK_TEAM_ENTER, cfg.act)
        if cfg.act:
            click_norm(CLICK_TEAM_ENTER, monitor, duration=FAST_CLICK_DURATION)
            rt.click_count += 1
            self.expect_transition(
                "team_enter_fallback",
                state.label,
                {"unknown", "choice_screen", "legend_choice", "card_reward", "dream_found"},
                max(cfg.wait_after_team_enter + 2.0, cfg.post_click_wait),
            )
        rt.wait_for_dialog_until = time.time() + cfg.wait_after_team_enter
        rt.dialog_advance_armed = True
        print(f"team fallback clicked; dialog advance armed after {cfg.wait_after_team_enter:.1f}s.")
        self.mark_action(now, min(max(cfg.wait_after_team_enter, cfg.interval), 1.0))
        return True

    def handle_start_screen(self, frame: np.ndarray, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(choice=True, start=False, dialog=True)
        if rt.handled_start_screen:
            print("start screen already clicked once; waiting for screen to change.")
            self.mark_action(now, DELAY_START_ALREADY_HANDLED)
            return not sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file)
        click_point = state.start_screen.point_at(*BUTTON_TEXT_POINT)
        if cfg.fast_start_to_team_enabled:
            quick_clicks = fast_start_to_team(
                monitor,
                cfg.stop_keys,
                cfg.stop_file,
                cfg.act,
                first_point=None,
            )
            rt.click_count += quick_clicks
            if cfg.act:
                if quick_clicks > 0:
                    self.expect_transition(
                        "start_enter",
                        state.label,
                        {"team_screen", "unknown"},
                        max(cfg.post_click_wait, 2.0),
                    )
                print("start enter clicked; waiting for team screen recognition.")
        else:
            print_action(f"start screen: click enter at {click_point}", CLICK_START_ENTER, cfg.act)
            if cfg.act:
                click_frame_point(click_point, monitor)
                rt.click_count += 1
                self.wait_visual(frame, "start_enter", {"team_screen", "unknown"})
        rt.handled_start_screen = True
        self.mark_action(now, DELAY_AFTER_START_ENTER)
        return True

    def handle_unknown(self, monitor: dict, state: DetectionState, now: float) -> bool:
        cfg = self.config
        rt = self.runtime
        self.reset_common(dialog=False)
        dialog_detected = state.dialog_indicator is not None
        if not cfg.advance_on_unknown and not dialog_detected:
            print("unknown screen: no click. Pass --advance-on-unknown to enable blind advance clicks.")
            self.mark_action(now, DELAY_UNKNOWN_IDLE)
            return True
        if not rt.dialog_advance_armed and not dialog_detected:
            print("unknown screen: dialog advance is not armed; waiting for a team enter first.")
            self.mark_action(now, DELAY_UNKNOWN_IDLE)
            return not sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file)
        if rt.wait_for_dialog_until > now:
            remaining = rt.wait_for_dialog_until - now
            print(f"unknown screen: waiting {remaining:.1f}s before dialog advance burst.")
            self.mark_action(now, min(max(remaining, cfg.interval), 1.0))
            return not sleep_interruptible(cfg.interval, cfg.stop_keys, cfg.stop_file)
        rt.wait_for_dialog_until = 0.0
        if dialog_detected and not rt.dialog_advance_armed:
            print(f"unknown screen: dialog indicator detected at {state.dialog_indicator.center}; advancing once.")
        burst_clicks = fast_advance_unknown(
            cfg.detector,
            monitor,
            cfg.monitor_index,
            cfg.capture_method,
            cfg.stop_keys,
            cfg.stop_file,
            cfg.act,
            max_taps=1 if dialog_detected and not rt.dialog_advance_armed else DIALOG_BURST_MAX_TAPS,
            mode="checked" if dialog_detected and not rt.dialog_advance_armed else DIALOG_BURST_MODE,
            max_total_clicks=(cfg.max_clicks - rt.click_count) if cfg.max_clicks > 0 else None,
        )
        rt.click_count += burst_clicks
        if burst_clicks > 0:
            self.expect_transition(
                "dialog_advance_burst",
                "unknown",
                {"choice_screen", "legend_choice", "card_reward", "dream_found", "flee_screen", "return_confirm"},
                max(2.0, cfg.interval * 4),
            )
        rt.dialog_advance_armed = False
        self.mark_action(now, DELAY_AFTER_UNKNOWN_BURST)
        return True


def run_live(
    detector: CznDetector,
    act: bool,
    interval: float,
    no_dream_action: str,
    max_seconds: float,
    monitor_index: int,
    advance_on_unknown: bool,
    stop_key: str,
    max_clicks: int,
    stop_file: Path | None,
    post_click_wait: float,
    capture_method: str,
    fast_start_to_team_enabled: bool,
    log_interval: float,
    wait_after_team_enter: float,
    dialog_burst_mode: str,
) -> None:
    stop_keys = parse_stop_keys(stop_key)
    LiveSession(
        LiveConfig(
            detector=detector,
            act=act,
            interval=interval,
            no_dream_action=no_dream_action,
            max_seconds=max_seconds,
            monitor_index=monitor_index,
            advance_on_unknown=advance_on_unknown,
            stop_keys=stop_keys,
            max_clicks=max_clicks,
            stop_file=stop_file,
            post_click_wait=post_click_wait,
            capture_method=capture_method,
            fast_start_to_team_enabled=fast_start_to_team_enabled,
            log_interval=log_interval,
            wait_after_team_enter=wait_after_team_enter,
            dialog_burst_mode=dialog_burst_mode,
        )
    ).run()

