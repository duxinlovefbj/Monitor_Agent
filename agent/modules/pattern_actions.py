from demo.lib.actions.displayhdr import DisplayHDRController
from demo.lib.actions.pattern import ScreenPatternTester


def show_pattern(pattern: str, parent=None) -> dict:
    color_map = {
        "red": "#FF0000",
        "green": "#00FF00",
        "blue": "#0000FF",
        "white": "#FFFFFF",
        "black": "#000000",
    }
    normalized = pattern.strip().lower()

    if normalized == "displayhdr":
        ok = DisplayHDRController.launch()
        return {"pattern": pattern, "launched": ok}

    if normalized.startswith("gray:"):
        level = int(normalized.split(":", 1)[1])
        color = ScreenPatternTester.rgb_to_hex(level, level, level)
    else:
        color = color_map.get(normalized)

    if not color:
        raise ValueError(f"不支持的 pattern: {pattern}")

    ScreenPatternTester.show(color, parent=parent)
    return {"pattern": pattern, "color": color}


def close_pattern() -> None:
    ScreenPatternTester.close()
