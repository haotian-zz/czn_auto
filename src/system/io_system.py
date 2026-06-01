from __future__ import annotations

import dataclasses

import cv2
import numpy as np
from ctypes import wintypes

from vision.detector import CznDetector
from core.models import DetectionState
from core.settings import _coerce_config_value
from core.settings import *
def _monitor_meta(monitor_index: int) -> dict:
    import mss

    mss_cls = getattr(mss, "MSS", None) or getattr(mss, "mss")
    with mss_cls() as sct:
        if monitor_index < 0 or monitor_index >= len(sct.monitors):
            raise ValueError(f"monitor index {monitor_index} is out of range; available: 0..{len(sct.monitors) - 1}")
        monitor = dict(sct.monitors[monitor_index])
        monitor["index"] = monitor_index
    return monitor


def _available_monitors() -> list[dict]:
    import mss

    mss_cls = getattr(mss, "MSS", None) or getattr(mss, "mss")
    with mss_cls() as sct:
        monitors = []
        for index, monitor in enumerate(sct.monitors):
            item = dict(monitor)
            item["index"] = index
            monitors.append(item)
        return monitors


def _screen_shot_mss(monitor_index: int) -> tuple[np.ndarray, dict]:
    import mss

    mss_cls = getattr(mss, "MSS", None) or getattr(mss, "mss")
    with mss_cls() as sct:
        if monitor_index < 0 or monitor_index >= len(sct.monitors):
            raise ValueError(f"monitor index {monitor_index} is out of range; available: 0..{len(sct.monitors) - 1}")
        grab_monitor = sct.monitors[monitor_index]
        monitor = dict(grab_monitor)
        monitor["index"] = monitor_index
        raw = np.array(sct.grab(grab_monitor))
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR), monitor


def _screen_shot_dxgi(monitor_index: int) -> tuple[np.ndarray, dict]:
    import dxcam

    output_idx = max(0, monitor_index - 1)
    camera = _DXGI_CAMERAS.get(output_idx)
    if camera is None:
        camera = dxcam.create(output_idx=output_idx, output_color="BGR")
        camera.start(target_fps=20, video_mode=True)
        _DXGI_CAMERAS[output_idx] = camera
        time.sleep(0.35)
    frame = None
    deadline = time.time() + 2.0
    while time.time() < deadline:
        frame = camera.get_latest_frame()
        if frame is not None:
            break
        time.sleep(0.03)
    if frame is None:
        frame = camera.grab()
    if frame is None:
        raise RuntimeError("DXGI capture did not return a frame")
    return frame.copy(), _monitor_meta(monitor_index)


def _target_capture_area_on_monitor(monitor: dict) -> dict | None:
    if not INPUT_TARGET_WINDOW_TITLE:
        return None
    hwnd = _cached_title_window_on_monitor(INPUT_TARGET_WINDOW_TITLE, monitor)
    area = _client_area_on_screen(hwnd) if hwnd else None
    if area and _area_monitor_intersection_ratio(area, monitor) >= 0.50:
        return area
    return None


def _crop_frame_to_area(frame: np.ndarray, monitor: dict, area: dict) -> tuple[np.ndarray, dict]:
    mon_left = int(monitor["left"])
    mon_top = int(monitor["top"])
    mon_right = mon_left + int(monitor["width"])
    mon_bottom = mon_top + int(monitor["height"])

    area_left = int(area["left"])
    area_top = int(area["top"])
    area_right = area_left + int(area["width"])
    area_bottom = area_top + int(area["height"])

    left = max(mon_left, area_left)
    top = max(mon_top, area_top)
    right = min(mon_right, area_right)
    bottom = min(mon_bottom, area_bottom)
    if right <= left or bottom <= top:
        return frame, monitor

    x1 = max(0, left - mon_left)
    y1 = max(0, top - mon_top)
    x2 = min(frame.shape[1], right - mon_left)
    y2 = min(frame.shape[0], bottom - mon_top)
    if x2 <= x1 or y2 <= y1:
        return frame, monitor

    cropped_monitor = dict(area)
    cropped_monitor.update(
        {
            "left": left,
            "top": top,
            "width": x2 - x1,
            "height": y2 - y1,
            "source": "target_window_client_capture",
            "capture_monitor": dict(monitor),
        }
    )
    return frame[y1:y2, x1:x2].copy(), cropped_monitor


