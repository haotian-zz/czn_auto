from __future__ import annotations

from typing import Iterable

import cv2
import numpy as np

from core.models import Box, DetectionState, MatchResult, detection_state
from core.settings import *
class CznDetector:
    def __init__(self, template_dir: Path | None = None, wide_match_scales: bool = False) -> None:
        visible_templates = app_install_dir() / "templates"
        bundled_templates = app_base_dir() / "templates"
        self.template_dir = template_dir or (visible_templates if visible_templates.exists() else bundled_templates)
        self.match_scale_factors = WIDE_MATCH_SCALE_FACTORS if wide_match_scales else FAST_MATCH_SCALE_FACTORS
        self._warned_aspect_sizes: set[tuple[int, int]] = set()
        self.legend_template = self._load_template("legend_word.jpg")
        self.legend_wide_template = self._load_template("legend_word_wide.jpg")
        self.dream_template = self._load_template("dream_border_title.jpg")
        self.card_reward_template = self._load_template("card_reward_title.jpg")
        self.start_enter_template = self._load_template("start_enter_button.jpg")
        self.choice_glow_template = self._load_template("choice_bottom_glow.jpg")
        self.top_right_menu_template = self._load_template("combat_top_right_menu.jpg")
        self.flee_button_template = self._load_template("flee_button.jpg")
        self.team_enter_template = self._load_template("team_enter_button.jpg")
        self.return_confirm_template = self._load_template("return_confirm_button.jpg")

    def _load_template(self, name: str) -> np.ndarray:
        path = self.template_dir / name
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"template not found or unreadable: {path}")
        return image

    def detect(self, frame_bgr: np.ndarray, warn_aspect: bool = True) -> DetectionState:
        frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        h, w = frame_bgr.shape[:2]
        if warn_aspect:
            self._warn_if_unexpected_aspect(w, h)
        dream = self._match_in_roi(
            frame_gray,
            self.dream_template,
            CARD_REWARD_ROI,
            "dream_border_title",
            threshold=0.78,
        )
        if dream:
            return detection_state(dream_card=dream)

        card_reward = self._match_in_roi(
            frame_gray,
            self.card_reward_template,
            Box(0.38, 0.06, 0.62, 0.20),
            "card_reward_title",
            threshold=0.72,
        )
        if card_reward:
            top_right_menu = self._match_in_roi(
                frame_gray,
                self.top_right_menu_template,
                Box(0.85, 0.00, 0.995, 0.11),
                "top_right_menu",
                threshold=0.70,
            )
            return detection_state(card_reward=card_reward, top_right_menu=top_right_menu)

        return_confirm = self._match_in_roi(
            frame_gray,
            self.return_confirm_template,
            Box(0.40, 0.56, 0.86, 0.76),
            "return_confirm_button",
            threshold=0.78,
        )
        if return_confirm:
            return detection_state(return_confirm=return_confirm)

        legend = self._best_match(
            frame_gray=frame_gray,
            templates=[
                ("legend_word", self.legend_template),
                ("legend_word_wide", self.legend_wide_template),
            ],
            roi=CHOICE_RIGHT_ROI,
            threshold=0.72,
        )
        if legend:
            return detection_state(legend_choice=legend)

        team_enter = self._match_in_roi(
            frame_gray,
            self.team_enter_template,
            Box(0.74, 0.84, 0.995, 0.995),
            "team_enter_button",
            threshold=0.74,
        )
        if team_enter:
            return detection_state(team_enter=team_enter)

        start_screen = self._match_in_roi(
            frame_gray,
            self.start_enter_template,
            Box(0.70, 0.82, 0.995, 0.99),
            "start_enter_button",
            threshold=0.72,
        )
        if start_screen:
            return detection_state(start_screen=start_screen)

        choice_card = self._detect_choice_anchors(frame_gray, allow_layout=False)
        if choice_card:
            return detection_state(choice_card=choice_card)

        dialog_indicator = self._detect_dialog_indicator(frame_gray)
        if dialog_indicator:
            return detection_state(dialog_indicator=dialog_indicator)

        choice_card = self._detect_choice_anchors(frame_gray, allow_layout=True)
        if choice_card:
            return detection_state(choice_card=choice_card)

        flee_button = self._match_in_roi(
            frame_gray,
            self.flee_button_template,
            Box(0.70, 0.82, 0.995, 0.995),
            "flee_button",
            threshold=0.72,
        )
        if flee_button:
            return detection_state(flee_button=flee_button)

        return detection_state()

    def _detect_choice_anchors(self, frame_gray: np.ndarray, allow_layout: bool = True) -> MatchResult | None:
        h, w = frame_gray.shape[:2]
        glow_rois = [
            Box(0.12, 0.74, 0.38, 0.998),
            Box(0.36, 0.74, 0.64, 0.998),
            Box(0.62, 0.74, 0.90, 0.998),
        ]
        matches: list[MatchResult] = []
        for index, roi in enumerate(glow_rois, start=1):
            match = self._match_in_roi(
                frame_gray,
                self.choice_glow_template,
                roi,
                f"choice_glow_{index}",
                threshold=0.55,
            )
            if match:
                matches.append(match)
        if len(matches) >= 3:
            x1 = min(match.box[0] for match in matches)
            y1 = min(match.box[1] for match in matches)
            x2 = max(match.box[2] for match in matches)
            y2 = max(match.box[3] for match in matches)
            score = min(match.score for match in matches)
            return MatchResult("choice_glows", score, (x1, y1, x2, y2))

        if not allow_layout:
            return None
        return self._detect_choice_panel_layout(frame_gray)

    def _detect_dialog_indicator(self, frame_gray: np.ndarray) -> MatchResult | None:
        height, width = frame_gray.shape[:2]
        roi = Box(0.90, 0.72, 0.995, 0.985)
        x1, y1, x2, y2 = roi.to_pixels(width, height)
        crop = frame_gray[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        min_w = max(10, width * 0.006)
        max_w = max(28, width * 0.075)
        min_h = max(8, height * 0.006)
        max_h = max(24, height * 0.075)
        best: MatchResult | None = None
        for threshold in (140, 165, 190, 215):
            _, bright = cv2.threshold(crop, threshold, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel, iterations=1)
            contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                bx, by, bw, bh = cv2.boundingRect(contour)
                if not (min_w <= bw <= max_w and min_h <= bh <= max_h):
                    continue
                abs_cx = x1 + bx + bw / 2.0
                abs_cy = y1 + by + bh / 2.0
                if abs_cx < width * 0.90 or abs_cy < height * 0.78 or abs_cy > height * 0.94:
                    continue
                area = cv2.contourArea(contour)
                fill = area / max(1.0, bw * bh)
                if fill < 0.04:
                    continue
                approx = cv2.approxPolyDP(contour, max(2.0, 0.05 * cv2.arcLength(contour, True)), True)
                if not (3 <= len(approx) <= 8):
                    continue

                score = min(0.99, 0.45 + fill + (215 - threshold) / 500.0)
                match = MatchResult("dialog_indicator", score, (x1 + bx, y1 + by, x1 + bx + bw, y1 + by + bh))
                if best is None or match.score > best.score:
                    best = match
        return best

    def _detect_choice_panel_layout(self, frame_gray: np.ndarray) -> MatchResult | None:
        height, width = frame_gray.shape[:2]
        band_y1 = int(height * 0.58)
        band_y2 = int(height * 0.985)
        band = frame_gray[band_y1:band_y2, :]
        if band.size == 0:
            return None

        edges = cv2.Canny(band, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, width // 80), max(3, height // 260)))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        panels: list[tuple[int, int, int, int]] = []
        min_w = width * 0.16
        max_w = width * 0.34
        min_h = height * 0.16
        max_h = height * 0.42
        for contour in contours:
            x, y, panel_w, panel_h = cv2.boundingRect(contour)
            if not (min_w <= panel_w <= max_w and min_h <= panel_h <= max_h):
                continue
            y += band_y1
            if y > height * 0.88:
                continue
            panels.append((x, y, x + panel_w, y + panel_h))

        panels = self._dedupe_choice_panels(panels)
        if len(panels) < 3:
            return None
        panels = self._best_choice_panel_triplet(panels, width, height)
        if panels is None:
            return None

        x1 = min(box[0] for box in panels)
        y1 = min(box[1] for box in panels)
        x2 = max(box[2] for box in panels)
        y2 = max(box[3] for box in panels)
        return MatchResult("choice_panel_layout", 0.50, (x1, y1, x2, y2))

    @staticmethod
    def _dedupe_choice_panels(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
        boxes = sorted(boxes, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)
        kept: list[tuple[int, int, int, int]] = []
        for box in boxes:
            cx = (box[0] + box[2]) / 2.0
            cy = (box[1] + box[3]) / 2.0
            duplicate = False
            for existing in kept:
                ecx = (existing[0] + existing[2]) / 2.0
                ecy = (existing[1] + existing[3]) / 2.0
                if abs(cx - ecx) < max(40, (existing[2] - existing[0]) * 0.35) and abs(cy - ecy) < max(40, (existing[3] - existing[1]) * 0.35):
                    duplicate = True
                    break
            if not duplicate:
                kept.append(box)
        return kept

    @staticmethod
    def _best_choice_panel_triplet(
        boxes: list[tuple[int, int, int, int]],
        width: int,
        height: int,
    ) -> list[tuple[int, int, int, int]] | None:
        best: tuple[float, list[tuple[int, int, int, int]]] | None = None
        for left_index in range(len(boxes) - 2):
            for mid_index in range(left_index + 1, len(boxes) - 1):
                for right_index in range(mid_index + 1, len(boxes)):
                    triplet = sorted(
                        [boxes[left_index], boxes[mid_index], boxes[right_index]],
                        key=lambda box: box[0],
                    )
                    centers = [((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0) for box in triplet]
                    xs = [center[0] / max(1, width) for center in centers]
                    ys = [center[1] / max(1, height) for center in centers]
                    panel_widths = [(box[2] - box[0]) / max(1, width) for box in triplet]
                    if not (xs[0] < 0.42 and 0.30 < xs[1] < 0.70 and xs[2] > 0.58):
                        continue
                    if xs[2] - xs[0] < 0.42:
                        continue
                    if min(ys) < 0.62 or max(ys) - min(ys) > 0.16:
                        continue
                    if max(panel_widths) - min(panel_widths) > 0.12:
                        continue
                    score = (xs[2] - xs[0]) - (max(ys) - min(ys)) - (max(panel_widths) - min(panel_widths))
                    if best is None or score > best[0]:
                        best = (score, triplet)
        return best[1] if best else None

    def _best_match(
        self,
        frame_gray: np.ndarray,
        templates: list[tuple[str, np.ndarray]],
        roi: Box,
        threshold: float,
    ) -> MatchResult | None:
        best: MatchResult | None = None
        for name, template in templates:
            match = self._match_in_roi(frame_gray, template, roi, name, threshold)
            if match and (best is None or match.score > best.score):
                best = match
        return best

    def _match_in_roi(
        self,
        frame_gray: np.ndarray,
        template_gray: np.ndarray,
        roi: Box,
        name: str,
        threshold: float,
    ) -> MatchResult | None:
        h, w = frame_gray.shape[:2]
        x1, y1, x2, y2 = roi.to_pixels(w, h)
        haystack = frame_gray[y1:y2, x1:x2]
        if haystack.size == 0:
            return None

        base_scale = self._template_scale(w, h)
        best_score = -1.0
        best_loc = (0, 0)
        best_size = (0, 0)
        for scale_factor in self.match_scale_factors:
            scale = base_scale * scale_factor
            tw = max(8, int(round(template_gray.shape[1] * scale)))
            th = max(8, int(round(template_gray.shape[0] * scale)))
            if tw >= haystack.shape[1] or th >= haystack.shape[0]:
                continue
            template = cv2.resize(template_gray, (tw, th), interpolation=cv2.INTER_AREA)
            score_map = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
            _, max_score, _, max_loc = cv2.minMaxLoc(score_map)
            if max_score > best_score:
                best_score = float(max_score)
                best_loc = max_loc
                best_size = (tw, th)

        max_score = best_score
        if max_score < threshold:
            return None
        mx, my = best_loc
        tw, th = best_size
        return MatchResult(
            name=name,
            score=float(max_score),
            box=(x1 + mx, y1 + my, x1 + mx + tw, y1 + my + th),
        )

    def _template_scale(self, width: int, height: int) -> float:
        # For same-aspect fullscreen captures, 4K/2K/1080P share one uniform UI scale.
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
    t = 0.0
    while t <= duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        yield t, frame
        t += every_sec
    cap.release()


def annotate(frame: np.ndarray, state: DetectionState) -> np.ndarray:
    out = frame.copy()
    for match, color in (
        (state.legend_choice, (0, 215, 255)),
        (state.choice_card, (255, 160, 0)),
        (state.return_confirm, (0, 165, 255)),
        (state.start_screen, (80, 255, 255)),
        (state.top_right_menu, (255, 120, 255)),
        (state.flee_button, (0, 140, 255)),
        (state.team_enter, (120, 255, 120)),
        (state.dialog_indicator, (255, 255, 120)),
        (state.card_reward, (255, 255, 255)),
        (state.dream_card, (0, 255, 0)),
    ):
        if not match:
            continue
        x1, y1, x2, y2 = match.box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 4)
        cv2.putText(
            out,
            f"{match.name} {match.score:.3f}",
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
    for t, frame in iter_video_frames(video_path, every_sec):
        state = detector.detect(frame)
        if state.label != "unknown":
            print_state(f"{t:7.2f}s", state)
            if out_dir:
                save_image(out_dir / f"video_{t:07.2f}s_{state.label}.jpg", annotate(frame, state))


def print_state(prefix: str, state: DetectionState) -> None:
    parts = [prefix, state.label]
    if state.legend_choice:
        parts.append(f"legend={state.legend_choice.score:.3f}@{state.legend_choice.center}")
    if state.choice_card:
        parts.append(f"choice={state.choice_card.score:.3f}@{state.choice_card.center}")
    if state.return_confirm:
        parts.append(f"return={state.return_confirm.score:.3f}@{state.return_confirm.center}")
    if state.start_screen:
        parts.append(f"start={state.start_screen.score:.3f}@{state.start_screen.center}")
    if state.top_right_menu:
        parts.append(f"menu={state.top_right_menu.score:.3f}@{state.top_right_menu.center}")
    if state.flee_button:
        parts.append(f"flee={state.flee_button.score:.3f}@{state.flee_button.center}")
    if state.team_enter:
        parts.append(f"team={state.team_enter.score:.3f}@{state.team_enter.center}")
    if state.dialog_indicator:
        parts.append(f"dialog={state.dialog_indicator.score:.3f}@{state.dialog_indicator.center}")
    if state.card_reward:
        parts.append(f"reward={state.card_reward.score:.3f}@{state.card_reward.center}")
    if state.dream_card:
        parts.append(f"dream={state.dream_card.score:.3f}@{state.dream_card.center}")
    try:
        print(" | ".join(parts), flush=True)
    except OSError:
        pass


def start_match_looks_like_team_fallback(state: DetectionState, frame_shape: tuple[int, ...]) -> bool:
    if not state.start_screen:
        return False
    h, w = frame_shape[:2]
    cx, cy = state.start_screen.center
    return (cx / max(1, w)) <= TEAM_FALLBACK_MATCH_MAX_X and (cy / max(1, h)) >= TEAM_FALLBACK_MATCH_MIN_Y

