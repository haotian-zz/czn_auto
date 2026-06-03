from __future__ import annotations

from core.settings import *
from state_machines.workflow import (
    ClickAction,
    CountRunAction,
    SetValueAction,
    WaitAction,
    WheelAction,
    WorkflowContext,
    WorkflowDefinition,
    WorkflowState,
    WorkflowTransition,
)


def auto_battle_not_started(ctx: WorkflowContext) -> bool:
    return not bool(ctx.values.get("auto_battle_started", False))


def auto_battle_started(ctx: WorkflowContext) -> bool:
    return bool(ctx.values.get("auto_battle_started", False))


def simulation_greed_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        name="模拟-战斗训练-记忆碎片-贪婪与执着",
        initial="主界面",
        states={
            "主界面": WorkflowState(
                "主界面",
                transitions=(
                    WorkflowTransition(
                        '点击“模拟”',
                        "模拟界面",
                        (ClickAction('点击“模拟”', CLICK_SIMULATION, wait_after=SIM_NAV_WAIT),),
                    ),
                ),
            ),
            "模拟界面": WorkflowState(
                "模拟界面",
                transitions=(
                    WorkflowTransition(
                        '点击“战斗训练”',
                        "战斗训练界面",
                        (ClickAction('点击“战斗训练”', CLICK_BATTLE_TRAINING, wait_after=SIM_NAV_WAIT),),
                    ),
                ),
            ),
            "战斗训练界面": WorkflowState(
                "战斗训练界面",
                transitions=(
                    WorkflowTransition(
                        '点击“记忆碎片”',
                        "记忆碎片界面",
                        (ClickAction('点击“记忆碎片”', CLICK_MEMORY_FRAGMENT_TAB, wait_after=SIM_NAV_WAIT),),
                    ),
                ),
            ),
            "成长界面": WorkflowState("成长界面"),
            "主战员界面": WorkflowState("主战员界面"),
            "辅战员界面": WorkflowState("辅战员界面"),
            "潜能界面": WorkflowState("潜能界面"),
            "挑战界面": WorkflowState("挑战界面"),
            "记忆碎片界面": WorkflowState(
                "记忆碎片界面",
                transitions=(
                    WorkflowTransition(
                        '右侧下拉到最底部, 点击“贪婪与执着”',
                        "贪婪与执着界面",
                        (
                            WheelAction(
                                "记忆碎片右侧列表下拉到底",
                                SCROLL_MEMORY_FRAGMENT_LIST,
                                notches=SIM_MEMORY_FRAGMENT_SCROLL_NOTCHES,
                                repeats=SIM_MEMORY_FRAGMENT_SCROLL_REPEATS,
                                wait_after=SIM_SCROLL_WAIT,
                            ),
                            ClickAction('点击“贪婪与执着”', CLICK_GREED_AND_OBSESSION, wait_after=SIM_NAV_WAIT),
                        ),
                    ),
                ),
            ),
            "贪婪与执着界面": WorkflowState(
                "贪婪与执着界面",
                transitions=(
                    WorkflowTransition(
                        '点击“出击”',
                        "进入游戏界面",
                        (ClickAction('点击“出击”', CLICK_GREED_SORTIE, wait_after=SIM_AFTER_SORTIE_WAIT),),
                    ),
                ),
            ),
            "进入游戏界面": WorkflowState(
                "进入游戏界面",
                transitions=(
                    WorkflowTransition(
                        "自动战斗未启动",
                        "点击右上角齿轮按钮启动自动战斗",
                        (
                            ClickAction(
                                "点击右上角齿轮按钮启动自动战斗",
                                CLICK_AUTO_BATTLE_TOP_RIGHT,
                                wait_after=SIM_AUTO_BATTLE_START_WAIT,
                            ),
                            SetValueAction("auto_battle_started", True),
                        ),
                        guard=auto_battle_not_started,
                    ),
                    WorkflowTransition(
                        "自动战斗已启动",
                        "战斗结算界面",
                        (WaitAction("等待自动战斗结束", SIM_BATTLE_FINISH_WAIT),),
                        guard=auto_battle_started,
                    ),
                ),
            ),
            "点击右上角齿轮按钮启动自动战斗": WorkflowState(
                "点击右上角齿轮按钮启动自动战斗",
                transitions=(
                    WorkflowTransition(
                        "等待自动战斗结束",
                        "战斗结算界面",
                        (WaitAction("等待自动战斗结束", SIM_BATTLE_FINISH_WAIT),),
                    ),
                ),
            ),
            "战斗结算界面": WorkflowState(
                "战斗结算界面",
                transitions=(
                    WorkflowTransition(
                        "确认",
                        "贪婪与执着界面",
                        (
                            ClickAction("战斗结算确认", CLICK_SIM_SETTLEMENT_CONFIRM, wait_after=SIM_SETTLEMENT_CONFIRM_WAIT),
                            CountRunAction(),
                        ),
                    ),
                ),
            ),
        },
    )
