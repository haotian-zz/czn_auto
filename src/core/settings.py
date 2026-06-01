from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import os
import platform
import sys
import time
from pathlib import Path

from core.models import Box


BASE_W = 3840
BASE_H = 2160
BASE_ASPECT = BASE_W / BASE_H
ASPECT_TOLERANCE = 0.03
APP_VERSION = "0.1.7"
_DXGI_CAMERAS: dict[int, object] = {}
_FORCED_CAPTURE_AREAS: dict[int, dict] = {}
_RUN_LOG_HANDLE = None
_RUN_LOG_STDOUT = None
_RUN_LOG_STDERR = None
_DEFAULT_UNRAISABLEHOOK = sys.unraisablehook

INPUT_BACKEND_SENDINPUT = "sendinput"
INPUT_BACKEND_POSTMESSAGE = "postmessage"
INPUT_BACKEND_POSTMESSAGE_ACTIVATE = "postmessage_activate"
INPUT_BACKENDS = {
    INPUT_BACKEND_SENDINPUT,
    INPUT_BACKEND_POSTMESSAGE,
    INPUT_BACKEND_POSTMESSAGE_ACTIVATE,
}

CAPTURE_METHOD_AUTO = "auto"
CAPTURE_METHOD_DXGI = "dxgi"
CAPTURE_METHOD_MSS = "mss"
CAPTURE_METHODS = {
    CAPTURE_METHOD_AUTO,
    CAPTURE_METHOD_DXGI,
    CAPTURE_METHOD_MSS,
}
DEFAULT_MONITOR = "auto"
DEFAULT_CAPTURE_METHOD = CAPTURE_METHOD_AUTO

WM_ACTIVATE = 0x0006
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WA_ACTIVE = 1
MK_LBUTTON = 0x0001


class TeeStream:
    def __init__(self, stream, log_file) -> None:
        self.stream = stream
        self.log_file = log_file

    def write(self, data: str) -> int:
        for target in (self.stream, self.log_file):
            try:
                target.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for target in (self.stream, self.log_file):
            try:
                target.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        try:
            return self.stream.isatty()
        except Exception:
            return False

    @property
    def encoding(self) -> str:
        return getattr(self.stream, "encoding", "utf-8")

    def __getattr__(self, name: str):
        return getattr(self.stream, name)


