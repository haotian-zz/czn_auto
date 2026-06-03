from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from pathlib import Path

import core.settings as settings
from system.controls import parse_stop_keys, sleep_interruptible, stop_requested
from system.io_system import click_frame_point, click_norm, resolve_monitor_index, screen_shot, wheel_norm
from ui.logging import print_action
from vision.detector import CznDetector, print_state


Guard = Callable[["WorkflowContext"], bool]


@dataclasses.dataclass
class WorkflowConfig:
    act: bool
    monitor_index: int | str
    capture_method: str
    stop_key: str
    stop_file: Path | None
    max_seconds: float = 0.0
    max_clicks: int = 0
    interval: float = settings.LIVE_LOOP_INTERVAL
    runs: int = 0
    detector: CznDetector | None = None


@dataclasses.dataclass
class WorkflowContext:
    config: WorkflowConfig
    monitor: dict
    stop_keys: list[str]
    detector: CznDetector | None = None
    started: float = dataclasses.field(default_factory=time.time)
    clicks: int = 0
    runs_completed: int = 0
    values: dict[str, object] = dataclasses.field(default_factory=dict)

    def should_stop(self) -> bool:
        cfg = self.config
        if stop_requested(self.stop_keys, cfg.stop_file):
            return True
        if cfg.max_seconds > 0 and time.time() - self.started >= cfg.max_seconds:
            print("workflow max seconds reached; exiting.")
            return True
        if cfg.max_clicks > 0 and self.clicks >= cfg.max_clicks:
            print("workflow max clicks reached; exiting.")
            return True
        if cfg.runs > 0 and self.runs_completed >= cfg.runs:
            print("workflow requested run count reached; exiting.")
            return True
        return False

    def wait(self, seconds: float) -> bool:
        if seconds <= 0:
            return not self.should_stop()
        return not sleep_interruptible(seconds, self.stop_keys, self.config.stop_file)


class WorkflowAction:
    def run(self, ctx: WorkflowContext) -> bool:
        raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class ClickAction(WorkflowAction):
    name: str
    point: tuple[float, float]
    duration: float | None = None
    wait_after: float = 0.5

    def run(self, ctx: WorkflowContext) -> bool:
        print_action(self.name, self.point, ctx.config.act)
        if ctx.config.act:
            duration = settings.FAST_CLICK_DURATION if self.duration is None else self.duration
            click_norm(self.point, ctx.monitor, duration=duration)
            ctx.clicks += 1
        return ctx.wait(self.wait_after)


@dataclasses.dataclass(frozen=True)
class WheelAction(WorkflowAction):
    name: str
    point: tuple[float, float]
    notches: int
    repeats: int = 1
    wait_after: float = 0.5

    def run(self, ctx: WorkflowContext) -> bool:
        direction = "down" if self.notches < 0 else "up"
        print(f"{'ACT' if ctx.config.act else 'DRY'}: {self.name} wheel {direction} x{self.repeats} notches={self.notches}", flush=True)
        if ctx.config.act:
            for index in range(self.repeats):
                if ctx.should_stop():
                    return False
                wheel_norm(self.point, ctx.monitor, self.notches)
                if index + 1 < self.repeats and not ctx.wait(self.wait_after):
                    return False
        return ctx.wait(self.wait_after)


@dataclasses.dataclass(frozen=True)
class WaitAction(WorkflowAction):
    name: str
    seconds: float

    def run(self, ctx: WorkflowContext) -> bool:
        print(f"workflow wait: {self.name} {self.seconds:.1f}s", flush=True)
        return ctx.wait(self.seconds)


@dataclasses.dataclass(frozen=True)
class SetValueAction(WorkflowAction):
    key: str
    value: object

    def run(self, ctx: WorkflowContext) -> bool:
        ctx.values[self.key] = self.value
        print(f"workflow context: {self.key}={self.value!r}", flush=True)
        return True


@dataclasses.dataclass(frozen=True)
class CountRunAction(WorkflowAction):
    name: str = "run completed"

    def run(self, ctx: WorkflowContext) -> bool:
        ctx.runs_completed += 1
        print(f"workflow {self.name}: runs_completed={ctx.runs_completed}", flush=True)
        return True


