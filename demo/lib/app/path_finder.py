import os
import json
from collections import deque

# 在文件开头或全局位置定义翻译字典
ACTION_MAP = {
    "Left button": "左键",
    "Right button": "右键",
    "Up button": "上键",
    "Down button": "下键",
    "Center button": "中键",
    "Press center button (Hold 2s)": "长按中键"
}

# ==========================================
# 寻路核心逻辑
# ==========================================
class OSDMenuPathfinder:
    def __init__(self, json_path=None, picture_mode_defaults=None, signal_mode="SDR mode", picture_mode="ECO"):
        self.tree_data = self.load_json(json_path) if json_path else []
        # Picture Mode 默认值表
        self.picture_mode_defaults = picture_mode_defaults or {}
        # 当前信号模式，先默认 SDR
        self.signal_mode = signal_mode
        # 当前 Picture Mode，Reset 后默认 ECO
        self.picture_mode = picture_mode

    REF_PICTURE_MODE_TEXT = "預設值請參考Picture mode頁次"

    PICTURE_MODE_KEY_ALIAS = {
        "Preset Mode": "__picture_mode__",

        "Brightness": "Brightness",
        "Contrast": "Contrast",
        "Sharpness": "Sharpness",

        # 菜单 JSON 叫 Color Vibrance，模式表里叫 Color Vibrance (HUE)
        "Color Vibrance": "Color Vibrance (HUE)",

        "Gamma": "Gamma",
        "Color Temperature": "Color Temperature",

        "APL Stabilize": "APL Stabilize",
        "APL Stabilize ": "APL Stabilize",

        "Super Resolution": "Super Resolution",
        "AI Black Equalizer": "Black Equalizer 2.0",
        "Black Equalizer 2.0": "Black Equalizer 2.0",

        "Dark Enhance": "Dark Enhance",
        "Color Enhance": "Color Enhance",
        "Light Enhance": "Light Enhance",
        "Hyper Nits": "Hyper Nits",
    }

    def set_picture_mode_context(self, signal_mode=None, picture_mode=None):
        """
        由主程序同步当前显示器状态。
        """
        if signal_mode is not None:
            self.signal_mode = signal_mode
        if picture_mode is not None:
            self.picture_mode = picture_mode

    def _normalize_value(self, value):
        """
        把模式表里的值转成可以和 OSD children name 匹配的字符串。
        """
        if value is None:
            return None

        s = str(value).strip()

        # Disable(100) -> 100
        # Disable(OFF) -> OFF
        if s.startswith("Disable(") and s.endswith(")"):
            s = s[len("Disable("):-1].strip()

        if s.upper() == "OFF":
            return "OFF"

        return s

    def _match_child_name(self, value, valid_names):
        """
        把模式表里的默认值匹配到实际 children name。
        例如 2.2 -> "2.2"，2 -> "2.0"。
        """
        if value is None:
            return None

        raw = self._normalize_value(value)
        if raw is None:
            return None

        raw_str = str(raw).strip()

        # 1. 直接匹配
        if raw_str in valid_names:
            return raw_str

        # 2. 数值兼容：2 和 2.0 视为相同
        try:
            raw_float = float(raw_str)
            for name in valid_names:
                try:
                    if float(str(name).strip()) == raw_float:
                        return name
                except ValueError:
                    pass
        except ValueError:
            pass

        # 3. 大小写兼容
        for name in valid_names:
            if str(name).strip().lower() == raw_str.lower():
                return name

        return None

    def _resolve_picture_mode_default(self, node, valid_names=None):
        """
        解析 '預設值請參考Picture mode頁次' 对应的真实默认值。
        """
        if not isinstance(node, dict):
            return None

        menu_name = node.get("name")
        if not menu_name:
            return None

        mapped_key = self.PICTURE_MODE_KEY_ALIAS.get(menu_name, menu_name)

        # Preset Mode 自己的默认焦点就是当前 picture_mode
        if mapped_key == "__picture_mode__":
            if valid_names:
                return self._match_child_name(self.picture_mode, valid_names)
            return self.picture_mode

        mode_table = self.picture_mode_defaults.get(self.signal_mode, {})
        profile = mode_table.get(self.picture_mode, {})

        if not isinstance(profile, dict):
            return None

        value = profile.get(mapped_key)

        if valid_names:
            return self._match_child_name(value, valid_names)

        return self._normalize_value(value)

    def update_data(self, json_path):
        """支持程序运行时动态切换 JSON"""
        self.tree_data = self.load_json(json_path)

    def load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def get_valid_children(self, node):
        """兼容新 JSON 的提取子节点名逻辑"""
        if isinstance(node, list):
            # 如果是根列表，返回所有含有 name 的顶层节点
            return [item["name"] for item in node if "name" in item]
        elif isinstance(node, dict):
            # 如果是字典节点，则去它的 children 数组里找
            children_list = node.get("children", [])
            return [child["name"] for child in children_list if "name" in child]
        return []

    def get_default_item(self, node):
        """
        兼容新 JSON 的 Default 读取逻辑。
        支持：
        1. 普通 Default
        2. 子节点 Default
        3. '預設值請參考Picture mode頁次' 动态解析
        """
        if not isinstance(node, dict):
            return None

        children = node.get("children", [])
        valid_names = self.get_valid_children(node)

        # 情况1：父节点自身显式定义了 Default
        if "Default" in node:
            def_val = node["Default"]

            # 核心：遇到“参考 Picture Mode 页次”，不要直接返回说明文字
            if def_val == self.REF_PICTURE_MODE_TEXT:
                resolved = self._resolve_picture_mode_default(node, valid_names)
                if resolved is not None:
                    return resolved
                return valid_names[0] if valid_names else None

            # 普通 Default：如果当前是选项列表，尽量匹配到真实 child name
            if valid_names:
                matched = self._match_child_name(def_val, valid_names)
                if matched is not None:
                    return matched
                return valid_names[0] if valid_names else None

            return def_val

        # 情况2：父节点没有 Default，但子节点带 Default
        if children:
            for child in children:
                if "Default" not in child:
                    continue

                def_val = child["Default"]

                if def_val == self.REF_PICTURE_MODE_TEXT:
                    resolved = self._resolve_picture_mode_default(node, valid_names)
                    if resolved is not None:
                        return resolved
                    continue

                matched = self._match_child_name(def_val, valid_names)
                if matched is not None:
                    return matched

            return valid_names[0] if valid_names else None

        return None

    def get_node_at_path(self, path_tuple):
        """兼容新 JSON 的按名寻址逻辑"""
        if not path_tuple:
            return self.tree_data  # 根节点是一个 List

        curr = self.tree_data
        for p in path_tuple:
            found = False
            # 兼容当前层级是根 List 还是子节点的 children List
            children_list = curr if isinstance(curr, list) else curr.get("children", [])
            for child in children_list:
                if child.get("name") == p:
                    curr = child
                    found = True
                    break
            if not found:
                return {}  # 路径无效返回空
        return curr

    def path_to_state(self, path_tuple):
        """将 JSON 绝对路径元组转换为内部 FSM 状态"""
        if not path_tuple: return ("IDLE",)

        parent_path = path_tuple[:-1]
        focused_item = path_tuple[-1]

        # 如果 parent_path 为空，说明目标是顶层大类别(如 "Main Menu(Setting)")
        # 按照物理逻辑，此时状态应该处于该类别的 LIST 中，焦点落在它的默认子项上
        if not parent_path:
            node = self.get_node_at_path(path_tuple)
            return ("LIST", path_tuple, self.get_default_item(node))

        return ("LIST", parent_path, focused_item)

    def is_target(self, state, target_path):
        """判断当前状态是否已经抵达寻路目标"""
        if not target_path: return state == ("IDLE",)

        if state[0] == "LIST":
            # 精确匹配：在正确的父菜单中，且焦点精准落在了目标项上
            if state[1] == target_path[:-1] and state[2] == target_path[-1]:
                return True
            # 模糊/层级匹配：目标如果是大类别，只要状态进入了该列表即视为到达
            if state[1] == target_path:
                return True
        return False

    def get_neighbors(self, state):
        neighbors = []
        if state == ("IDLE",):
            for item in self.tree_data:
                ops = item.get("operation", [])
                if not ops: continue
                target_name = item.get("name")

                actions = []
                for op_str in ops:
                    for part in op_str.split('\n'):
                        mapped_act = ACTION_MAP.get(part.strip())
                        if mapped_act: actions.append(mapped_act)

                # --- 核心修正：区分“直接进入”与“仅聚焦” ---
                children_names = self.get_valid_children(item)
                if children_names:
                    # 如果该入口包含子菜单（如 Main Menu），按键后直接穿透，焦点落在内部子项上
                    default_item = self.get_default_item(item)
                    if default_item not in children_names:
                        default_item = children_names[0]
                    target_state = ("LIST", (target_name,), default_item)
                else:
                    # 如果没有子菜单（如 Brightness），按键后焦点就是自身
                    target_state = ("LIST", (), target_name)

                for act in actions:
                    neighbors.append((act, target_state))

        # --- 以下为第二阶段全新的 LIST 游走逻辑 ---
        elif state[0] == "LIST":
            menu_path = state[1]
            focused_item = state[2]

            node = self.get_node_at_path(menu_path)
            children_names = self.get_valid_children(node)

            # 1. 列表内的上下游走
            if focused_item in children_names:
                idx = children_names.index(focused_item)
                length = len(children_names)

                # 只有当列表项目大于1个时，才需要上下游走
                if length > 1:
                    # 上键：通过取模运算 (idx - 1) % length，如果是第0个，会自动变成倒数第1个
                    up_idx = (idx - 1) % length
                    neighbors.append(("上键", ("LIST", menu_path, children_names[up_idx])))

                    # 下键：通过取模运算 (idx + 1) % length，如果是最后一个，会自动变成第0个
                    down_idx = (idx + 1) % length
                    neighbors.append(("下键", ("LIST", menu_path, children_names[down_idx])))

            # 2. 右键：向内部子菜单穿透
            if focused_item is not None:
                child_path = menu_path + (focused_item,)
                child_node = self.get_node_at_path(child_path)
                child_children_names = self.get_valid_children(child_node)

                if child_children_names:
                    # 如果该焦点存在有效的子菜单，右键即可进入，并聚焦默认项
                    default_item = self.get_default_item(child_node)
                    if default_item not in child_children_names:  # 安全校验
                        default_item = child_children_names[0]
                    neighbors.append(("右键", ("LIST", child_path, default_item)))

            # 3. 左键：返回上一层级
            if len(menu_path) == 1:
                # 如果处在第一级菜单(如 Main Menu(Setting))，左键直接退回待机
                neighbors.append(("左键", ("IDLE",)))
            elif len(menu_path) > 1:
                # 如果在深层菜单，左键退回父级列表，并且焦点必须停留在刚才的进入点上
                parent_path = menu_path[:-1]
                parent_focus = menu_path[-1]
                neighbors.append(("左键", ("LIST", parent_path, parent_focus)))

        return neighbors

    def find_shortest_path(self, start_path, end_path):
        """广度优先 (BFS) 寻路算法引擎"""
        start_state = self.path_to_state(start_path)
        if self.is_target(start_state, end_path):
            return "SAME", []

        queue = deque([(start_state, [])])
        visited = set([start_state])

        while queue:
            current_state, path_data = queue.popleft()
            for action, next_state in self.get_neighbors(current_state):
                if next_state not in visited:
                    new_path = path_data + [(action, next_state)]

                    if self.is_target(next_state, end_path):
                        # --- 闭环确认逻辑 ---
                        # 判断寻路的终点是否为一个最末端的叶子选项(例如 ON, OFF)
                        end_node = self.get_node_at_path(end_path)
                        if not self.get_valid_children(end_node):
                            # 追加右键作为参数设定确认动作，映射为 MANUAL 状态以便 UI 显示
                            final_confirm_state = ("MANUAL", f"确认设置\n[{end_path[-1]}]")
                            new_path.append(("右键", final_confirm_state))
                        return "OK", new_path

                    visited.add(next_state)
                    queue.append((next_state, new_path))

        return "ERROR", []