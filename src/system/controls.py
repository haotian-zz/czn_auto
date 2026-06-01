from __future__ import annotations

from pathlib import Path

from core.settings import VK_CODES


def parse_stop_keys(stop_key: str) -> list[str]:
    keys = [key.strip().lower() for key in stop_key.split(",") if key.strip()]
    return [key for key in keys if key in VK_CODES]


def stop_requested(stop_keys: list[str], stop_file: Path | None) -> bool:
    if stop_file and stop_file.exists():
        print(f"stop file detected: {stop_file}")
        return True
    for key in stop_keys:
        if ctypes.windll.user32.GetAsyncKeyState(VK_CODES[key]) & 0x8000:
            print(f"{key.upper()} pressed; exiting immediately.")
            return True
    return False


def sleep_interruptible(seconds: float, stop_keys: list[str], stop_file: Path | None) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if stop_requested(stop_keys, stop_file):
            return True
        time.sleep(min(0.05, max(0.0, deadline - time.time())))
    return False

