from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            max(0, min(width, int(round(self.x1 * width)))),
            max(0, min(height, int(round(self.y1 * height)))),
            max(0, min(width, int(round(self.x2 * width)))),
            max(0, min(height, int(round(self.y2 * height)))),
        )


@dataclasses.dataclass
class MatchResult:
    name: str
    score: float
    box: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def point_at(self, rx: float, ry: float) -> tuple[int, int]:
        x1, y1, x2, y2 = self.box
        return (int(round(x1 + (x2 - x1) * rx)), int(round(y1 + (y2 - y1) * ry)))


@dataclasses.dataclass
class DetectionState:
    label: str = "unknown"
    matches: dict[str, MatchResult] = dataclasses.field(default_factory=dict)

    @property
    def best_match(self) -> MatchResult | None:
        if not self.matches:
            return None
        return max(self.matches.values(), key=lambda match: match.score)

    def match(self, name: str) -> MatchResult | None:
        return self.matches.get(name)

    @property
    def custom(self) -> MatchResult | None:
        return self.best_match

    @property
    def custom_label(self) -> str | None:
        return None if self.label == "unknown" else self.label

    # These properties keep older automation modules importable while the
    # detector itself uses only manifest-driven labels and match names.
    @property
    def legend_choice(self) -> MatchResult | None:
        return self.match("legend_choice")

    @property
    def dream_card(self) -> MatchResult | None:
        return self.match("dream_found") or self.match("dream_card")

    @property
    def card_reward(self) -> MatchResult | None:
        return self.match("card_reward")

    @property
    def choice_card(self) -> MatchResult | None:
        return self.match("choice_screen") or self.match("choice_card")

    @property
    def return_confirm(self) -> MatchResult | None:
        return self.match("return_confirm")

    @property
    def start_screen(self) -> MatchResult | None:
        return self.match("start_screen")

    @property
    def top_right_menu(self) -> MatchResult | None:
        return self.match("top_right_menu")

    @property
    def flee_button(self) -> MatchResult | None:
        return self.match("flee_screen") or self.match("flee_button")

    @property
    def team_enter(self) -> MatchResult | None:
        return self.match("team_screen") or self.match("team_enter")

    @property
    def dialog_indicator(self) -> MatchResult | None:
        return self.match("dialog_indicator")


def detection_state(
    label: str = "unknown",
    matches: dict[str, MatchResult] | None = None,
    **legacy_matches: MatchResult | None,
) -> DetectionState:
    state_matches = dict(matches or {})
    for name, match in legacy_matches.items():
        if match is not None:
            state_matches[name] = match
            if label == "unknown":
                label = name
    return DetectionState(label=label, matches=state_matches)
