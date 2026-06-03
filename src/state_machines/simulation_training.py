from __future__ import annotations

from state_machines.workflow import (
    CountRunAction,
    ManifestAction,
    WorkflowDefinition,
    WorkflowState,
    WorkflowTransition,
)


def simulation_greed_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        name="模拟-战斗训练-记忆碎片-贪婪与执着",
        initial="main",
        states={
            "main": WorkflowState(
                "main",
                transitions=(
                    WorkflowTransition(
                        '点击“模拟”',
                        "simulate",
                        (ManifestAction("main", "click_simulation"),),
                    ),
                ),
            ),
            "simulate": WorkflowState(
                "simulate",
                transitions=(
                    WorkflowTransition(
                        '点击“战斗训练”',
                        "battle_training",
                        (ManifestAction("simulate", "click_battle_training"),),
                    ),
                ),
            ),
            "battle_training": WorkflowState(
                "battle_training",
                transitions=(
                    WorkflowTransition(
                        '点击“记忆碎片”',
                        "memory_fragment",
                        (ManifestAction("battle_training", "click_memory_fragment"),),
                    ),
                ),
            ),
            "memory_fragment": WorkflowState(
                "memory_fragment",
                transitions=(
                    WorkflowTransition(
                        '右侧下拉到最底部, 点击“贪婪与执着”',
                        "greed",
                        (
                            ManifestAction("memory_fragment", "scroll_to_bottom"),
                            ManifestAction("memory_fragment", "click_greed"),
                        ),
                    ),
                ),
            ),
            "greed": WorkflowState(
                "greed",
                transitions=(
                    WorkflowTransition(
                        '点击“出击”',
                        "greed_game",
                        (ManifestAction("greed", "click_sortie"),),
                    ),
                ),
            ),
            "greed_game": WorkflowState(
                "greed_game",
                transitions=(
                    WorkflowTransition(
                        "点击右上角按钮启动自动战斗",
                        "greed_game_auto_started",
                        (ManifestAction("greed_game", "click_auto_battle"),),
                    ),
                ),
            ),
            "greed_game_auto_started": WorkflowState(
                "greed_game_auto_started",
                transitions=(
                    WorkflowTransition(
                        "等待自动战斗结束",
                        "settlement",
                        (ManifestAction("greed_game", "wait_battle_finish"),),
                    ),
                ),
            ),
            "settlement": WorkflowState(
                "settlement",
                transitions=(
                    WorkflowTransition(
                        "确认",
                        "greed",
                        (
                            ManifestAction("settlement", "click_confirm"),
                            CountRunAction(),
                        ),
                    ),
                ),
            ),
        },
    )
