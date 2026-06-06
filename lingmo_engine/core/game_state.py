"""游戏状态容器。

CharacterManager 是角色数据的唯一来源。_data 只存储与角色无关的场景状态。
_player / _inventory / _equipment 等顶层键已移除，运行时通过 CharacterManager 读写。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from lingmo_engine.core.save_version import CURRENT_SAVE_VERSION, run_migrations

if TYPE_CHECKING:
    from lingmo_engine.core.protocols.storage import StorageBackend

logger = logging.getLogger(__name__)


class GameState:
    """游戏状态容器。

    角色管理委托给 CharacterManager，本类只负责持久化、场景状态和会话管理。
    """

    def __init__(self, slot_dir: Path, storage: "StorageBackend | None" = None):
        self._slot_dir = slot_dir
        self._slot_dir.mkdir(parents=True, exist_ok=True)
        self._save_manager = None
        self._lock = threading.Lock()
        self._data: dict = self._default_state()
        self._character_manager = None
        self._custom_items: dict[str, dict] = {}
        self._custom_abilities: dict[str, dict] = {}
        self._amplify_fn = None  # 显示增幅回调，由世界特定代码注册
        self._corrupted = False  # 校验和失败时置 True
        self._save_lock = threading.RLock()  # 序列化 save() + save_plugins() 整体流程（可重入）
        # 存储后端（默认使用文件系统）
        if storage is not None:
            self._storage = storage
        else:
            from lingmo_engine.core.storage.filesystem import FileSystemBackend
            self._storage = FileSystemBackend()

    # ── 数据访问 ──────────────────────────────────

    @property
    def data(self) -> dict:
        """返回完整游戏状态快照（每次返回新 dict，修改不影响内部状态）。"""
        return self._build_full_snapshot()

    def is_corrupted(self) -> bool:
        """上次 load() 时校验和是否失败。"""
        return self._corrupted

    def snapshot(self) -> "StateSnapshot":
        """返回不可变状态快照（新代码推荐使用此方法替代 data 属性）。"""
        from lingmo_engine.core.state_snapshot import StateSnapshot

        full = self._build_full_snapshot()
        cm = self._character_manager
        location = cm.player.location if cm else ""
        return StateSnapshot(
            player_data=full.get("player", {}),
            scene_state={
                k: v
                for k, v in full.items()
                if k.startswith("__")
            },
            game_data=full,
            location_info=location,
        )

    def get_data_copy(self) -> dict:
        """返回完整游戏状态的浅拷贝（线程安全，含角色数据）。"""
        return self._build_full_snapshot()

    def _build_full_snapshot(self) -> dict:
        """基于 _data + CharacterManager + 注册表 构建完整快照。"""
        with self._lock:
            result = dict(self._data)
            # 直接读取，不调用带锁的公开方法（避免不可重入死锁）
            result["custom_abilities"] = dict(self._custom_abilities)
            result["custom_items"] = dict(self._custom_items)
            cm = self._character_manager
            if cm:
                player = cm.player
                pdata = player.to_dict()
                pdata.update(player.attrs)
                # 前端兼容：abilities 顶层别名
                pdata["abilities"] = pdata.get("abilities", [])
                # 应用显示增幅
                if self._amplify_fn:
                    pdata = self._amplify_fn(pdata)
                result["player"] = pdata
                result["inventory"] = list(player.inventory)
                result["equipment"] = dict(player.equipment)
            else:
                result["player"] = {}
                result["inventory"] = []
                result["equipment"] = {}
            return result

    # ── 槽位管理 ──────────────────────────────────

    @property
    def slot_dir(self) -> Path:
        return self._slot_dir

    def set_slot_dir(self, slot_dir: Path) -> None:
        old = self._slot_dir
        self._slot_dir = slot_dir
        self._slot_dir.mkdir(parents=True, exist_ok=True)
        logger.info("slot_dir 变更: %s → %s", old, self._slot_dir)

    def get_save_dir(self) -> Path:
        return self._slot_dir

    # ── SaveManager ───────────────────────────────

    @property
    def save_manager(self):
        return self._save_manager

    @save_manager.setter
    def save_manager(self, sm) -> None:
        self._save_manager = sm

    # ── CharacterManager ──────────────────────────

    @property
    def character_manager(self):
        return self._character_manager

    @character_manager.setter
    def character_manager(self, cm) -> None:
        self._character_manager = cm

    def set_amplify_fn(self, fn) -> None:
        """注册显示增幅函数 fn(pdata: dict) -> dict，由世界特定模块调用。"""
        self._amplify_fn = fn

    # ── 插件命名空间 ──────────────────────────────

    def get_plugin_data(self, plugin_name: str) -> dict:
        with self._lock:
            return dict(self._data.setdefault("plugins", {}).get(plugin_name, {}))

    def set_plugin_data(self, plugin_name: str, data: dict) -> None:
        with self._lock:
            plugins = self._data.setdefault("plugins", {})
            plugins[plugin_name] = dict(data)

    # ── Session ID ────────────────────────────────

    def get_session_id(self) -> str:
        with self._lock:
            return self._data.get("__session_id__", "")

    def set_session_id(self, session_id: str) -> None:
        with self._lock:
            self._data["__session_id__"] = session_id

    # ── 场景敌人 ──────────────────────────────────

    def get_scene_enemies(self) -> dict | None:
        with self._lock:
            return self._data.get("scene_enemies")

    def set_scene_enemies(self, data: dict | None) -> None:
        with self._lock:
            self._data["scene_enemies"] = data

    def clear_scene_enemies(self) -> None:
        with self._lock:
            self._data["scene_enemies"] = None

    # ── Registry: 物品注册表 ──────────────────────

    def add_registry_item(self, item_id: str, data: dict) -> None:
        with self._lock:
            self._custom_items[item_id] = data

    def get_registry_item(self, item_id: str) -> dict | None:
        with self._lock:
            return self._custom_items.get(item_id)

    def get_all_registry_items(self) -> dict:
        with self._lock:
            return dict(self._custom_items)

    # ── Registry: 技能注册表 ──────────────────────

    def add_registry_ability(self, ability_id: str, data: dict) -> None:
        with self._lock:
            self._custom_abilities[ability_id] = data

    def get_registry_ability(self, ability_id: str) -> dict | None:
        with self._lock:
            return self._custom_abilities.get(ability_id)

    def get_all_registry_abilities(self) -> dict:
        with self._lock:
            return dict(self._custom_abilities)

    # ── Registry: YAML 持久化 ─────────────────────

    def save_registries(self) -> None:
        """原子写入 items.yaml 和 abilities.yaml。"""
        with self._lock:
            snapshot_items = dict(self._custom_items)
            snapshot_abilities = dict(self._custom_abilities)
        for filename, data in [
            ("items.yaml", snapshot_items),
            ("abilities.yaml", snapshot_abilities),
        ]:
            target = str(self._slot_dir / filename)
            self._storage.atomic_write_yaml(target, data)
        logger.info("注册表已保存: items.yaml, abilities.yaml")

    def load_registries(self) -> None:
        """从 items.yaml 和 abilities.yaml 加载注册表。

        使用 dict() 拷贝 YAML 解析器返回的数据，避免共享原始对象引用
        导致 add_registry_item() 等方法的修改污染解析器缓存。
        """
        for filename, attr in [
            ("items.yaml", "_custom_items"),
            ("abilities.yaml", "_custom_abilities"),
        ]:
            path = str(self._slot_dir / filename)
            data = self._storage.read_yaml(path)
            if data is not None:
                with self._lock:
                    setattr(self, attr, dict(data))
                logger.info("加载注册表: %s (%d 条)", filename, len(data))

    # ── 默认状态 ──────────────────────────────────

    def _default_state(self) -> dict:
        """返回默认游戏状态（不含角色数据，角色数据由 CharacterManager 管理）。"""
        return {
            "flags": {},
            "scene_enemies": None,
            "game_time": {},
            "plugins": {},
            "player_id": 0,
        }

    # ── Flag ─────────────────────────────────────

    def set_flag(self, flag: str, value: bool = True) -> None:
        with self._lock:
            self._data["flags"][flag] = value

    def has_flag(self, flag: str) -> bool:
        with self._lock:
            return self._data["flags"].get(flag, False)

    # ── 持久化 ────────────────────────────────────

    def save(self) -> Path:
        """保存游戏状态到 state.json + npcs/*.yaml + 注册表 YAML。

        使用 _save_lock 序列化整个保存流程，防止 AutoSaveManager
        后台线程与主线程的并发 save() 交叉写入文件。
        """
        with self._save_lock:
            return self._save_impl()

    def _save_impl(self) -> Path:
        """保存的实际实现（调用方应已持有 _save_lock）。"""
        path = self._slot_dir / "state.json"
        cm = self._character_manager
        with self._lock:
            data_copy = dict(self._data)
        if cm:
            data_copy["player_id"] = cm.player.id
            # 清除旧格式残留
            data_copy.pop("characters", None)
            data_copy.pop("player", None)
            data_copy.pop("inventory", None)
            data_copy.pop("equipment", None)
            # custom_abilities 已迁移到 abilities.yaml，不再写入 state.json
            data_copy.pop("custom_abilities", None)
            # 位置字段已迁移到 Character，不在 state.json 中持久化
            data_copy.pop("location", None)
            data_copy.pop("current_node_id", None)
            # 角色数据持久化到 YAML
            npc_dir = self._slot_dir / "npcs"
            cm.save_all(npc_dir)
        # 写入版本号
        data_copy["save_version"] = CURRENT_SAVE_VERSION
        # 计算校验和（不包含 _checksum 字段本身）
        data_copy.pop("_checksum", None)
        checksum = self._compute_checksum(data_copy)
        data_copy["_checksum"] = checksum
        self._storage.atomic_write_json(str(path), data_copy)
        # 持久化注册表
        self.save_registries()
        if self._save_manager:
            slot_id = self._slot_dir.name
            player_name = cm.player.name if cm else ""
            player_level = cm.player.level if cm else 1
            self._save_manager.update_meta(
                slot_id,
                player_name=player_name,
                player_level=player_level,
                location=cm.player.location if cm else "",
                session_id=data_copy.get("__session_id__", ""),
            )
        logger.info("Game saved to %s", path)
        return path

    def save_plugins(self, plugin_registry) -> None:
        """调用所有 SelfPersistable 插件的自持久化钩子。

        使用 _save_lock 与 save() 序列化，确保 save()+save_plugins()
        作为一个原子单元执行，不被其他线程的 save() 穿插。
        """
        with self._save_lock:
            self._save_plugins_impl(plugin_registry)

    def save_all(self, plugin_registry) -> Path:
        """原子保存：state.json + 插件自持久化在同一个 _save_lock 内完成。

        替代分两次调用的 save() + save_plugins() 模式，
        消除两次锁获取之间的竞态窗口（AutoSaveManager 后台线程
        可能在两次调用之间穿插写入，导致 save_as() 混合快照）。
        """
        with self._save_lock:
            path = self._save_impl()
            self._save_plugins_impl(plugin_registry)
            return path

    def _save_plugins_impl(self, plugin_registry) -> None:
        """插件自持久化的实际实现（调用方应已持有 _save_lock）。"""
        if plugin_registry is None:
            return
        for plugin in plugin_registry.get_enabled_plugins():
            pdir = plugin.get_persistence_dir()
            if not pdir:
                continue
            dir_path = self._slot_dir / pdir
            dir_path.mkdir(parents=True, exist_ok=True)
            try:
                plugin.save_own_state(self._slot_dir)
            except Exception:
                logger.exception(
                    "插件 %s save_own_state 失败", getattr(plugin, "name", "?")
                )

    def load_plugins(self, plugin_registry) -> None:
        """调用所有 SelfPersistable 插件的自持久化恢复钩子。

        由加载流程在 load() 之后调用。plugin_registry 是 PluginRegistry 实例。
        """
        if plugin_registry is None:
            return
        for plugin in plugin_registry.get_enabled_plugins():
            pdir = plugin.get_persistence_dir()
            if not pdir:
                continue
            dir_path = self._slot_dir / pdir
            if not dir_path.exists():
                continue
            try:
                plugin.load_own_state(self._slot_dir)
            except Exception:
                logger.exception(
                    "插件 %s load_own_state 失败", getattr(plugin, "name", "?")
                )

    def save_as(self, new_slot_id: str, overwrite: bool = False) -> Path:
        """将当前状态另存为新槽位。先 save() 持久化内存状态，再复制到新目录。"""
        if self._save_manager is None:
            raise RuntimeError("SaveManager not set")
        # 先持久化当前内存状态到原槽位，确保另存的是最新数据
        self.save()
        new_dir = self._save_manager.resolve_slot_path(new_slot_id)
        if new_dir.exists():
            if overwrite:
                self._storage.remove_tree(str(new_dir))
            else:
                raise FileExistsError(f"槽位已存在: {new_slot_id}")
        self._storage.copy_tree(str(self._slot_dir), str(new_dir))
        current_meta = self._save_manager.read_meta(self._slot_dir.name)
        current_meta.update({"slot_id": new_slot_id})
        self._save_manager.write_meta(new_slot_id, current_meta)
        # 断言：save_as 不应改变活跃槽位
        assert self._slot_dir != new_dir, (
            f"save_as 意外切换了活跃槽位到 {new_dir}"
        )
        logger.info("Game saved as new slot: %s (active slot: %s)", new_slot_id, self._slot_dir.name)
        return new_dir

    def load(self) -> bool:
        """从 state.json + npcs/*.yaml 加载游戏状态。支持旧存档自动迁移。"""
        self._corrupted = False
        path = self._slot_dir / "state.json"
        if not path.exists():
            logger.info("No save file: %s", path)
            return False
        loaded_data = self._storage.read_json(str(path))
        if loaded_data is None:
            logger.info("Failed to read save file: %s", path)
            return False
        # 校验和验证
        saved_checksum = loaded_data.pop("_checksum", None)
        if saved_checksum is not None:
            actual = self._compute_checksum(loaded_data)
            if actual != saved_checksum:
                logger.warning(
                    "存档校验和不匹配: 期望 %s, 实际 %s",
                    saved_checksum[:8], actual[:8],
                )
                self._corrupted = True
        elif loaded_data.get("save_version") is not None:
            # 有版本号但无校验和 — 可能被篡改（旧存档无版本号和校验和，不标记）
            logger.warning("存档缺少校验和（save_version=%s），可能被篡改",
                           loaded_data.get("save_version"))
            self._corrupted = True
        # 运行版本迁移链
        loaded_data = run_migrations(loaded_data)
        # 迁移：旧存档可能包含 location，主动清除（位置由 Character 管理）
        loaded_data.pop("location", None)
        # 注意：不在此处清除 current_node_id，MapPlugin.load_state() 需要读取旧值作为兼容回退
        default = self._default_state()
        for top_key in default:
            if top_key not in loaded_data:
                loaded_data[top_key] = default[top_key]
        with self._lock:
            self._data = loaded_data

        # 加载 YAML 注册表
        self.load_registries()

        # 迁移：旧存档中 custom_abilities 在 state.json → 迁移到 abilities.yaml
        abilities_yaml = self._slot_dir / "abilities.yaml"
        old_abilities = self._data.get("custom_abilities", {})
        if not self._storage.file_exists(str(abilities_yaml)) and old_abilities:
            with self._lock:
                self._custom_abilities = dict(old_abilities)
            self.save_registries()
            logger.info("迁移 custom_abilities → abilities.yaml (%d 条)", len(old_abilities))
        with self._lock:
            self._data.pop("custom_abilities", None)

        cm = self._character_manager
        if cm is None:
            logger.warning("load(): CharacterManager 未初始化，跳过角色加载。"
                           "请确保调用方在 load() 前设置 character_manager。")
        if cm:
            npc_dir = self._slot_dir / "npcs"
            # 旧存档迁移：从 state.json 的 characters 数组或 player 对象生成 YAML 文件
            saved_chars = self._data.get("characters")
            saved_player = self._data.get("player")
            if not (npc_dir / "npc_0.yaml").exists():
                npc_dir.mkdir(parents=True, exist_ok=True)
                from lingmo_engine.core.character import Character
                if saved_chars:
                    for char_data in saved_chars:
                        char = Character.from_dict(char_data)
                        cm.save_npc_file(char, npc_dir)
                    logger.info("旧存档迁移完成: %d 个角色已写入 YAML", len(saved_chars))
                elif saved_player and isinstance(saved_player, dict):
                    char = Character.from_dict(saved_player)
                    cm.save_npc_file(char, npc_dir)
                    logger.info("旧存档迁移完成: player 对象已写入 YAML")
            # 清除 _data 中的旧格式数据，防止干扰
            self._data.pop("characters", None)
            self._data.pop("player", None)
            self._data.pop("inventory", None)
            self._data.pop("equipment", None)

            # 从 YAML 文件加载所有角色
            # 批量文件是全量快照，加载前清空模板角色确保存档为唯一来源；
            # 逐文件模式只保存脏角色，不清空以保留未脏的模板角色
            if npc_dir.exists():
                batch_file = npc_dir / "npcs_batch.yaml"
                if batch_file.exists():
                    cm.clear_all()
                cm.load_npc_dir(npc_dir)
                # 校验并移除幽灵/重复角色
                removed = cm.validate_after_load()
                if removed:
                    logger.warning("存档加载后清理重复角色: %s", removed)
            # 恢复角色运行时状态
            self._restore_characters_from_save()

            # 迁移：旧装备槽位 → 叙事模式新槽位
            self._migrate_equipment_slots()

        logger.info("Game loaded from %s", path)
        return True

    def load_from_slot(self, slot_id: str) -> bool:
        """从指定槽位加载游戏状态。"""
        if self._save_manager is None:
            logger.warning("load_from_slot: SaveManager 未设置，无法切换槽位")
            return False
        new_dir = self._save_manager.resolve_slot_path(slot_id)
        if not self._storage.dir_exists(str(new_dir)):
            return False
        logger.info("load_from_slot: %s → %s", self._slot_dir, new_dir)
        self._slot_dir = new_dir
        return self.load()

    def _restore_characters_from_save(self) -> None:
        """角色数据已由 load_npc_dir 从 YAML 加载，此方法保留为空操作。"""

    def _migrate_equipment_slots(self) -> None:
        """旧装备槽位迁移到叙事模式新槽位。

        对 player 和所有 NPC 执行相同的迁移逻辑：
        - body/headpiece/mask/shoes/legs/socks → clothing（取第一个非空）
        - ring_1/ring_2/necklace → accessory（取第一个非空）
        - life_treasure → 不变
        - mount → 新增为空
        """
        cm = self._character_manager
        if not cm:
            return

        migrated = 0
        for char in cm.all():
            if self._migrate_char_equipment(char):
                migrated += 1

        if migrated:
            logger.info("装备槽位迁移完成: %d 个角色", migrated)

    @staticmethod
    def _migrate_char_equipment(char) -> bool:
        """迁移单个角色的装备槽位。返回 True 表示发生了迁移。"""
        old_equipment = dict(char.equipment) if char.equipment else {}
        if not old_equipment:
            return False

        old_slot_keys = {"body", "headpiece", "mask", "shoes", "legs", "socks",
                         "ring_1", "ring_2", "necklace"}
        if not any(k in old_equipment for k in old_slot_keys):
            return False

        new_equipment = {}

        if "life_treasure" in old_equipment:
            new_equipment["life_treasure"] = old_equipment["life_treasure"]

        for slot in ["body", "headpiece", "mask", "shoes", "legs", "socks"]:
            if old_equipment.get(slot):
                new_equipment["clothing"] = old_equipment[slot]
                break

        for slot in ["ring_1", "ring_2", "necklace"]:
            if old_equipment.get(slot):
                new_equipment["accessory"] = old_equipment[slot]
                break

        new_equipment["mount"] = None

        char.equipment = new_equipment
        return True

    @staticmethod
    def _compute_checksum(data: dict) -> str:
        """计算 dict 数据的 SHA-256 校验和。

        调用方应已 pop _checksum，save_version 包含在校验中以检测版本篡改。
        使用 separators=(',', ':') 避免 JSON 中冒号后的空格在不同 Python
        版本间产生差异（如 float 序列化格式变化）。sort_keys=True 确保 dict
        key 顺序一致。
        """
        raw = json.dumps(data, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def list_saves(self) -> list[dict]:
        """列出所有存档槽位摘要。"""
        if self._save_manager:
            return self._save_manager.list_saves()
        parent = self._slot_dir.parent
        if not parent.exists():
            return []
        return [{"slot_id": p.name, "is_autosave": p.name.startswith("autosave")}
                for p in sorted(parent.iterdir()) if p.is_dir()]

    def reset_scene_state(self) -> None:
        """重置场景状态（location/flags/scene_enemies 等），不影响角色数据。"""
        with self._lock:
            self._data = self._default_state()
            self._custom_items = {}
            self._custom_abilities = {}
            self._amplify_fn = None

    # ── 顶层键写入 ────────────────────────────────

    def set_game_time(self, time_data: dict) -> None:
        with self._lock:
            self._data["game_time"] = time_data

    def set_top_level(self, key: str, value: object) -> None:
        with self._lock:
            if key not in self._data:
                raise KeyError(f"不允许创建新的顶层键: {key}")
            self._data[key] = value

    # ── Player 操作（代理到 CharacterManager） ────

    def get_player(self):
        """获取主角 Character 对象。CharacterManager 未初始化时抛出 RuntimeError。"""
        cm = self._character_manager
        if cm is None:
            raise RuntimeError("CharacterManager 未初始化，无法访问玩家数据")
        return cm.player

    def update_player(self, **kwargs) -> None:
        """批量更新玩家属性。

        已知字段（name/level/exp/abilities）走类型校验；
        数值字段写入 attrs（支持运行时动态扩展属性，如 gold）；
        非数值字符串写入 Character 对应字段（location/faction 等）；
        其余类型静默忽略。
        """
        player = self.get_player()
        # Character dataclass 中可直接 setattr 的字符串字段
        _string_fields = {"location", "faction", "personality", "background", "avatar"}
        for key, value in kwargs.items():
            if key == "name":
                if not isinstance(value, str):
                    raise TypeError(f"name 必须为字符串，收到 {type(value).__name__}")
                player.name = value
            elif key == "level":
                if not isinstance(value, int) or value <= 0:
                    raise ValueError(f"level 必须为正整数")
                player.level = value
            elif key == "exp":
                if not isinstance(value, int):
                    raise TypeError(f"exp 必须为整数")
                player.exp = value
            elif key == "abilities":
                if not isinstance(value, list):
                    raise TypeError(f"abilities 必须为列表")
                player.abilities = list(value)
            elif isinstance(value, (int, float)):
                # 数值属性：直接写入 attrs（支持 LLM 动态创建新属性）
                player.attrs[key] = int(value)
            elif key in player.attrs:
                # 已有 attrs 键但收到非数值 → 类型错误
                raise TypeError(f"{key} 必须为数字，收到 {type(value).__name__}")
            elif isinstance(value, str) and key in _string_fields:
                setattr(player, key, value)
            # 其余未知键静默忽略

    def add_player_exp(self, amount: int) -> None:
        """增加玩家经验值。"""
        player = self.get_player()
        player.exp += amount

    def get_player_snapshot(self) -> dict:
        """返回玩家数据的快照（含展开的属性 + 显示增幅）。"""
        player = self.get_player()
        result = player.to_dict()
        result.update(player.attrs)
        if self._amplify_fn:
            result = self._amplify_fn(result)
        return result

    # ── Inventory 操作 ────────────────────────────

    def add_player_item(self, item_id: str, quantity: int = 1) -> None:
        """向物品栏添加物品（堆叠到已有条目）。"""
        player = self.get_player()
        for entry in player.inventory:
            if entry["item_id"] == item_id:
                entry["quantity"] += quantity
                return
        player.inventory.append({"item_id": item_id, "quantity": quantity})

    def remove_player_item(self, item_id: str, quantity: int = 1) -> bool:
        """从物品栏移除指定数量的物品。成功返回 True，不足则返回 False。"""
        player = self.get_player()
        for entry in player.inventory:
            if entry["item_id"] == item_id:
                if entry["quantity"] < quantity:
                    return False
                entry["quantity"] -= quantity
                if entry["quantity"] <= 0:
                    player.inventory.remove(entry)
                return True
        return False

    def get_inventory_snapshot(self) -> list:
        """返回物品栏的浅拷贝。"""
        return list(self.get_player().inventory)

    # ── Equipment 操作 ────────────────────────────

    def equip_item(self, slot: str, item_id: str) -> None:
        """装备物品到指定槽位。"""
        self.get_player().equipment[slot] = item_id

    def unequip_item(self, slot: str) -> str | None:
        """卸下指定槽位的装备，返回被卸下的物品 ID，若为空则返回 None。"""
        return self.get_player().equipment.pop(slot, None)

    def get_equipment(self) -> dict:
        """返回装备字典的拷贝。"""
        return dict(self.get_player().equipment)

    def set_equipment(self, eq: dict) -> None:
        """整体设置装备字典。"""
        self.get_player().equipment = dict(eq)

    # ── Abilities 操作 ────────────────────────────

    def add_player_ability(self, ability_id: str) -> None:
        """添加玩家技能（去重）。"""
        player = self.get_player()
        if ability_id not in player.abilities:
            player.abilities.append(ability_id)

    def has_player_ability(self, ability_id: str) -> bool:
        """检查玩家是否拥有指定技能。"""
        return ability_id in self.get_player().abilities

    def get_player_abilities(self) -> list:
        """返回玩家技能列表的拷贝。"""
        return list(self.get_player().abilities)

    # ── Custom Abilities 操作（代理到注册表）──────

    def add_custom_ability(self, ability_id: str, data: dict) -> None:
        self.add_registry_ability(ability_id, data)

    def get_custom_ability(self, ability_id: str) -> dict | None:
        return self.get_registry_ability(ability_id)

    def get_all_custom_abilities(self) -> dict:
        return self.get_all_registry_abilities()
