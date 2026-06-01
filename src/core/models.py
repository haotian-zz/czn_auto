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
    legend_choice: MatchResult | None
    dream_card: MatchResult | None
    card_reward: MatchResult | None
    choice_card: MatchResult | None
    return_confirm: MatchResult | None
    start_screen: MatchResult | None
    top_right_menu: MatchResult | None
    flee_button: MatchResult | None
    team_enter: MatchResult | None
    dialog_indicator: MatchResult | None

    @property
    def label(self) -> str:
        if self.dream_card:
            return "dream_found"
        if self.card_reward:
            return "card_reward"
        if self.return_confirm:
            return "return_confirm"
        if self.legend_choice:
            return "legend_choice"
        if self.choice_card:
            return "choice_screen"
        if self.flee_button:
            return "flee_screen"
        if self.team_enter:
            return "team_screen"
        if self.start_screen:
            return "start_screen"
        return "unknown"


def detection_state(
    legend_choice: MatchResult | None = None,
    dream_card: MatchResult | None = None,
    card_reward: MatchResult | None = None,
    choice_card: MatchResult | None = None,
    return_confirm: MatchResult | None = None,
    start_screen: MatchResult | None = None,
    top_right_menu: MatchResult | None = None,
    flee_button: MatchResult | None = None,
    team_enter: MatchResult | None = None,
    dialog_indicator: MatchResult | None = None,
) -> DetectionState:
    return DetectionState(
        legend_choice=legend_choice,
        dream_card=dream_card,
        card_reward=card_reward,
        choice_card=choice_card,
        return_confirm=return_confirm,
        start_screen=start_screen,
        top_right_menu=top_right_menu,
        flee_button=flee_button,
        team_enter=team_enter,
        dialog_indicator=dialog_indicator,
    )