def _apply_target_window_crop(frame: np.ndarray, monitor: dict) -> tuple[np.ndarray, dict]:
    forced_area = _FORCED_CAPTURE_AREAS.get(int(monitor.get("index", -1)))
    if forced_area:
        return _crop_frame_to_area(frame, monitor, forced_area)
    area = _target_capture_area_on_monitor(monitor)
    if not area:
        return frame, monitor
    return _crop_frame_to_area(frame, monitor, area)


def screen_shot(monitor_index: int, capture_method: str = DEFAULT_CAPTURE_METHOD) -> tuple[np.ndarray, dict]:
    if capture_method == CAPTURE_METHOD_AUTO:
        try:
            frame, monitor = _screen_shot_mss(monitor_index)
            return _apply_target_window_crop(frame, monitor)
        except Exception as exc:
            print(f"MSS capture failed, falling back to dxgi: {exc}", flush=True)
            frame, monitor = _screen_shot_dxgi(monitor_index)
            return _apply_target_window_crop(frame, monitor)
    if capture_method == CAPTURE_METHOD_DXGI:
        try:
            frame, monitor = _screen_shot_dxgi(monitor_index)
            return _apply_target_window_crop(frame, monitor)
        except Exception as exc:
            print(f"DXGI capture failed, falling back to mss: {exc}", flush=True)
            frame, monitor = _screen_shot_mss(monitor_index)
            return _apply_target_window_crop(frame, monitor)
    if capture_method == CAPTURE_METHOD_MSS:
        frame, monitor = _screen_shot_mss(monitor_index)
        return _apply_target_window_crop(frame, monitor)
    raise ValueError(f"unknown capture method: {capture_method}")

class MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class InputUnion(ctypes.Union):
    _fields_ = (("mi", MouseInput),)


class Input(ctypes.Structure):
    _fields_ = (("type", ctypes.c_ulong), ("union", InputUnion))


class Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


def _send_mouse(flags: int, x: int | None = None, y: int | None = None) -> bool:
    mi = MouseInput()
    if x is not None and y is not None:
        vx = ctypes.windll.user32.GetSystemMetrics(76)
        vy = ctypes.windll.user32.GetSystemMetrics(77)
        vw = ctypes.windll.user32.GetSystemMetrics(78)
        vh = ctypes.windll.user32.GetSystemMetrics(79)
        mi.dx = int((x - vx) * 65535 / max(1, vw - 1))
        mi.dy = int((y - vy) * 65535 / max(1, vh - 1))
        mi.dwFlags = flags | 0x8000 | 0x4000
    else:
        mi.dwFlags = flags
    inp = Input()
    inp.type = 0
    inp.union.mi = mi
    return ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) == 1


def cursor_pos() -> tuple[int, int] | None:
    point = Point()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return (int(point.x), int(point.y))
    return None


def restore_cursor_pos(point: tuple[int, int] | None) -> None:
    if point is None:
        return
    ctypes.windll.user32.SetCursorPos(point[0], point[1])


def click_screen_xy_sendinput(x: int, y: int, duration: float = 0.08) -> None:
    saved_cursor = cursor_pos() if RESTORE_CURSOR_AFTER_CLICK else None
    hwnd = window_at(x, y)
    if hwnd:
        ensure_foreground_and_top(hwnd)
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(CLICK_MOVE_DELAY)
    _send_mouse(0x0001, x, y)
    time.sleep(CLICK_ABSOLUTE_MOVE_DELAY)
    _send_mouse(0x0002)
    time.sleep(duration)
    _send_mouse(0x0004)
    time.sleep(CLICK_AFTER_UP_DELAY)
    restore_cursor_pos(saved_cursor)


