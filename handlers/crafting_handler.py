# handlers/crafting_handler.py
"""炼丹/炼器系统指令处理器"""

from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player
from ..core.crafting_manager import CraftingManager
from .utils import player_required

__all__ = ["CraftingHandler"]


class CraftingHandler:
    """炼丹/炼器系统相关指令处理器"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.crafting_manager = CraftingManager(db, config, config_manager)

    @player_required
    async def handle_alchemy(self, player: Player, event: AstrMessageEvent):
        """查看炼丹界面"""
        furnace_info = self.config_manager.get_furnace_info(player.furnace_level)
        furnace_name = furnace_info.get("name", "凡铁丹炉") if furnace_info else "凡铁丹炉"
        
        title = self.crafting_manager.get_crafter_title(player.alchemy_level, "alchemy")
        next_level_info = self.config_manager.get_crafter_level_info(player.alchemy_level + 1)
        
        if next_level_info:
            exp_needed = next_level_info.get("exp_required", 0) - player.alchemy_exp
            exp_text = f"{player.alchemy_exp} (距下级还需 {exp_needed})"
        else:
            exp_text = f"{player.alchemy_exp} (已满级)"
        
        recipes = self.config_manager.get_all_recipes("alchemy")
        available_recipes = []
        for recipe_id, recipe in recipes.items():
            req_level = recipe.get("required_level", 1)
            req_realm = recipe.get("required_realm", 0)
            if player.alchemy_level >= req_level and player.level_index >= req_realm:
                output_id = recipe.get("output_id")
                output_item = self.config_manager.item_data.get(output_id)
                output_name = output_item.name if output_item else "未知"
                available_recipes.append(f"  {recipe.get('name')} → {output_name}")
        
        lines = [
            "═══ 【炼丹界面】 ═══",
            f"🔥 丹炉：{furnace_name} (Lv.{player.furnace_level})",
            f"📜 炼丹师：{title} (Lv.{player.alchemy_level})",
            f"📊 熟练度：{exp_text}",
            "",
            "--- 可用配方 ---",
            *available_recipes[:10] if available_recipes else ["  暂无可用配方"],
            "",
            "💡 指令：",
            "  「炼丹 <配方名>」炼制丹药",
            "  「升级丹炉」升级丹炉",
            "  「配方 <配方名>」查看配方详情",
            "═══════════════════"
        ]
        
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_smithing(self, player: Player, event: AstrMessageEvent):
        """查看炼器界面"""
        forge_info = self.config_manager.get_forge_info(player.forge_level)
        forge_name = forge_info.get("name", "简易炼器台") if forge_info else "简易炼器台"
        
        title = self.crafting_manager.get_crafter_title(player.smithing_level, "smithing")
        next_level_info = self.config_manager.get_crafter_level_info(player.smithing_level + 1)
        
        if next_level_info:
            exp_needed = next_level_info.get("exp_required", 0) - player.smithing_exp
            exp_text = f"{player.smithing_exp} (距下级还需 {exp_needed})"
        else:
            exp_text = f"{player.smithing_exp} (已满级)"
        
        recipes = self.config_manager.get_all_recipes("smithing")
        available_recipes = []
        for recipe_id, recipe in recipes.items():
            req_level = recipe.get("required_level", 1)
            req_realm = recipe.get("required_realm", 0)
            if player.smithing_level >= req_level and player.level_index >= req_realm:
                output_id = recipe.get("output_id")
                output_item = self.config_manager.item_data.get(output_id)
                output_name = output_item.name if output_item else "未知"
                available_recipes.append(f"  {recipe.get('name')} → {output_name}")
        
        lines = [
            "═══ 【炼器界面】 ═══",
            f"🔨 炼器台：{forge_name} (Lv.{player.forge_level})",
            f"📜 炼器师：{title} (Lv.{player.smithing_level})",
            f"📊 熟练度：{exp_text}",
            "",
            "--- 可用配方 ---",
            *available_recipes[:10] if available_recipes else ["  暂无可用配方"],
            "",
            "💡 指令：",
            "  「炼器 <配方名>」炼制法器",
            "  「升级炼器台」升级炼器台",
            "  「配方 <配方名>」查看配方详情",
            "═══════════════════"
        ]
        
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_craft_alchemy(self, player: Player, event: AstrMessageEvent, recipe_name: str):
        """炼制丹药"""
        if not recipe_name:
            yield event.plain_result("请指定要炼制的配方名称。用法：「炼丹 <配方名>」")
            return
        
        recipe_result = self.config_manager.get_recipe_by_name(recipe_name)
        if not recipe_result:
            yield event.plain_result(f"未找到名为「{recipe_name}」的配方。")
            return
        
        recipe_id, recipe, craft_type = recipe_result
        if craft_type != "alchemy":
            yield event.plain_result(f"「{recipe_name}」不是炼丹配方，请使用「炼器」指令。")
            return
        
        if player.state != "空闲":
            yield event.plain_result(f"道友当前正在「{player.state}」中，无法炼丹。")
            return
        
        success, msg, _ = await self.crafting_manager.craft_item(player, recipe_id, "alchemy")
        yield event.plain_result(msg)

    @player_required
    async def handle_craft_smithing(self, player: Player, event: AstrMessageEvent, recipe_name: str):
        """炼制法器"""
        if not recipe_name:
            yield event.plain_result("请指定要炼制的配方名称。用法：「炼器 <配方名>」")
            return
        
        recipe_result = self.config_manager.get_recipe_by_name(recipe_name)
        if not recipe_result:
            yield event.plain_result(f"未找到名为「{recipe_name}」的配方。")
            return
        
        recipe_id, recipe, craft_type = recipe_result
        if craft_type != "smithing":
            yield event.plain_result(f"「{recipe_name}」不是炼器配方，请使用「炼丹」指令。")
            return
        
        if player.state != "空闲":
            yield event.plain_result(f"道友当前正在「{player.state}」中，无法炼器。")
            return
        
        success, msg, _ = await self.crafting_manager.craft_item(player, recipe_id, "smithing")
        yield event.plain_result(msg)

    @player_required
    async def handle_upgrade_furnace(self, player: Player, event: AstrMessageEvent):
        """升级丹炉"""
        success, msg, _ = await self.crafting_manager.upgrade_station(player, "furnace")
        yield event.plain_result(msg)

    @player_required
    async def handle_upgrade_forge(self, player: Player, event: AstrMessageEvent):
        """升级炼器台"""
        success, msg, _ = await self.crafting_manager.upgrade_station(player, "forge")
        yield event.plain_result(msg)

    @player_required
    async def handle_recipe_info(self, player: Player, event: AstrMessageEvent, recipe_name: str):
        """查看配方详情"""
        if not recipe_name:
            yield event.plain_result("请指定配方名称。用法：「配方 <配方名>」")
            return
        
        recipe_result = self.config_manager.get_recipe_by_name(recipe_name)
        if not recipe_result:
            yield event.plain_result(f"未找到名为「{recipe_name}」的配方。")
            return
        
        recipe_id, _, _ = recipe_result
        info_text = self.crafting_manager.get_recipe_info_text(recipe_id, player)
        if info_text:
            yield event.plain_result(info_text)
        else:
            yield event.plain_result("无法获取配方信息。")

    @player_required
    async def handle_recipe_list(self, player: Player, event: AstrMessageEvent):
        """查看所有配方"""
        alchemy_recipes = self.config_manager.get_all_recipes("alchemy")
        smithing_recipes = self.config_manager.get_all_recipes("smithing")
        
        lines = ["═══ 【配方图鉴】 ═══", "", "--- 炼丹配方 ---"]
        
        for recipe_id, recipe in alchemy_recipes.items():
            req_level = recipe.get("required_level", 1)
            can_craft = "✓" if player.alchemy_level >= req_level else "✗"
            output_id = recipe.get("output_id")
            output_item = self.config_manager.item_data.get(output_id)
            output_name = output_item.name if output_item else "未知"
            lines.append(f"[{can_craft}] {recipe.get('name')} → {output_name} (需Lv.{req_level})")
        
        lines.extend(["", "--- 炼器配方 ---"])
        
        for recipe_id, recipe in smithing_recipes.items():
            req_level = recipe.get("required_level", 1)
            can_craft = "✓" if player.smithing_level >= req_level else "✗"
            output_id = recipe.get("output_id")
            output_item = self.config_manager.item_data.get(output_id)
            output_name = output_item.name if output_item else "未知"
            lines.append(f"[{can_craft}] {recipe.get('name')} → {output_name} (需Lv.{req_level})")
        
        lines.append("═══════════════════")
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_materials(self, player: Player, event: AstrMessageEvent):
        """查看材料图鉴"""
        materials = [item for item in self.config_manager.item_data.values() if item.type == "材料"]
        materials.sort(key=lambda x: (x.rank, x.price))
        
        rank_order = {"凡品": 0, "珍品": 1, "圣品": 2, "帝品": 3}
        
        lines = ["═══ 【材料图鉴】 ═══"]
        current_rank = None
        
        for item in materials:
            if item.rank != current_rank:
                current_rank = item.rank
                lines.append(f"\n--- {current_rank} ---")
            lines.append(f"「{item.name}」{item.price}灵石 - {item.description[:20]}...")
        
        lines.append("\n═══════════════════")
        yield event.plain_result("\n".join(lines))