@dataclasses.dataclass(frozen=True)
class ManifestAction(WorkflowAction):
    state_label: str
    action_name: str

    def run(self, ctx: WorkflowContext) -> bool:
        detector = ctx.detector
        if detector is None:
            print(f"manifest action skipped: no detector configured for {self.state_label}.{self.action_name}", flush=True)
            return False

        spec = detector.action_spec(self.state_label, self.action_name)
        if spec is None:
            print(f"manifest action missing: {self.state_label}.{self.action_name}", flush=True)
            return False

        frame, monitor = screen_shot(ctx.config.monitor_index, ctx.config.capture_method)
        ctx.monitor = monitor
        current_state = detector.detect(frame)
        print_state(f"manifest action before {self.state_label}.{self.action_name}", current_state)
        if current_state.label != self.state_label:
            print(
                f"HIGH RISK: manifest action state mismatch: expected={self.state_label}, "
                f"current={current_state.label}; action={self.action_name}; skipping.",
                flush=True,
            )
            return False

        if spec.kind == "click_template":
            if spec.template is None:
                print(f"manifest action invalid: missing template for {self.state_label}.{self.action_name}", flush=True)
                return False
            match = detector.match_template(frame, spec.template)
            if match is None:
                print(
                    f"HIGH RISK: manifest action template not found: "
                    f"{self.state_label}.{self.action_name} template={spec.template.name}",
                    flush=True,
                )
                return False
            click_point = match.point_at(*spec.click_at)
            print_action(
                f"manifest {self.state_label}.{self.action_name} click {match.name} at {click_point}",
                spec.click_at,
                ctx.config.act,
            )
            if ctx.config.act:
                click_frame_point(click_point, monitor, duration=settings.FAST_CLICK_DURATION)
                ctx.clicks += 1
            return ctx.wait(spec.wait_after)

        if spec.kind == "wheel":
            if spec.point is None:
                print(f"manifest action invalid: missing point for {self.state_label}.{self.action_name}", flush=True)
                return False
            direction = "down" if spec.notches < 0 else "up"
            print(
                f"{'ACT' if ctx.config.act else 'DRY'}: manifest {self.state_label}.{self.action_name} "
                f"wheel {direction} x{spec.repeats} notches={spec.notches}",
                flush=True,
            )
            if ctx.config.act:
                for index in range(spec.repeats):
                    if ctx.should_stop():
                        return False
                    wheel_norm(spec.point, monitor, spec.notches)
                    if index + 1 < spec.repeats and not ctx.wait(spec.wait_after):
                        return False
            return ctx.wait(spec.wait_after)

        if spec.kind == "wait":
            print(f"workflow wait: manifest {self.state_label}.{self.action_name} {spec.seconds:.1f}s", flush=True)
            if not ctx.wait(spec.seconds):
                return False
            return ctx.wait(spec.wait_after)

        print(f"manifest action invalid type: {self.state_label}.{self.action_name} type={spec.kind}", flush=True)
        return False


@dataclasses.dataclass(frozen=True)
class WorkflowTransition:
    event: str
    target: str
    actions: tuple[WorkflowAction, ...] = ()
    guard: Guard | None = None


@dataclasses.dataclass(frozen=True)
class WorkflowState:
    name: str
    transitions: tuple[WorkflowTransition, ...] = ()


@dataclasses.dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    initial: str
    states: dict[str, WorkflowState]


class WorkflowRunner:
    def __init__(self, definition: WorkflowDefinition, config: WorkflowConfig) -> None:
        self.definition = definition
        self.config = config

    def run(self) -> None:
        monitor_index = (
            resolve_monitor_index(self.config.monitor_index)
            if isinstance(self.config.monitor_index, str)
            else self.config.monitor_index
        )
        _, monitor = screen_shot(monitor_index, self.config.capture_method)
        ctx = WorkflowContext(
            config=dataclasses.replace(self.config, monitor_index=monitor_index),
            monitor=monitor,
            stop_keys=parse_stop_keys(self.config.stop_key),
            detector=self.config.detector,
        )
        if self.config.stop_file and self.config.stop_file.exists():
            self.config.stop_file.unlink()

        current = self.definition.initial
        print(
            f"workflow started: name={self.definition.name}, initial={current}, "
            f"act={self.config.act}, monitor={monitor_index}, capture={self.config.capture_method}, "
            f"runs={self.config.runs}, max_seconds={self.config.max_seconds}, max_clicks={self.config.max_clicks}",
            flush=True,
        )
        try:
            while not ctx.should_stop():
                state = self.definition.states[current]
                transition = self._select_transition(state, ctx)
                if transition is None:
                    print(f"workflow terminal state reached: {state.name}", flush=True)
                    return
                print(f"workflow transition: {state.name} --{transition.event}--> {transition.target}", flush=True)
                for action in transition.actions:
                    if not action.run(ctx):
                        return
                current = transition.target
                if not ctx.wait(self.config.interval):
                    return
        finally:
            elapsed = time.time() - ctx.started
            print(
                f"workflow stopped: name={self.definition.name}, state={current}, "
                f"elapsed={elapsed:.1f}s, clicks={ctx.clicks}, runs={ctx.runs_completed}",
                flush=True,
            )

    @staticmethod
    def _select_transition(state: WorkflowState, ctx: WorkflowContext) -> WorkflowTransition | None:
        for transition in state.transitions:
            if transition.guard is None or transition.guard(ctx):
                return transition
        return None
