from __future__ import annotations

import argparse
import time
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


STATE_CAPTURE_DIRS = {
    "main": "common/main",
    "dialog": "common/dialog",
    "combat": "common/combat",
    "settlement": "common/battle/settlement",
    "start_screen": "common/dream/start_screen",
    "team_screen": "common/dream/team_screen",
    "choice_screen": "common/dream/choice_screen",
    "legend_choice": "common/dream/legend_choice",
    "card_reward": "common/dream/card_reward",
    "return_confirm": "common/return_confirm",
    "flee_screen": "common/flee_screen",
    "simulate": "simulate",
    "battle_training": "simulate/battle_training",
    "growth": "simulate/battle_training/growth",
    "main_combatant": "simulate/battle_training/main_combatant",
    "support_combatant": "simulate/battle_training/support_combatant",
    "potential": "simulate/battle_training/potential",
    "memory_fragment": "simulate/battle_training/memory",
    "challenge": "simulate/battle_training/challenge",
    "greed": "simulate/battle_training/memory/greed",
    "greed_game": "simulate/battle_training/memory/greed/in_game",
}


def capture_dir_for(state_name: str, root: Path) -> Path:
    key = state_name.strip().replace("\\", "/").strip("/")
    relative = STATE_CAPTURE_DIRS.get(key, key)
    return root / relative / "captures"


def print_known_states() -> None:
    for name, relative in sorted(STATE_CAPTURE_DIRS.items()):
        print(f"{name:24s} -> templates/{relative}/captures")


def limit_detector_to_state(detector: CznDetector, state_name: str | None) -> None:
    if not state_name:
        return
    filtered = tuple(spec for spec in detector.state_specs if spec.label == state_name)
    if not filtered:
        return
    detector.state_specs = filtered
    print(f"state check filter: only testing state={state_name}", flush=True)


def print_state_template_debug(detector: CznDetector, frame, state_name: str | None) -> None:
    if not state_name:
        return
    spec = detector.state_spec(state_name)
    if spec is None:
        print(f"state template debug: state not found in manifest: {state_name}", flush=True)
        return
    for template in spec.templates:
        score, box = detector.template_best_score(frame, template)
        box_text = "none" if box is None else str(box)
        print(
            "state template debug: "
            f"state={state_name} template={template.name} path={template.path} "
            f"threshold={template.threshold:.3f} best_score={score:.3f} box={box_text} "
            f"roi={[template.roi.x1, template.roi.y1, template.roi.x2, template.roi.y2]}",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one fresh frame and classify the current CZN state.")
    parser.add_argument("--config", type=Path, default=default_config_file())
    parser.add_argument("--no-user-config", action="store_true")
    parser.add_argument("--monitor")
    parser.add_argument("--capture-method", choices=sorted(CAPTURE_METHODS))
    parser.add_argument("--save-state", help="Save the fresh screenshot under templates/<state>/captures.")
    parser.add_argument("--templates-root", type=Path, default=None, help="Root directory for saved state screenshots. Defaults to app templates/.")
    parser.add_argument("--list-states", action="store_true", help="List known --save-state names and their directories.")
    parser.add_argument("--no-detect", action="store_true", help="Only capture/save the screenshot; skip template-based detection.")
    parser.add_argument("--test-action", help="After detecting the current state, test this manifest action template without clicking.")
    args = parser.parse_args()
    if args.list_states:
        print_known_states()
        return
    if not args.no_user_config:
        apply_user_config(args.config, create_missing=False)
    monitor_value = args.monitor if args.monitor is not None else cfg.MONITOR_INDEX
    capture_method = args.capture_method if args.capture_method is not None else cfg.CAPTURE_METHOD
    args.monitor = resolve_monitor_index(monitor_value)

    root = app_install_dir()
    frame, monitor = screen_shot(args.monitor, capture_method)
    print(f"capture={capture_method} monitor={monitor}")
    state = None
    if args.test_action and args.no_detect:
        parser.error("--test-action requires detection; remove --no-detect")

    if not args.no_detect:
        detector = CznDetector()
        limit_detector_to_state(detector, args.save_state)
        state = detector.detect(frame)
        print_state("fresh_state", state)
        if state.label == "unknown":
            print_state_template_debug(detector, frame, args.save_state)

    debug_dir = root / "debug_live"
    save_image(debug_dir / "fresh_state.jpg", frame)
    if state is not None:
        save_image(debug_dir / "fresh_state_annotated.jpg", annotate(frame, state))

    if args.save_state:
        templates_root = args.templates_root or (root / "templates")
        out_dir = capture_dir_for(args.save_state, templates_root)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        raw_path = out_dir / f"{stamp}_raw.jpg"
        save_image(raw_path, frame)
        print(f"saved capture: {raw_path}")
        if state is not None:
            annotated_path = out_dir / f"{stamp}_{state.label}_annotated.jpg"
            save_image(annotated_path, annotate(frame, state))
            print(f"saved annotated capture: {annotated_path}")

    if args.test_action and state is not None:
        action = detector.action_spec(state.label, args.test_action)
        if action is None:
            print(f"action missing: state={state.label} action={args.test_action}")
            return
        print(f"action found: state={state.label} action={args.test_action} type={action.kind} target={action.target}")
        if action.kind == "click_template":
            if action.template is None:
                print("action template missing")
                return
            match = detector.match_template(frame, action.template)
            if match is None:
                print(f"action template not matched: {action.template.name}")
                return
            base_point = match.point_at(*action.click_at)
            click_point = (base_point[0] + action.click_offset[0], base_point[1] + action.click_offset[1])
            print(
                f"action template matched: {match.name} score={match.score:.3f} "
                f"box={match.box} base_point={base_point} click_offset={action.click_offset} click_point={click_point}"
            )
            templates_root = args.templates_root or (root / "templates")
            out_dir = capture_dir_for(args.save_state or state.label, templates_root)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            action_state = type(state)(label=state.label, matches={f"action_{args.test_action}": match})
            action_path = out_dir / f"{stamp}_{state.label}_{args.test_action}_action_annotated.jpg"
            save_image(action_path, annotate(frame, action_state))
            print(f"saved action annotated capture: {action_path}")
        elif action.kind == "wheel":
            print(f"wheel action: point={action.point} notches={action.notches} repeats={action.repeats}")
        elif action.kind == "wait":
            print(f"wait action: seconds={action.seconds}")


if __name__ == "__main__":
    main()
