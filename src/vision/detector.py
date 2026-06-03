from __future__ import annotations

import dataclasses
import json
from typing import Iterable

import cv2
import numpy as np

from core.models import Box, DetectionState, MatchResult, detection_state
from core.settings import *


@dataclasses.dataclass(frozen=True)
class TemplateMatchSpec:
    name: str
    path: str
    roi: Box
    threshold: float


@dataclasses.dataclass(frozen=True)
class StateMatchSpec:
    label: str
    mode: str
    priority: int
    templates: tuple[TemplateMatchSpec, ...]


class CznDetector:
    def __init__(self, template_dir: Path | None = None, wide_match_scales: bool = False) -> None:
        visible_templates = app_install_dir() / "templates"
        bundled_templates = app_base_dir() / "templates"
        self.template_dir = template_dir or (visible_templates if visible_templates.exists() else bundled_templates)
        self.match_scale_factors = WIDE_MATCH_SCALE_FACTORS if wide_match_scales else FAST_MATCH_SCALE_FACTORS
        self._warned_aspect_sizes: set[tuple[int, int]] = set()
        self._template_cache: dict[str, np.ndarray] = {}
        self.state_specs = self._load_state_manifest()

    def _load_state_manifest(self) -> tuple[StateMatchSpec, ...]:
        path = self.template_dir / "state_manifest.json"
        if not path.exists():
            print(f"warning: state manifest missing: {path}; detector will return unknown.", flush=True)
            return ()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print(f"warning: failed to load state manifest {path}: {exc}", flush=True)
            return ()
        states = data.get("states", [])
        if not isinstance(states, list):
            print(f"warning: state manifest states must be a list: {path}", flush=True)
            return ()

        specs: list[StateMatchSpec] = []
        for index, raw_state in enumerate(states):
            if not isinstance(raw_state, dict):
                print(f"warning: state manifest entry #{index} must be an object", flush=True)
                continue
            try:
                specs.append(self._parse_state_spec(raw_state))
            except Exception as exc:
                print(f"warning: invalid state manifest entry #{index}: {exc}", flush=True)
        specs.sort(key=lambda spec: spec.priority, reverse=True)
        print(f"loaded state manifest: {path} states={len(specs)}", flush=True)
        return tuple(specs)

    def _parse_state_spec(self, data: dict) -> StateMatchSpec:
        label = str(data["label"]).strip()
        mode = str(data.get("mode", "all")).strip().lower()
        priority = int(data.get("priority", 100))
        raw_templates = data.get("templates", [])
        if mode not in {"all", "any"}:
            raise ValueError("mode must be all or any")
        if not label:
            raise ValueError("label is required")
        if not isinstance(raw_templates, list) or not raw_templates:
            raise ValueError("templates must be a non-empty list")
        templates = tuple(self._parse_template_spec(label, item) for item in raw_templates)
        return StateMatchSpec(label=label, mode=mode, priority=priority, templates=templates)

    @staticmethod
    def _parse_template_spec(label: str, data: object) -> TemplateMatchSpec:
        if not isinstance(data, dict):
            raise ValueError("template spec must be an object")
        path = str(data["path"]).strip()
        name = str(data.get("name") or Path(path).stem or label).strip()
        raw_roi = data.get("roi", [0.0, 0.0, 1.0, 1.0])
        if not isinstance(raw_roi, list | tuple) or len(raw_roi) != 4:
            raise ValueError("template roi must be [x1, y1, x2, y2]")
        roi = Box(float(raw_roi[0]), float(raw_roi[1]), float(raw_roi[2]), float(raw_roi[3]))
        threshold = float(data.get("threshold", 0.80))
        if not path:
            raise ValueError("template path is required")
        if not (0.0 <= roi.x1 < roi.x2 <= 1.0 and 0.0 <= roi.y1 < roi.y2 <= 1.0):
            raise ValueError("template roi values must be normalized and ordered")
        if not 0.0 < threshold <= 1.0:
            raise ValueError("template threshold must be between 0 and 1")
        return TemplateMatchSpec(name=name, path=path, roi=roi, threshold=threshold)

    def _load_template(self, path: str) -> np.ndarray | None:
        cached = self._template_cache.get(path)
        if cached is not None:
            return cached
        full_path = self.template_dir / path
        image = cv2.imdecode(np.fromfile(str(full_path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            print(f"warning: template not found or unreadable: {full_path}", flush=True)
            return None
        self._template_cache[path] = image
        return image

    def detect(self, frame_bgr: np.ndarray, warn_aspect: bool = True) -> DetectionState:
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        height, width = frame_bgr.shape[:2]
        if warn_aspect:
            self._warn_if_unexpected_aspect(width, height)

        for state_spec in self.state_specs:
            matches = self._match_state(frame_gray, state_spec)
            if matches:
                return detection_state(label=state_spec.label, matches=matches)
        return detection_state()

    def _match_state(self, frame_gray: np.ndarray, state_spec: StateMatchSpec) -> dict[str, MatchResult]:
        matches: dict[str, MatchResult] = {}
        for template_spec in state_spec.templates:
            template = self._load_template(template_spec.path)
            if template is None:
                if state_spec.mode == "all":
                    return {}
                continue
            match = self._match_in_roi(
                frame_gray,
                template,
                template_spec.roi,
                template_spec.name,
                threshold=template_spec.threshold,
            )
            if match:
                matches[template_spec.name] = match
            elif state_spec.mode == "all":
                return {}
        if state_spec.mode == "any" and not matches:
            return {}
        return matches

    def _match_in_roi(
        self,
        frame_gray: np.ndarray,
        template_gray: np.ndarray,
        roi: Box,
        name: str,
        threshold: float,
    ) -> MatchResult | None:
        height, width = frame_gray.shape[:2]
        x1, y1, x2, y2 = roi.to_pixels(width, height)
        haystack = frame_gray[y1:y2, x1:x2]
        if haystack.size == 0:
            return None

        base_scale = self._template_scale(width, height)
        best_score = -1.0
        best_loc = (0, 0)
        best_size = (0, 0)
        for scale_factor in self.match_scale_factors:
            scale = base_scale * scale_factor
            template_width = max(8, int(round(template_gray.shape[1] * scale)))
            template_height = max(8, int(round(template_gray.shape[0] * scale)))
            if template_width >= haystack.shape[1] or template_height >= haystack.shape[0]:
                continue
            template = cv2.resize(template_gray, (template_width, template_height), interpolation=cv2.INTER_AREA)
            score_map = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
            _, max_score, _, max_loc = cv2.minMaxLoc(score_map)
            if max_score > best_score:
                best_score = float(max_score)
                best_loc = max_loc
                best_size = (template_width, template_height)

        if best_score < threshold:
            return None
        match_x, match_y = best_loc
        template_width, template_height = best_size
        return MatchResult(
            name=name,
            score=float(best_score),
            box=(
                x1 + match_x,
                y1 + match_y,
                x1 + match_x + template_width,
                y1 + match_y + template_height,
            ),
        )

    def _template_scale(self, width: int, height: int) -> float:
        return min(width / BASE_W, height / BASE_H)

    def _warn_if_unexpected_aspect(self, width: int, height: int) -> None:
        size = (width, height)
        if size in self._warned_aspect_sizes:
            return
        self._warned_aspect_sizes.add(size)
        aspect = width / max(1, height)
        if abs(aspect - BASE_ASPECT) > ASPECT_TOLERANCE:
            print(
                f"warning: capture aspect {width}x{height} differs from base {BASE_W}x{BASE_H}; "
                "same-ratio 16:9 fullscreen captures are expected.",
                flush=True,
            )


def read_image(path: Path) -> np.ndarray:
    frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return frame


def iter_video_frames(path: Path, every_sec: float) -> Iterable[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else 0.0
    timestamp = 0.0
    while timestamp <= duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        yield timestamp, frame
        timestamp += every_sec
    cap.release()


def annotate(frame: np.ndarray, state: DetectionState) -> np.ndarray:
    out = frame.copy()
    for match in state.matches.values():
        x1, y1, x2, y2 = match.box
        color = (180, 120, 255)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 4)
        cv2.putText(
            out,
            f"{state.label}:{match.name} {match.score:.3f}",
            (x1, max(30, y1 - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            color,
            3,
            cv2.LINE_AA,
        )
    return out


def save_image(path: Path, frame: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 94])
    if not ok:
        raise RuntimeError(f"failed to encode image: {path}")
    buf.tofile(str(path))


def run_image(detector: CznDetector, image_path: Path, out_dir: Path | None) -> None:
    frame = read_image(image_path)
    state = detector.detect(frame)
    print_state(image_path.name, state)
    if out_dir:
        save_image(out_dir / f"{image_path.stem}_annotated.jpg", annotate(frame, state))


def run_video(detector: CznDetector, video_path: Path, every_sec: float, out_dir: Path | None) -> None:
    for timestamp, frame in iter_video_frames(video_path, every_sec):
        state = detector.detect(frame)
        if state.label != "unknown":
            print_state(f"{timestamp:7.2f}s", state)
            if out_dir:
                save_image(out_dir / f"video_{timestamp:07.2f}s_{state.label}.jpg", annotate(frame, state))


def print_state(prefix: str, state: DetectionState) -> None:
    parts = [prefix, state.label]
    for name, match in sorted(state.matches.items()):
        parts.append(f"{name}={match.score:.3f}@{match.center}")
    try:
        print(" | ".join(parts), flush=True)
    except OSError:
        pass


def start_match_looks_like_team_fallback(state: DetectionState, frame_shape: tuple[int, ...]) -> bool:
    match = state.match("team_enter") or state.match("start_screen")
    if not match:
        return False
    height, width = frame_shape[:2]
    cx, cy = match.center
    return (cx / max(1, width)) <= TEAM_FALLBACK_MATCH_MAX_X and (cy / max(1, height)) >= TEAM_FALLBACK_MATCH_MIN_Y
