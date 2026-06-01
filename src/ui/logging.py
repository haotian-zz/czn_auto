from __future__ import annotations


def print_action(label: str, point: tuple[float, float], act: bool) -> None:
    mode = "ACT" if act else "DRY"
    print(f"{mode}: {label} at normalized {point}", flush=True)
