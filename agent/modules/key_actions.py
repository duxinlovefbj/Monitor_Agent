from demo.lib.control.key_control import MonitorController


def press_osd_key(action_name: str, manufacturer: str = "KTC", async_mode: bool = False) -> dict:
    """Dispatch monitor physical key action via legacy USB controller."""
    MonitorController.press(action_name, manufacturer=manufacturer, async_mode=async_mode)
    return {
        "action": action_name,
        "manufacturer": manufacturer,
        "async_mode": async_mode,
    }