def _make_lparam(x: int, y: int) -> int:
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def _window_title(hwnd: int) -> str:
    title = ctypes.create_unicode_buffer(512)
    ctypes.windll.user32.GetWindowTextW(hwnd, title, len(title))
    return title.value


def _window_contains_point(hwnd: int, x: int, y: int) -> bool:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    return rect.left <= x < rect.right and rect.top <= y < rect.bottom


def _client_area_on_screen(hwnd: int) -> dict | None:
    user32 = ctypes.windll.user32
    if not hwnd or not user32.IsWindow(hwnd) or user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = Point(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        return None
    return {
        "left": int(origin.x),
        "top": int(origin.y),
        "width": width,
        "height": height,
        "source": "target_window_client",
        "hwnd": int(hwnd),
        "title": _window_title(hwnd),
    }


def _area_intersects_monitor(area: dict, monitor: dict) -> bool:
    left = int(area["left"])
    top = int(area["top"])
    right = left + int(area["width"])
    bottom = top + int(area["height"])
    mon_left = int(monitor["left"])
    mon_top = int(monitor["top"])
    mon_right = mon_left + int(monitor["width"])
    mon_bottom = mon_top + int(monitor["height"])
    return left < mon_right and right > mon_left and top < mon_bottom and bottom > mon_top


def _area_monitor_intersection_ratio(area: dict, monitor: dict) -> float:
    intersection = _window_area_intersection_score(area, monitor)
    area_size = float(max(1, int(area.get("width", 0)) * int(area.get("height", 0))))
    return intersection / area_size


def _area_looks_like_game_window(area: dict) -> bool:
    width = int(area.get("width", 0))
    height = int(area.get("height", 0))
    if width < 640 or height < 360:
        return False
    aspect = width / max(1, height)
    return 1.15 <= aspect <= 2.25


def _find_window_by_title_at_point(title_part: str, x: int, y: int) -> int:
    needle = title_part.strip().lower()
    if not needle:
        return 0

    user32 = ctypes.windll.user32
    found = ctypes.c_void_p(0)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd).lower()
        if needle in title and _window_contains_point(hwnd, x, y):
            found.value = int(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return int(found.value or 0)


def _find_window_by_title_on_monitor(title_part: str, monitor: dict) -> int:
    needle = title_part.strip().lower()
    if not needle:
        return 0

    user32 = ctypes.windll.user32
    candidates: list[tuple[float, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(hwnd).lower()
        area = _client_area_on_screen(hwnd)
        if (
            needle in title
            and area
            and _area_monitor_intersection_ratio(area, monitor) >= 0.50
            and _area_looks_like_game_window(area)
        ):
            aspect = int(area["width"]) / max(1, int(area["height"]))
            score = _window_area_intersection_score(area, monitor) - abs(aspect - BASE_ASPECT) * 100_000
            candidates.append((score, int(hwnd)))
        return True

    user32.EnumWindows(enum_proc, 0)
    if not candidates:
        return 0
    candidates.sort(reverse=True)
    return candidates[0][1]


def _cached_title_window(title_part: str, x: int, y: int) -> int:
    global _INPUT_TARGET_HWND_CACHE
    user32 = ctypes.windll.user32
    hwnd = _INPUT_TARGET_HWND_CACHE
    needle = title_part.strip().lower()
    if (
        hwnd
        and user32.IsWindow(hwnd)
        and user32.IsWindowVisible(hwnd)
        and needle in _window_title(hwnd).lower()
        and _window_contains_point(hwnd, x, y)
    ):
        return hwnd
    hwnd = _find_window_by_title_at_point(title_part, x, y)
    _INPUT_TARGET_HWND_CACHE = hwnd
    return hwnd


def _cached_title_window_on_monitor(title_part: str, monitor: dict) -> int:
    global _INPUT_TARGET_HWND_CACHE
    user32 = ctypes.windll.user32
    hwnd = _INPUT_TARGET_HWND_CACHE
    needle = title_part.strip().lower()
    area = _client_area_on_screen(hwnd) if hwnd else None
    if (
        hwnd
        and user32.IsWindow(hwnd)
        and user32.IsWindowVisible(hwnd)
        and needle in _window_title(hwnd).lower()
        and area
        and _area_monitor_intersection_ratio(area, monitor) >= 0.50
        and _area_looks_like_game_window(area)
    ):
        return hwnd
    hwnd = _find_window_by_title_on_monitor(title_part, monitor)
    _INPUT_TARGET_HWND_CACHE = hwnd
    return hwnd


def click_area_for(monitor: dict) -> dict:
    if INPUT_TARGET_WINDOW_TITLE:
        hwnd = _cached_title_window_on_monitor(INPUT_TARGET_WINDOW_TITLE, monitor)
        area = _client_area_on_screen(hwnd) if hwnd else None
        if area:
            return area
    return {
        "left": int(monitor["left"]),
        "top": int(monitor["top"]),
        "width": int(monitor["width"]),
        "height": int(monitor["height"]),
        "source": "monitor",
    }


@dataclasses.dataclass
class CaptureProbe:
    monitor_index: int
    area: dict
    frame: np.ndarray
    monitor: dict
    state: DetectionState
    score: float


def _window_area_intersection_score(area: dict, monitor: dict) -> float:
    left = max(int(area["left"]), int(monitor["left"]))
    top = max(int(area["top"]), int(monitor["top"]))
    right = min(int(area["left"]) + int(area["width"]), int(monitor["left"]) + int(monitor["width"]))
    bottom = min(int(area["top"]) + int(area["height"]), int(monitor["top"]) + int(monitor["height"]))
    if right <= left or bottom <= top:
        return 0.0
    return float((right - left) * (bottom - top))


def _window_title_matches_target(title: str) -> bool:
    needle = INPUT_TARGET_WINDOW_TITLE.strip().lower()
    return bool(needle and needle in title.lower())


def _visible_game_window_candidates(monitor: dict) -> list[tuple[int, dict]]:
    user32 = ctypes.windll.user32
    candidates: list[tuple[int, dict]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        area = _client_area_on_screen(hwnd)
        if not area or _area_monitor_intersection_ratio(area, monitor) < 0.50:
            return True
        if not _area_looks_like_game_window(area):
            return True
        area = dict(area)
        title = _window_title(hwnd)
        if INPUT_TARGET_WINDOW_TITLE.strip() and not _window_title_matches_target(title):
            return True
        area["hwnd"] = int(hwnd)
        area["title"] = title
        candidates.append((int(hwnd), area))
        return True

    user32.EnumWindows(enum_proc, 0)
    candidates.sort(
        key=lambda item: (
            _window_title_matches_target(item[1].get("title", "")),
            _window_area_intersection_score(item[1], monitor),
        ),
        reverse=True,
    )
    return candidates


def probe_game_window_capture(detector: CznDetector, capture_method: str) -> CaptureProbe | None:
    probes: list[CaptureProbe] = []
    for monitor_index, monitor in enumerate(_available_monitors()[1:], start=1):
        try:
            base_frame, base_monitor = _screen_shot_mss(monitor_index)
        except Exception as exc:
            print(f"window probe: failed to capture monitor {monitor_index}: {exc}", flush=True)
            continue
        for _hwnd, area in _visible_game_window_candidates(base_monitor):
            frame, cropped_monitor = _crop_frame_to_area(base_frame, base_monitor, area)
            if frame.shape[:2] == base_frame.shape[:2]:
                continue
            state = detector.detect(frame, warn_aspect=False)
            if state.label == "unknown":
                continue
            title_match = INPUT_TARGET_WINDOW_TITLE.strip().lower() in area.get("title", "").lower()
            aspect = int(area["width"]) / max(1, int(area["height"]))
            score = _window_area_intersection_score(area, base_monitor)
            if title_match:
                score += 10_000_000
            score -= abs(aspect - BASE_ASPECT) * 100_000
            probes.append(
                CaptureProbe(
                    monitor_index=monitor_index,
                    area=area,
                    frame=frame,
                    monitor=cropped_monitor,
                    state=state,
                    score=score,
                )
            )
    if not probes:
        return None
    probes.sort(key=lambda probe: probe.score, reverse=True)
    best = probes[0]
    print(
        "window probe: selected "
        f"monitor={best.monitor_index}, state={best.state.label}, "
        f"area={best.area}, frame_shape={best.frame.shape}",
        flush=True,
    )
    _FORCED_CAPTURE_AREAS[best.monitor_index] = best.area
    return best


def resolve_monitor_index(monitor_value: object) -> int:
    normalized = _coerce_config_value(monitor_value, "monitor", "runtime.monitor")
    monitors = _available_monitors()
    if normalized != "auto":
        index = int(normalized)
        if index >= len(monitors):
            raise ValueError(f"monitor index {index} is out of range; available: 0..{len(monitors) - 1}")
        CONFIG_MESSAGES.append(f"runtime monitor: using configured monitor {index}")
        return index

    if INPUT_TARGET_WINDOW_TITLE:
        for index, monitor in enumerate(monitors[1:], start=1):
            hwnd = _find_window_by_title_on_monitor(INPUT_TARGET_WINDOW_TITLE, monitor)
            area = _client_area_on_screen(hwnd) if hwnd else None
            if area:
                CONFIG_MESSAGES.append(
                    "runtime monitor: auto selected monitor "
                    f"{index} for target_window_title={INPUT_TARGET_WINDOW_TITLE!r}, "
                    f"hwnd={int(hwnd)}, area={area}"
                )
                return index
        CONFIG_MESSAGES.append(
            "runtime monitor: auto could not find target window "
            f"{INPUT_TARGET_WINDOW_TITLE!r}; falling back to primary monitor 1"
        )
    else:
        CONFIG_MESSAGES.append("runtime monitor: auto has no target_window_title; falling back to primary monitor 1")

    if len(monitors) > 1:
        return 1
    return 0


def message_target_at(x: int, y: int) -> int:
    if INPUT_TARGET_WINDOW_TITLE:
        hwnd = _cached_title_window(INPUT_TARGET_WINDOW_TITLE, x, y)
        if hwnd:
            return _message_target_for(hwnd)
        print(
            f"postmessage target title not found at ({x},{y}): {INPUT_TARGET_WINDOW_TITLE!r}; "
            "falling back to WindowFromPoint",
            flush=True,
        )
    return _message_target_for(window_at(x, y))


def _message_target_for(hwnd: int) -> int:
    if not hwnd:
        return 0
    user32 = ctypes.windll.user32
    root = int(user32.GetAncestor(hwnd, 3)) or hwnd
    popup = int(user32.GetLastActivePopup(root))
    if popup and popup != hwnd and user32.IsWindowVisible(popup):
        return popup
    return hwnd


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = Point(x, y)
    ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point))
    return (int(point.x), int(point.y))


def post_message_click_screen_xy(x: int, y: int, duration: float = 0.08, activate: bool = False) -> None:
    target = message_target_at(x, y)
    if not target:
        print(f"postmessage click skipped: no window at ({x},{y})", flush=True)
        return
    user32 = ctypes.windll.user32
    if activate:
        user32.PostMessageW(target, WM_ACTIVATE, WA_ACTIVE, 0)
        time.sleep(0.01)
    cx, cy = _screen_to_client(target, x, y)
    lparam = _make_lparam(cx, cy)
    ok_move = user32.PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
    ok_down = user32.PostMessageW(target, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(duration)
    ok_up = user32.PostMessageW(target, WM_LBUTTONUP, 0, lparam)
    time.sleep(CLICK_AFTER_UP_DELAY)
    if not (ok_move and ok_down and ok_up):
        print(
            f"postmessage click warning: target=0x{target:x} client=({cx},{cy}) "
            f"ok_move={ok_move} ok_down={ok_down} ok_up={ok_up}",
            flush=True,
        )


def click_screen_xy(x: int, y: int, duration: float = 0.08) -> None:
    if INPUT_BACKEND == INPUT_BACKEND_POSTMESSAGE:
        post_message_click_screen_xy(x, y, duration=duration, activate=False)
        return
    if INPUT_BACKEND == INPUT_BACKEND_POSTMESSAGE_ACTIVATE:
        post_message_click_screen_xy(x, y, duration=duration, activate=True)
        return
    click_screen_xy_sendinput(x, y, duration=duration)


def ensure_foreground_and_top(hwnd: int) -> bool:
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    foreground = user32.GetForegroundWindow()
    if hwnd == foreground:
        return True
    # Same basic strategy as MaaFramework's Win32 controller: bring the
    # target window to the top, then request foreground, then verify.
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
    time.sleep(FOCUS_TOP_DELAY)
    user32.SetForegroundWindow(hwnd)
    time.sleep(FOCUS_FOREGROUND_DELAY)
    ok = hwnd == user32.GetForegroundWindow()
    if not ok:
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002)
        time.sleep(FOCUS_RETRY_DELAY)
        ok = hwnd == user32.GetForegroundWindow()
    print(f"foreground {'ok' if ok else 'failed'} target=0x{hwnd:x} current=0x{user32.GetForegroundWindow():x}", flush=True)
    return ok


def describe_window_at(x: int, y: int) -> str:
    hwnd = window_at(x, y)
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, title, 256)
    return f"hwnd=0x{hwnd:x} pid={pid.value} title={title.value!r}"


def click_log_suffix(x: int, y: int) -> str:
    if not LOG_CLICK_WINDOW:
        return ""
    return f" {describe_window_at(x, y)}"


def window_at(x: int, y: int) -> int:
    return int(ctypes.windll.user32.WindowFromPoint(Point(x, y)))


def click_norm(point: tuple[float, float], monitor: dict, duration: float = 0.08) -> None:
    area = click_area_for(monitor)
    x = int(area["left"] + area["width"] * point[0])
    y = int(area["top"] + area["height"] * point[1])
    print(f"click screen=({x},{y}){click_log_suffix(x, y)}", flush=True)
    click_screen_xy(x, y, duration=duration)


def rapid_click_norm(
    point: tuple[float, float],
    monitor: dict,
    count: int,
    duration: float,
    interval: float,
    stop_keys: list[str],
    stop_file: Path | None,
) -> int:
    area = click_area_for(monitor)
    x = int(area["left"] + area["width"] * point[0])
    y = int(area["top"] + area["height"] * point[1])
    print(f"rapid click screen=({x},{y}) count={count}{click_log_suffix(x, y)}", flush=True)
    if INPUT_BACKEND in {INPUT_BACKEND_POSTMESSAGE, INPUT_BACKEND_POSTMESSAGE_ACTIVATE}:
        for sent in range(count):
            if stop_requested(stop_keys, stop_file):
                return sent
            post_message_click_screen_xy(
                x,
                y,
                duration=duration,
                activate=INPUT_BACKEND == INPUT_BACKEND_POSTMESSAGE_ACTIVATE,
            )
            if sleep_interruptible(interval, stop_keys, stop_file):
                return sent + 1
        return count
    saved_cursor = cursor_pos() if RESTORE_CURSOR_AFTER_CLICK else None
    hwnd = window_at(x, y)
    if hwnd:
        ensure_foreground_and_top(hwnd)
    ctypes.windll.user32.SetCursorPos(x, y)
    sent = 0
    for _ in range(count):
        if stop_requested(stop_keys, stop_file):
            restore_cursor_pos(saved_cursor)
            return sent
        _send_mouse(0x0002)
        time.sleep(duration)
        _send_mouse(0x0004)
        sent += 1
        if sleep_interruptible(interval, stop_keys, stop_file):
            restore_cursor_pos(saved_cursor)
            return sent
    restore_cursor_pos(saved_cursor)
    return sent


def click_frame_point(point: tuple[int, int], monitor: dict, duration: float = 0.08) -> None:
    x = int(monitor["left"] + point[0])
    y = int(monitor["top"] + point[1])
    print(f"click screen=({x},{y}){click_log_suffix(x, y)}", flush=True)
    click_screen_xy(x, y, duration=duration)