def install_unraisable_filter() -> None:
    def hook(unraisable) -> None:
        exc = unraisable.exc_value
        obj = unraisable.object
        obj_text = repr(obj)
        if (
            isinstance(exc, OSError)
            and "access violation writing" in str(exc).lower()
            and ("comtypes" in obj_text or "_compointer_base" in obj_text)
        ):
            print(
                f"warning: suppressed known comtypes cleanup warning: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return
        _DEFAULT_UNRAISABLEHOOK(unraisable)

    sys.unraisablehook = hook


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def app_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "CZN Auto" / "logs"
    return Path.home() / "AppData" / "Local" / "CZN Auto" / "logs"


def default_config_dir() -> Path:
    return app_install_dir()


def default_config_file() -> Path:
    return default_config_dir() / "config.json"


def default_log_file() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return default_log_dir() / f"czn_auto_{stamp}_{os.getpid()}.log"


def _close_run_log() -> None:
    global _RUN_LOG_HANDLE, _RUN_LOG_STDOUT, _RUN_LOG_STDERR
    if _RUN_LOG_HANDLE is None:
        return
    try:
        print(f"run log closed: {_RUN_LOG_HANDLE.name}", flush=True)
    except Exception:
        pass
    try:
        sys.stdout = _RUN_LOG_STDOUT or sys.stdout
        sys.stderr = _RUN_LOG_STDERR or sys.stderr
        _RUN_LOG_HANDLE.close()
    except Exception:
        pass
    _RUN_LOG_HANDLE = None


def setup_run_log(log_file: Path | None) -> Path | None:
    global _RUN_LOG_HANDLE, _RUN_LOG_STDOUT, _RUN_LOG_STDERR
    if _RUN_LOG_HANDLE is not None:
        return Path(_RUN_LOG_HANDLE.name)

    path = log_file or default_log_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _RUN_LOG_HANDLE = path.open("a", encoding="utf-8", buffering=1)
    except OSError as exc:
        print(f"warning: failed to open run log {path}: {exc}", file=sys.stderr, flush=True)
        return None

    _RUN_LOG_STDOUT = sys.stdout
    _RUN_LOG_STDERR = sys.stderr
    sys.stdout = TeeStream(sys.stdout, _RUN_LOG_HANDLE)
    sys.stderr = TeeStream(sys.stderr, _RUN_LOG_HANDLE)
    atexit.register(_close_run_log)
    return path


def json_safe_args(args: argparse.Namespace) -> str:
    values = {}
    for key, value in vars(args).items():
        if isinstance(value, Path):
            values[key] = str(value)
        else:
            values[key] = value
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def print_run_header(args: argparse.Namespace, log_path: Path | None) -> None:
    print("=" * 80)
    print(f"CZN Auto run started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"app_version={APP_VERSION}")
    print(f"log_file={log_path if log_path else 'disabled/unavailable'}")
    print(f"cwd={Path.cwd()}")
    print(f"app_base={app_base_dir()}")
    print(f"app_install_dir={app_install_dir()}")
    print(f"frozen={bool(getattr(sys, 'frozen', False))}")
    print(f"python={sys.version.split()[0]} executable={sys.executable}")
    print(f"platform={platform.platform()}")
    print(f"argv={sys.argv!r}")
    print(f"args={json_safe_args(args)}")
    print(f"config_messages={json.dumps(CONFIG_MESSAGES, ensure_ascii=False)}")
    print(f"display_environment={json.dumps(display_environment(), ensure_ascii=False, sort_keys=True)}")
    print(f"runtime_defaults={json.dumps(runtime_timing_profile(), ensure_ascii=False, sort_keys=True)}")
    print(f"click_defaults={json.dumps(runtime_click_profile(), ensure_ascii=False, sort_keys=True)}")
    print("=" * 80)


def display_environment() -> dict:
    user32 = ctypes.windll.user32
    info: dict[str, object] = {
        "primary_width": user32.GetSystemMetrics(0),
        "primary_height": user32.GetSystemMetrics(1),
        "virtual_left": user32.GetSystemMetrics(76),
        "virtual_top": user32.GetSystemMetrics(77),
        "virtual_width": user32.GetSystemMetrics(78),
        "virtual_height": user32.GetSystemMetrics(79),
        "monitor_count": user32.GetSystemMetrics(80),
    }
    try:
        info["system_dpi"] = user32.GetDpiForSystem()
    except Exception:
        pass
    try:
        import mss

        mss_cls = getattr(mss, "MSS", None) or getattr(mss, "mss")
        with mss_cls() as sct:
            info["mss_monitors"] = [dict(monitor) for monitor in sct.monitors]
    except Exception as exc:
        info["mss_monitors_error"] = repr(exc)
    return info


def runtime_timing_profile() -> dict:
    return {
        "live_loop_interval": LIVE_LOOP_INTERVAL,
        "live_log_interval": LIVE_LOG_INTERVAL,
        "post_click_wait": POST_CLICK_WAIT,
        "wait_after_team_enter": WAIT_AFTER_TEAM_ENTER_BEFORE_DIALOG,
        "dialog_burst_max_taps": DIALOG_BURST_MAX_TAPS,
        "dialog_burst_tap_delay": DIALOG_BURST_TAP_DELAY,
        "dialog_burst_mode": DIALOG_BURST_MODE,
        "dialog_burst_rapid_postcheck": DIALOG_BURST_RAPID_POSTCHECK,
        "dialog_burst_fallback_taps": DIALOG_BURST_FALLBACK_TAPS,
        "dialog_burst_fallback_tap_delay": DIALOG_BURST_FALLBACK_TAP_DELAY,
        "legend_dialog_taps": LEGEND_DIALOG_TAPS,
        "legend_dialog_tap_delay": LEGEND_DIALOG_TAP_DELAY,
        "start_to_team_burst_taps": START_TO_TEAM_BURST_TAPS,
        "start_to_team_tap_delay": START_TO_TEAM_TAP_DELAY,
        "reward_settle_before_action": REWARD_SETTLE_BEFORE_ACTION,
        "choice_settle_before_action": CHOICE_SETTLE_BEFORE_ACTION,
        "chain_menu_to_flee_delay": CHAIN_MENU_TO_FLEE_DELAY,
        "chain_flee_to_confirm_delay": CHAIN_FLEE_TO_CONFIRM_DELAY,
        "chain_menu_to_flee_timeout": CHAIN_MENU_TO_FLEE_TIMEOUT,
        "chain_flee_to_confirm_timeout": CHAIN_FLEE_TO_CONFIRM_TIMEOUT,
        "chain_after_confirm_delay": CHAIN_AFTER_CONFIRM_DELAY,
        "legend_confirm_delay": LEGEND_CONFIRM_DELAY,
        "fast_click_duration": FAST_CLICK_DURATION,
        "chain_click_duration": CHAIN_CLICK_DURATION,
        "click_move_delay": CLICK_MOVE_DELAY,
        "click_absolute_move_delay": CLICK_ABSOLUTE_MOVE_DELAY,
        "click_after_up_delay": CLICK_AFTER_UP_DELAY,
        "focus_top_delay": FOCUS_TOP_DELAY,
        "focus_foreground_delay": FOCUS_FOREGROUND_DELAY,
        "focus_retry_delay": FOCUS_RETRY_DELAY,
        "visual_change_poll_interval": VISUAL_CHANGE_POLL_INTERVAL,
        "delay_reward_already_handled": DELAY_REWARD_ALREADY_HANDLED,
        "delay_after_reward_action": DELAY_AFTER_REWARD_ACTION,
        "delay_after_return_confirm": DELAY_AFTER_RETURN_CONFIRM,
        "delay_after_no_legend_chain": DELAY_AFTER_NO_LEGEND_CHAIN,
        "delay_choice_already_handled": DELAY_CHOICE_ALREADY_HANDLED,
        "delay_after_flee": DELAY_AFTER_FLEE,
        "delay_after_team_enter": DELAY_AFTER_TEAM_ENTER,
        "delay_start_already_handled": DELAY_START_ALREADY_HANDLED,
        "delay_after_start_enter": DELAY_AFTER_START_ENTER,
        "delay_after_unknown_burst": DELAY_AFTER_UNKNOWN_BURST,
        "delay_unknown_idle": DELAY_UNKNOWN_IDLE,
        "delay_after_legend_confirm": DELAY_AFTER_LEGEND_CONFIRM,
        "click_window_log": LOG_CLICK_WINDOW,
    }


def runtime_click_profile() -> dict:
    return {
        "input_backend": INPUT_BACKEND,
        "restore_cursor_after_click": RESTORE_CURSOR_AFTER_CLICK,
        "target_window_title": INPUT_TARGET_WINDOW_TITLE,
        "advance": CLICK_ADVANCE,
        "choice_right": CLICK_CHOICE_RIGHT,
        "confirm": CLICK_CONFIRM,
        "retry_top_right": CLICK_RETRY_TOP_RIGHT,
        "start_enter": CLICK_START_ENTER,
        "team_enter": CLICK_TEAM_ENTER,
        "button_text_point": BUTTON_TEXT_POINT,
        "chain_flee": CHAIN_FLEE_POINT,
        "chain_return_confirm": CHAIN_RETURN_CONFIRM_POINT,
        "choice_confirm_y": CHOICE_CONFIRM_Y,
        "team_fallback_match_max_x": TEAM_FALLBACK_MATCH_MAX_X,
        "team_fallback_match_min_y": TEAM_FALLBACK_MATCH_MIN_Y,
    }


def set_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


set_dpi_awareness()
install_unraisable_filter()


def _stop_dxgi_cameras() -> None:
    for camera in list(_DXGI_CAMERAS.values()):
        try:
            camera.stop()
        except Exception:
            pass
    _DXGI_CAMERAS.clear()


atexit.register(_stop_dxgi_cameras)


CHOICE_RIGHT_ROI = Box(2440 / BASE_W, 1600 / BASE_H, 3430 / BASE_W, 2050 / BASE_H)
CARD_REWARD_ROI = Box(560 / BASE_W, 470 / BASE_H, 3300 / BASE_W, 920 / BASE_H)

CLICK_ADVANCE = (0.935, 0.855)
CLICK_CHOICE_RIGHT = (0.765, 0.860)
CLICK_CONFIRM = (0.895, 0.945)
CLICK_RETRY_TOP_RIGHT = (0.955, 0.055)
CLICK_START_ENTER = (0.840, 0.905)
CLICK_TEAM_ENTER = (0.840, 0.905)
BUTTON_TEXT_POINT = (0.78, 0.52)
TEAM_FALLBACK_MATCH_MAX_X = 0.86
TEAM_FALLBACK_MATCH_MIN_Y = 0.90
CHOICE_CONFIRM_Y = 0.946

# ===== 可调速度参数 =====
# 主循环识别间隔。越小反应越快，也会更吃 CPU/GPU。
LIVE_LOOP_INTERVAL = 0.25
LIVE_LOG_INTERVAL = 1.50
FAST_MATCH_SCALE_FACTORS = (1.0,)
WIDE_MATCH_SCALE_FACTORS = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)

# 一般点击按下到抬起的时间。太小可能被游戏漏掉，太大会拖慢连点。
FAST_CLICK_DURATION = 0.035

# 固定流程里的点击时长，例如“右上角 -> 脱逃 -> 确认”快链。
CHAIN_CLICK_DURATION = 0.04

# 无传说快链固定点击点。这里不做中途识图，按固定流程直接点。
CHAIN_FLEE_POINT = (0.923, 0.920)
CHAIN_RETURN_CONFIRM_POINT = (0.691, 0.652)

# 无传说快链固定间隔：右上角菜单 -> 脱逃 -> 确认。
# 如果漏点，优先稍微加大这两个值；如果稳定，可以继续降低。
CHAIN_MENU_TO_FLEE_DELAY = 0.3
CHAIN_FLEE_TO_CONFIRM_DELAY = 0.2
CHAIN_MENU_TO_FLEE_TIMEOUT = 1.8
CHAIN_FLEE_TO_CONFIRM_TIMEOUT = 1.8

# 点确认后给页面开始跳转的一点时间；后续仍由主循环识别当前位置。
CHAIN_AFTER_CONFIRM_DELAY = 0.20

# 对白页连续点击：最多连点次数。到三选一/奖励等已知状态会提前停。
DIALOG_BURST_MAX_TAPS = 9

# 对白页连续点击：每次点击后的间隔。想更快可以先试 0.08，再低要观察是否漏点。
DIALOG_BURST_TAP_DELAY = 0.4
DIALOG_BURST_MODE = "rapid"
DIALOG_BURST_RAPID_POSTCHECK = 1.0
DIALOG_BURST_FALLBACK_TAPS = 3
DIALOG_BURST_FALLBACK_TAP_DELAY = 0.6
LEGEND_DIALOG_TAPS = 2
LEGEND_DIALOG_TAP_DELAY = 0.4
DIALOG_BURST_STOP_LABELS = {
    "dream_found",
    "card_reward",
    "legend_choice",
    "choice_screen",
    "flee_screen",
    "return_confirm",
    "team_screen",
    "start_screen",
}

# Start-screen click count. Keep this at 1 so the team screen is recognized
# before clicking the team enter button.
START_TO_TEAM_BURST_TAPS = 1
START_TO_TEAM_TAP_DELAY = 0.5
WAIT_AFTER_TEAM_ENTER_BEFORE_DIALOG = 7.0
POST_CLICK_WAIT = 4.0
REWARD_SETTLE_BEFORE_ACTION = 1.5
SAVE_VISUAL_CHANGE_DEBUG = False
LOG_CLICK_WINDOW = False
INPUT_BACKEND = INPUT_BACKEND_POSTMESSAGE_ACTIVATE
RESTORE_CURSOR_AFTER_CLICK = False
INPUT_TARGET_WINDOW_TITLE = "卡厄思梦境"
MONITOR_INDEX = DEFAULT_MONITOR
CAPTURE_METHOD = DEFAULT_CAPTURE_METHOD
_INPUT_TARGET_HWND_CACHE = 0

# 识别等待轮询间隔，用在等待“脱逃页/确认弹窗/回首页”等关键状态。

# 旧的 before/after 调试等待轮询间隔。正常快链较少用到，单步调试会用。
VISUAL_CHANGE_POLL_INTERVAL = 0.20

# 无传说快链兜底等待。当前直接快链不再依赖这两个值，只留给以后调试用。

# 无传说快链兜底等待。当前直接快链不再依赖这两个值，只留给以后调试用。

# 无传说快链：点确认后等回到首页/队伍/加载页的最长时间。

# 传说选项：点选项卡后，等对勾出现/可点的短暂停顿。
LEGEND_CONFIRM_DELAY = 0.20
CHOICE_SETTLE_BEFORE_ACTION = 0.35

# 点击函数内部固定耗时。一次点击大约是：
# CLICK_MOVE_DELAY + CLICK_ABSOLUTE_MOVE_DELAY + duration + CLICK_AFTER_UP_DELAY。
CLICK_MOVE_DELAY = 0.03
CLICK_ABSOLUTE_MOVE_DELAY = 0.02
CLICK_AFTER_UP_DELAY = 0.03

# 窗口抢前台时的等待。正常游戏已经在前台时不会每次都吃满。
FOCUS_TOP_DELAY = 0.05
FOCUS_FOREGROUND_DELAY = 0.12
FOCUS_RETRY_DELAY = 0.05

# 各状态处理完后下一轮识别的短暂停顿。
INITIAL_ACTION_DELAY = 0.20
DELAY_REWARD_ALREADY_HANDLED = 0.30
DELAY_AFTER_REWARD_ACTION = 0.50
DELAY_AFTER_RETURN_CONFIRM = 0.50
DELAY_AFTER_NO_LEGEND_CHAIN = 0.20
DELAY_CHOICE_ALREADY_HANDLED = 0.30
DELAY_AFTER_FLEE = 0.30
DELAY_AFTER_TEAM_ENTER = 0.50
DELAY_START_ALREADY_HANDLED = 0.30
DELAY_AFTER_START_ENTER = 0.50
DELAY_AFTER_UNKNOWN_BURST = 0.05
DELAY_UNKNOWN_IDLE = 0.30
DELAY_AFTER_LEGEND_CONFIRM = 1


CONFIG_MESSAGES: list[str] = []
CONFIG_BINDINGS = {
    "click_points": {
        "advance": ("CLICK_ADVANCE", "point"),
        "choice_right": ("CLICK_CHOICE_RIGHT", "point"),
        "confirm": ("CLICK_CONFIRM", "point"),
        "retry_top_right": ("CLICK_RETRY_TOP_RIGHT", "point"),
        "start_enter": ("CLICK_START_ENTER", "point"),
        "team_enter": ("CLICK_TEAM_ENTER", "point"),
        "button_text_point": ("BUTTON_TEXT_POINT", "point"),
        "chain_flee": ("CHAIN_FLEE_POINT", "point"),
        "chain_return_confirm": ("CHAIN_RETURN_CONFIRM_POINT", "point"),
        "choice_confirm_y": ("CHOICE_CONFIRM_Y", "unit_float"),
        "team_fallback_match_max_x": ("TEAM_FALLBACK_MATCH_MAX_X", "unit_float"),
        "team_fallback_match_min_y": ("TEAM_FALLBACK_MATCH_MIN_Y", "unit_float"),
    },
    "timing": {
        "live_loop_interval": ("LIVE_LOOP_INTERVAL", "positive_float"),
        "live_log_interval": ("LIVE_LOG_INTERVAL", "nonnegative_float"),
        "post_click_wait": ("POST_CLICK_WAIT", "nonnegative_float"),
        "wait_after_team_enter": ("WAIT_AFTER_TEAM_ENTER_BEFORE_DIALOG", "nonnegative_float"),
        "reward_settle_before_action": ("REWARD_SETTLE_BEFORE_ACTION", "nonnegative_float"),
        "choice_settle_before_action": ("CHOICE_SETTLE_BEFORE_ACTION", "nonnegative_float"),
        "start_to_team_burst_taps": ("START_TO_TEAM_BURST_TAPS", "nonnegative_int"),
        "start_to_team_tap_delay": ("START_TO_TEAM_TAP_DELAY", "nonnegative_float"),
        "dialog_burst_max_taps": ("DIALOG_BURST_MAX_TAPS", "nonnegative_int"),
        "dialog_burst_tap_delay": ("DIALOG_BURST_TAP_DELAY", "nonnegative_float"),
        "dialog_burst_mode": ("DIALOG_BURST_MODE", "dialog_mode"),
        "dialog_burst_rapid_postcheck": ("DIALOG_BURST_RAPID_POSTCHECK", "nonnegative_float"),
        "dialog_burst_fallback_taps": ("DIALOG_BURST_FALLBACK_TAPS", "nonnegative_int"),
        "dialog_burst_fallback_tap_delay": ("DIALOG_BURST_FALLBACK_TAP_DELAY", "nonnegative_float"),
        "legend_dialog_taps": ("LEGEND_DIALOG_TAPS", "nonnegative_int"),
        "legend_dialog_tap_delay": ("LEGEND_DIALOG_TAP_DELAY", "nonnegative_float"),
        "legend_confirm_delay": ("LEGEND_CONFIRM_DELAY", "nonnegative_float"),
        "chain_menu_to_flee_delay": ("CHAIN_MENU_TO_FLEE_DELAY", "nonnegative_float"),
        "chain_flee_to_confirm_delay": ("CHAIN_FLEE_TO_CONFIRM_DELAY", "nonnegative_float"),
        "chain_menu_to_flee_timeout": ("CHAIN_MENU_TO_FLEE_TIMEOUT", "nonnegative_float"),
        "chain_flee_to_confirm_timeout": ("CHAIN_FLEE_TO_CONFIRM_TIMEOUT", "nonnegative_float"),
        "chain_after_confirm_delay": ("CHAIN_AFTER_CONFIRM_DELAY", "nonnegative_float"),
        "fast_click_duration": ("FAST_CLICK_DURATION", "nonnegative_float"),
        "chain_click_duration": ("CHAIN_CLICK_DURATION", "nonnegative_float"),
        "click_move_delay": ("CLICK_MOVE_DELAY", "nonnegative_float"),
        "click_absolute_move_delay": ("CLICK_ABSOLUTE_MOVE_DELAY", "nonnegative_float"),
        "click_after_up_delay": ("CLICK_AFTER_UP_DELAY", "nonnegative_float"),
        "focus_top_delay": ("FOCUS_TOP_DELAY", "nonnegative_float"),
        "focus_foreground_delay": ("FOCUS_FOREGROUND_DELAY", "nonnegative_float"),
        "focus_retry_delay": ("FOCUS_RETRY_DELAY", "nonnegative_float"),
        "visual_change_poll_interval": ("VISUAL_CHANGE_POLL_INTERVAL", "nonnegative_float"),
        "delay_reward_already_handled": ("DELAY_REWARD_ALREADY_HANDLED", "nonnegative_float"),
        "delay_after_reward_action": ("DELAY_AFTER_REWARD_ACTION", "nonnegative_float"),
        "delay_after_return_confirm": ("DELAY_AFTER_RETURN_CONFIRM", "nonnegative_float"),
        "delay_after_no_legend_chain": ("DELAY_AFTER_NO_LEGEND_CHAIN", "nonnegative_float"),
        "delay_choice_already_handled": ("DELAY_CHOICE_ALREADY_HANDLED", "nonnegative_float"),
        "delay_after_flee": ("DELAY_AFTER_FLEE", "nonnegative_float"),
        "delay_after_team_enter": ("DELAY_AFTER_TEAM_ENTER", "nonnegative_float"),
        "delay_start_already_handled": ("DELAY_START_ALREADY_HANDLED", "nonnegative_float"),
        "delay_after_start_enter": ("DELAY_AFTER_START_ENTER", "nonnegative_float"),
        "delay_after_unknown_burst": ("DELAY_AFTER_UNKNOWN_BURST", "nonnegative_float"),
        "delay_unknown_idle": ("DELAY_UNKNOWN_IDLE", "nonnegative_float"),
        "delay_after_legend_confirm": ("DELAY_AFTER_LEGEND_CONFIRM", "nonnegative_float"),
    },
    "input": {
        "backend": ("INPUT_BACKEND", "input_backend"),
        "restore_cursor_after_click": ("RESTORE_CURSOR_AFTER_CLICK", "bool"),
        "target_window_title": ("INPUT_TARGET_WINDOW_TITLE", "string"),
    },
    "runtime": {
        "monitor": ("MONITOR_INDEX", "monitor"),
        "capture_method": ("CAPTURE_METHOD", "capture_method"),
    },
}

_RUNTIME_SYNC_MODULES = {
    "actions.common",
    "commands.cli",
    "system.io_system",
    "state_machines.live.session",
    "vision.detector",
}


def set_runtime_value(name: str, value: object) -> None:
    globals()[name] = value
    for module_name in _RUNTIME_SYNC_MODULES:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            setattr(module, name, value)


def default_user_config() -> dict:
    return {
        "_说明": "坐标都是相对当前截图的比例，左上角是 [0, 0]，右下角是 [1, 1]。时间单位是秒。",
        "_建议": "先只小幅调整一个值。改坏了可以删除本文件，程序会重新生成默认配置。",
        "click_points": {
            "_说明": "常用点击位置。一般只需要改 start_enter/team_enter/advance。",
            "advance": list(CLICK_ADVANCE),
            "choice_right": list(CLICK_CHOICE_RIGHT),
            "confirm": list(CLICK_CONFIRM),
            "retry_top_right": list(CLICK_RETRY_TOP_RIGHT),
            "start_enter": list(CLICK_START_ENTER),
            "team_enter": list(CLICK_TEAM_ENTER),
            "button_text_point": list(BUTTON_TEXT_POINT),
            "chain_flee": list(CHAIN_FLEE_POINT),
            "chain_return_confirm": list(CHAIN_RETURN_CONFIRM_POINT),
            "choice_confirm_y": CHOICE_CONFIRM_Y,
            "team_fallback_match_max_x": TEAM_FALLBACK_MATCH_MAX_X,
            "team_fallback_match_min_y": TEAM_FALLBACK_MATCH_MIN_Y,
        },
        "timing": {
            "_说明": "流程等待和连点参数。机器慢就优先加 wait_after_team_enter、post_click_wait、reward_settle_before_action。",
            "live_loop_interval": LIVE_LOOP_INTERVAL,
            "live_log_interval": LIVE_LOG_INTERVAL,
            "post_click_wait": POST_CLICK_WAIT,
            "wait_after_team_enter": WAIT_AFTER_TEAM_ENTER_BEFORE_DIALOG,
            "reward_settle_before_action": REWARD_SETTLE_BEFORE_ACTION,
            "choice_settle_before_action": CHOICE_SETTLE_BEFORE_ACTION,
            "start_to_team_burst_taps": START_TO_TEAM_BURST_TAPS,
            "start_to_team_tap_delay": START_TO_TEAM_TAP_DELAY,
            "dialog_burst_max_taps": DIALOG_BURST_MAX_TAPS,
            "dialog_burst_tap_delay": DIALOG_BURST_TAP_DELAY,
            "dialog_burst_mode": DIALOG_BURST_MODE,
            "dialog_burst_rapid_postcheck": DIALOG_BURST_RAPID_POSTCHECK,
            "dialog_burst_fallback_taps": DIALOG_BURST_FALLBACK_TAPS,
            "dialog_burst_fallback_tap_delay": DIALOG_BURST_FALLBACK_TAP_DELAY,
            "legend_dialog_taps": LEGEND_DIALOG_TAPS,
            "legend_dialog_tap_delay": LEGEND_DIALOG_TAP_DELAY,
            "legend_confirm_delay": LEGEND_CONFIRM_DELAY,
            "chain_menu_to_flee_delay": CHAIN_MENU_TO_FLEE_DELAY,
            "chain_flee_to_confirm_delay": CHAIN_FLEE_TO_CONFIRM_DELAY,
            "chain_menu_to_flee_timeout": CHAIN_MENU_TO_FLEE_TIMEOUT,
            "chain_flee_to_confirm_timeout": CHAIN_FLEE_TO_CONFIRM_TIMEOUT,
            "chain_after_confirm_delay": CHAIN_AFTER_CONFIRM_DELAY,
            "fast_click_duration": FAST_CLICK_DURATION,
            "chain_click_duration": CHAIN_CLICK_DURATION,
            "click_move_delay": CLICK_MOVE_DELAY,
            "click_absolute_move_delay": CLICK_ABSOLUTE_MOVE_DELAY,
            "click_after_up_delay": CLICK_AFTER_UP_DELAY,
            "focus_top_delay": FOCUS_TOP_DELAY,
            "focus_foreground_delay": FOCUS_FOREGROUND_DELAY,
            "focus_retry_delay": FOCUS_RETRY_DELAY,
            "visual_change_poll_interval": VISUAL_CHANGE_POLL_INTERVAL,
            "delay_reward_already_handled": DELAY_REWARD_ALREADY_HANDLED,
            "delay_after_reward_action": DELAY_AFTER_REWARD_ACTION,
            "delay_after_return_confirm": DELAY_AFTER_RETURN_CONFIRM,
            "delay_after_no_legend_chain": DELAY_AFTER_NO_LEGEND_CHAIN,
            "delay_choice_already_handled": DELAY_CHOICE_ALREADY_HANDLED,
            "delay_after_flee": DELAY_AFTER_FLEE,
            "delay_after_team_enter": DELAY_AFTER_TEAM_ENTER,
            "delay_start_already_handled": DELAY_START_ALREADY_HANDLED,
            "delay_after_start_enter": DELAY_AFTER_START_ENTER,
            "delay_after_unknown_burst": DELAY_AFTER_UNKNOWN_BURST,
            "delay_unknown_idle": DELAY_UNKNOWN_IDLE,
            "delay_after_legend_confirm": DELAY_AFTER_LEGEND_CONFIRM,
        },
        "input": {
            "_说明": "输入方式。sendinput 是默认真实鼠标点击；postmessage/postmessage_activate 是实验后台消息点击，可能被游戏忽略。",
            "backend": INPUT_BACKEND,
            "restore_cursor_after_click": RESTORE_CURSOR_AFTER_CLICK,
            "target_window_title": INPUT_TARGET_WINDOW_TITLE,
        },
        "runtime": {
            "_说明": "运行环境。monitor 默认 auto，会按 target_window_title 自动选择游戏所在屏幕；capture_method 默认 auto，优先使用更适合多屏/窗口模式的 mss。",
            "monitor": MONITOR_INDEX,
            "capture_method": CAPTURE_METHOD,
        },
    }


def write_default_config(path: Path, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(default_user_config(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _coerce_config_value(value: object, kind: str, label: str) -> object:
    if kind == "point":
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise ValueError(f"{label} must be [x, y]")
        x = float(value[0])
        y = float(value[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"{label} point values must be between 0 and 1")
        return (x, y)
    if kind == "unit_float":
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{label} must be between 0 and 1")
        return number
    if kind == "positive_float":
        number = float(value)
        if number <= 0:
            raise ValueError(f"{label} must be greater than 0")
        return number
    if kind == "nonnegative_float":
        number = float(value)
        if number < 0:
            raise ValueError(f"{label} must be >= 0")
        return number
    if kind == "nonnegative_int":
        number = int(value)
        if number < 0:
            raise ValueError(f"{label} must be >= 0")
        return number
    if kind == "dialog_mode":
        text = str(value)
        if text not in {"rapid", "checked"}:
            raise ValueError(f"{label} must be rapid or checked")
        return text
    if kind == "input_backend":
        text = str(value).strip().lower().replace("-", "_")
        if text not in INPUT_BACKENDS:
            raise ValueError(f"{label} must be one of {', '.join(sorted(INPUT_BACKENDS))}")
        return text
    if kind == "capture_method":
        text = str(value).strip().lower().replace("-", "_")
        if text not in CAPTURE_METHODS:
            raise ValueError(f"{label} must be one of {', '.join(sorted(CAPTURE_METHODS))}")
        return text
    if kind == "monitor":
        if isinstance(value, int):
            if value < 0:
                raise ValueError(f"{label} must be auto or a monitor index >= 0")
            return value
        text = str(value).strip().lower()
        if text in {"auto", "target", "window"}:
            return "auto"
        try:
            index = int(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be auto or a monitor index") from exc
        if index < 0:
            raise ValueError(f"{label} must be auto or a monitor index >= 0")
        return index
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"{label} must be true or false")
    if kind == "string":
        return str(value).strip()
    raise ValueError(f"unknown config type {kind}")


def apply_user_config(path: Path, create_missing: bool = True) -> None:
    if create_missing and not path.exists():
        try:
            write_default_config(path)
            CONFIG_MESSAGES.append(f"created default config: {path}")
        except OSError as exc:
            CONFIG_MESSAGES.append(f"warning: failed to create config {path}: {exc}")
            return
    if not path.exists():
        CONFIG_MESSAGES.append(f"user config disabled or missing: {path}")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        CONFIG_MESSAGES.append(f"warning: failed to read config {path}: {exc}")
        return
    if not isinstance(data, dict):
        CONFIG_MESSAGES.append(f"warning: config root must be an object: {path}")
        return

    applied: list[str] = []
    for section, bindings in CONFIG_BINDINGS.items():
        section_data = data.get(section, {})
        if section_data is None:
            continue
        if not isinstance(section_data, dict):
            CONFIG_MESSAGES.append(f"warning: config section {section} must be an object")
            continue
        for key, value in section_data.items():
            if key.startswith("_"):
                continue
            binding = bindings.get(key)
            if not binding:
                CONFIG_MESSAGES.append(f"warning: unknown config key ignored: {section}.{key}")
                continue
            global_name, kind = binding
            try:
                set_runtime_value(global_name, _coerce_config_value(value, kind, f"{section}.{key}"))
            except Exception as exc:
                CONFIG_MESSAGES.append(f"warning: invalid config value ignored: {section}.{key}: {exc}")
                continue
            applied.append(f"{section}.{key}")
    CONFIG_MESSAGES.append(f"loaded config: {path} ({len(applied)} values applied)")


VK_CODES = {
    "esc": 0x1B,
    "end": 0x23,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f12": 0x7B,
    "pause": 0x13,
}
