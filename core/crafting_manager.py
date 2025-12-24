# core/crafting_manager.py
"""炼丹/炼器系统核心逻辑"""

import random
from typing import Tuple, Optional, Dict, List, Any

from astrbot.api import AstrBotConfig
from ..models import Player
from ..data import DataBase
from ..config_manager import ConfigManager


class CraftingManager:
    """炼丹/炼器管理器"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    def get_crafter_level(self, exp: int) -> int:
        """根据熟练度计算等级"""
        crafter_levels = self.config_manager.recipe_data.get("crafter_levels", {})
        level = 1
        for lvl_str, info in crafter_levels.items():
            lvl = int(lvl_str)
            if exp >= info.get("exp_required", 0):
                level = max(level, lvl)
        return level

    def get_crafter_title(self, level: int, craft_type: str) -> str:
        """获取炼丹师/炼器师称号"""
        info = self.config_manager.get_crafter_level_info(level)
        if not info:
            return "学徒"
        title = info.get("name", "学徒")
        if craft_type == "smithing" and "/" in title:
            return title.split("/")[1]
        elif craft_type == "alchemy" and "/" in title:
            return title.split("/")[0]
        return title

    def calculate_success_rate(self, player: Player, recipe: dict, craft_type: str) -> float:
        """计算炼制成功率"""
        base_rate = recipe.get("base_success_rate", 0.5)
        
        if craft_type == "alchemy":
            furnace_info = self.config_manager.get_furnace_info(player.furnace_level)
            station_bonus = furnace_info.get("success_bonus", 0) if furnace_info else 0
            crafter_level = player.alchemy_level
        else:
            forge_info = self.config_manager.get_forge_info(player.forge_level)
            station_bonus = forge_info.get("success_bonus", 0) if forge_info else 0
            crafter_level = player.smithing_level
        
        level_bonus = (crafter_level - 1) * 0.02
        final_rate = min(0.95, base_rate + station_bonus + level_bonus)
        return final_rate

    def calculate_quality(self, player: Player, craft_type: str) -> Tuple[str, float]:
        """计算产出品质，返回 (品质名, 效果倍率)"""
        quality_rates = self.config_manager.get_quality_rates()
        
        if craft_type == "alchemy":
            furnace_info = self.config_manager.get_furnace_info(player.furnace_level)
            quality_bonus = furnace_info.get("quality_bonus", 0) if furnace_info else 0
        else:
            forge_info = self.config_manager.get_forge_info(player.forge_level)
            quality_bonus = forge_info.get("quality_bonus", 0) if forge_info else 0
        
        rand = random.random()
        cumulative = 0
        
        adjusted_rates = {}
        total_rate = 0
        for quality, info in quality_rates.items():
            rate = info.get("rate", 0)
            if quality in ["完美", "传说"]:
                rate = min(0.5, rate + quality_bonus)
            elif quality == "残次":
                rate = max(0.05, rate - quality_bonus)
            adjusted_rates[quality] = rate
            total_rate += rate
        
        for quality in ["残次", "普通", "精良", "完美", "传说"]:
            if quality in adjusted_rates:
                cumulative += adjusted_rates[quality] / total_rate
                if rand <= cumulative:
                    return quality, quality_rates[quality].get("multiplier", 1.0)
        
        return "普通", 1.0

    async def craft_item(self, player: Player, recipe_id: str, craft_type: str) -> Tuple[bool, str, Optional[Player]]:
        """执行炼制操作"""
        recipe_result = self.config_manager.get_recipe_by_id(recipe_id)
        if not recipe_result:
            return False, "配方不存在。", None
        
        recipe, _ = recipe_result
        
        required_level = recipe.get("required_level", 1)
        crafter_level = player.alchemy_level if craft_type == "alchemy" else player.smithing_level
        if crafter_level < required_level:
            title = "炼丹师" if craft_type == "alchemy" else "炼器师"
            return False, f"需要{title}等级达到 {required_level} 级才能炼制此配方。", None
        
        required_realm = recipe.get("required_realm", 0)
        if player.level_index < required_realm:
            return False, f"境界不足，无法炼制此配方。", None
        
        materials = recipe.get("materials", {})
        has_materials, missing = await self.db.check_materials(player.user_id, materials)
        if not has_materials:
            missing_names = []
            for item_id in missing:
                item = self.config_manager.item_data.get(item_id)
                name = item.name if item else f"未知物品({item_id})"
                missing_names.append(name)
            return False, f"材料不足：{', '.join(missing_names)}", None
        
        success_rate = self.calculate_success_rate(player, recipe, craft_type)
        is_success = random.random() < success_rate
        
        p_clone = player.clone()
        exp_reward = recipe.get("exp_reward", 1)
        
        if is_success:
            quality, multiplier = self.calculate_quality(player, craft_type)
            output_id = recipe.get("output_id")
            output_min = recipe.get("output_min", 1)
            output_max = recipe.get("output_max", 1)
            base_count = random.randint(output_min, output_max)
            output_count = max(1, int(base_count * multiplier))
            
            success, reason = await self.db.transactional_craft_item(
                player.user_id, materials, output_id, output_count
            )
            
            if not success:
                return False, "炼制过程中发生错误，请稍后再试。", None
            
            if craft_type == "alchemy":
                p_clone.alchemy_exp += exp_reward
                p_clone.alchemy_level = self.get_crafter_level(p_clone.alchemy_exp)
            else:
                p_clone.smithing_exp += exp_reward
                p_clone.smithing_level = self.get_crafter_level(p_clone.smithing_exp)
            
            await self.db.update_player(p_clone)
            
            output_item = self.config_manager.item_data.get(output_id)
            output_name = output_item.name if output_item else "未知物品"
            
            await self.db.record_crafting(player.user_id, craft_type, recipe_id, True, quality, output_count)
            
            quality_colors = {"残次": "灰", "普通": "白", "精良": "绿", "完美": "蓝", "传说": "紫"}
            color = quality_colors.get(quality, "白")
            
            msg = (
                f"🎉 炼制成功！\n"
                f"品质：【{quality}】({color})\n"
                f"获得：「{output_name}」x{output_count}\n"
                f"熟练度：+{exp_reward}"
            )
            return True, msg, p_clone
        else:
            success, _ = await self.db.transactional_craft_fail(player.user_id, materials, 0.5)
            
            if craft_type == "alchemy":
                p_clone.alchemy_exp += 1
                p_clone.alchemy_level = self.get_crafter_level(p_clone.alchemy_exp)
            else:
                p_clone.smithing_exp += 1
                p_clone.smithing_level = self.get_crafter_level(p_clone.smithing_exp)
            
            await self.db.update_player(p_clone)
            await self.db.record_crafting(player.user_id, craft_type, recipe_id, False, None, 0)
            
            msg = (
                f"💥 炼制失败！\n"
                f"损失了50%的材料...\n"
                f"熟练度：+1"
            )
            return False, msg, p_clone

    async def upgrade_station(self, player: Player, station_type: str) -> Tuple[bool, str, Optional[Player]]:
        """升级丹炉/炼器台"""
        if station_type == "furnace":
            current_level = player.furnace_level
            next_level = current_level + 1
            station_info = self.config_manager.get_furnace_info(next_level)
            station_name = "丹炉"
            crafter_level = player.alchemy_level
        else:
            current_level = player.forge_level
            next_level = current_level + 1
            station_info = self.config_manager.get_forge_info(next_level)
            station_name = "炼器台"
            crafter_level = player.smithing_level
        
        if not station_info:
            return False, f"你的{station_name}已经是最高等级了！", None
        
        required_level = station_info.get("required_level", 1)
        if crafter_level < required_level:
            title = "炼丹师" if station_type == "furnace" else "炼器师"
            return False, f"需要{title}等级达到 {required_level} 级才能升级。", None
        
        cost = station_info.get("price", 0)
        if player.gold < cost:
            return False, f"灵石不足！升级需要 {cost} 灵石，你只有 {player.gold} 灵石。", None
        
        p_clone = player.clone()
        p_clone.gold -= cost
        
        if station_type == "furnace":
            p_clone.furnace_level = next_level
        else:
            p_clone.forge_level = next_level
        
        await self.db.update_player(p_clone)
        
        new_name = station_info.get("name", f"{next_level}级{station_name}")
        success_bonus = station_info.get("success_bonus", 0) * 100
        quality_bonus = station_info.get("quality_bonus", 0) * 100
        
        msg = (
            f"🔧 升级成功！\n"
            f"「{new_name}」\n"
            f"成功率加成：+{success_bonus:.0f}%\n"
            f"品质加成：+{quality_bonus:.0f}%\n"
            f"消耗灵石：{cost}"
        )
        return True, msg, p_clone

    def get_recipe_info_text(self, recipe_id: str, player: Player) -> Optional[str]:
        """获取配方详情文本"""
        recipe_result = self.config_manager.get_recipe_by_id(recipe_id)
        if not recipe_result:
            return None
        
        recipe, craft_type = recipe_result
        
        output_id = recipe.get("output_id")
        output_item = self.config_manager.item_data.get(output_id)
        output_name = output_item.name if output_item else "未知物品"
        
        materials_text = []
        for item_id, quantity in recipe.get("materials", {}).items():
            item = self.config_manager.item_data.get(item_id)
            name = item.name if item else f"未知({item_id})"
            materials_text.append(f"  {name} x{quantity}")
        
        success_rate = self.calculate_success_rate(player, recipe, craft_type)
        
        lines = [
            f"═══ 【{recipe.get('name', '未知配方')}】 ═══",
            f"产出：「{output_name}」",
            f"数量：{recipe.get('output_min', 1)}-{recipe.get('output_max', 1)}",
            f"成功率：{success_rate*100:.1f}%",
            f"所需材料：",
            *materials_text,
            f"熟练度奖励：+{recipe.get('exp_reward', 1)}",
            "═══════════════════"
        ]
        
        return "\n".join(lines)
