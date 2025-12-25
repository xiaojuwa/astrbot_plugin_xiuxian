# config_manager.py

import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

from astrbot.api import logger
from .models import Item

class ConfigManager:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self.config_dir = base_dir / "config"
        self._paths = {
            "level": self.config_dir / "level_config.json",
            "item": self.config_dir / "items.json",
            "boss": self.config_dir / "bosses.json",
            "monster": self.config_dir / "monsters.json",
            "realm": self.config_dir / "realms.json",
            "tag": self.config_dir / "tags.json",
            "recipe": self.config_dir / "recipes.json",
            "sect_shop": self.config_dir / "sect_shop.json",
            "sect_buildings": self.config_dir / "sect_buildings.json"
        }

        self.level_data: List[dict] = []
        self.item_data: Dict[str, Item] = {}
        self.boss_data: Dict[str, dict] = {}
        self.monster_data: Dict[str, dict] = {}
        self.realm_data: Dict[str, dict] = {}
        self.tag_data: Dict[str, dict] = {}
        self.recipe_data: Dict[str, dict] = {}
        self.sect_shop_data: Dict[str, dict] = {}
        self.sect_buildings_data: Dict[str, dict] = {}

        self.level_map: Dict[str, dict] = {}
        self.item_name_to_id: Dict[str, str] = {}
        self.realm_name_to_id: Dict[str, str] = {}
        self.boss_name_to_id: Dict[str, str] = {}
        self.recipe_name_to_id: Dict[str, str] = {}

        self._load_all()

    def _load_json_data(self, file_path: Path) -> Any:
        if not file_path.exists():
            logger.warning(f"数据文件 {file_path} 不存在，将使用空数据。")
            return {} if file_path.suffix == '.json' else []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"成功加载 {file_path.name} (共 {len(data)} 条数据)。")
                return data
        except Exception as e:
            logger.error(f"加载数据文件 {file_path} 失败: {e}")
            return {} if file_path.suffix == '.json' else []

    def _load_all(self):
        """加载所有数据文件并进行后处理"""
        self.level_data = self._load_json_data(self._paths["level"])
        raw_item_data = self._load_json_data(self._paths["item"])
        self.boss_data = self._load_json_data(self._paths["boss"])
        self.monster_data = self._load_json_data(self._paths["monster"])
        self.realm_data = self._load_json_data(self._paths["realm"])
        self.tag_data = self._load_json_data(self._paths["tag"])
        self.recipe_data = self._load_json_data(self._paths["recipe"])
        self.sect_shop_data = self._load_json_data(self._paths["sect_shop"])
        self.sect_buildings_data = self._load_json_data(self._paths["sect_buildings"])

        self.level_map = {info["level_name"]: {"index": i, **info}
                          for i, info in enumerate(self.level_data) if "level_name" in info}

        self.item_data = {}
        self.item_name_to_id = {}
        for item_id, info in raw_item_data.items():
            try:
                self.item_data[item_id] = Item(id=item_id, **info)
                if "name" in info:
                    self.item_name_to_id[info["name"]] = item_id
            except TypeError as e:
                logger.error(f"加载物品 {item_id} 失败，配置项不匹配: {e}")

        self.realm_name_to_id = {info["name"]: realm_id
                                 for realm_id, info in self.realm_data.items() if "name" in info}
        self.boss_name_to_id = {info["name"]: boss_id
                                for boss_id, info in self.boss_data.items() if "name" in info}
        
        # 加载配方名称映射
        self.recipe_name_to_id = {}
        for craft_type in ["alchemy", "smithing"]:
            if craft_type in self.recipe_data:
                for recipe_id, recipe_info in self.recipe_data[craft_type].items():
                    if "name" in recipe_info:
                        self.recipe_name_to_id[recipe_info["name"]] = recipe_id

    def get_item_by_name(self, name: str) -> Optional[Tuple[str, Item]]:
        item_id = self.item_name_to_id.get(name)
        return (item_id, self.item_data[item_id]) if item_id and item_id in self.item_data else None

    def get_realm_by_name(self, name: str) -> Optional[Tuple[str, dict]]:
        realm_id = self.realm_name_to_id.get(name)
        return (realm_id, self.realm_data[realm_id]) if realm_id else None

    def get_boss_by_name(self, name: str) -> Optional[Tuple[str, dict]]:
        boss_id = self.boss_name_to_id.get(name)
        return (boss_id, self.boss_data[boss_id]) if boss_id else None

    def get_recipe_by_name(self, name: str) -> Optional[Tuple[str, dict, str]]:
        """根据配方名获取配方信息，返回 (recipe_id, recipe_info, craft_type)"""
        recipe_id = self.recipe_name_to_id.get(name)
        if not recipe_id:
            return None
        for craft_type in ["alchemy", "smithing"]:
            if craft_type in self.recipe_data and recipe_id in self.recipe_data[craft_type]:
                return (recipe_id, self.recipe_data[craft_type][recipe_id], craft_type)
        return None

    def get_recipe_by_id(self, recipe_id: str) -> Optional[Tuple[dict, str]]:
        """根据配方ID获取配方信息，返回 (recipe_info, craft_type)"""
        for craft_type in ["alchemy", "smithing"]:
            if craft_type in self.recipe_data and recipe_id in self.recipe_data[craft_type]:
                return (self.recipe_data[craft_type][recipe_id], craft_type)
        return None

    def get_all_recipes(self, craft_type: str) -> Dict[str, dict]:
        """获取指定类型的所有配方"""
        return self.recipe_data.get(craft_type, {})

    def get_furnace_info(self, level: int) -> Optional[dict]:
        """获取丹炉信息"""
        return self.recipe_data.get("furnace_levels", {}).get(str(level))

    def get_forge_info(self, level: int) -> Optional[dict]:
        """获取炼器台信息"""
        return self.recipe_data.get("forge_levels", {}).get(str(level))

    def get_crafter_level_info(self, level: int) -> Optional[dict]:
        """获取炼丹师/炼器师等级信息"""
        return self.recipe_data.get("crafter_levels", {}).get(str(level))

    def get_quality_rates(self) -> Dict[str, dict]:
        """获取品质概率配置"""
        return self.recipe_data.get("quality_rates", {})