# handlers/sect_building_handler.py
"""宗门建筑处理器"""

from datetime import datetime, timedelta
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required
import json

__all__ = ["SectBuildingHandler"]

class SectBuildingHandler:
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    @player_required
    async def handle_sect_buildings(self, player: Player, event: AstrMessageEvent):
        """查看宗门建筑"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门。")
            return

        sect = await self.db.get_sect_by_id(player.sect_id)
        if not sect:
            yield event.plain_result("宗门信息异常。")
            return

        buildings_config = self.config_manager.sect_buildings_data
        owned_buildings = await self.db.get_all_sect_buildings(player.sect_id)
        owned_map = {b["building_id"]: b for b in owned_buildings}

        lines = [f"=== {sect['name']} 宗门建筑 ==="]
        lines.append(f"宗门资金：{sect['funds']} 灵石")
        lines.append("")

        for bid, bconfig in buildings_config.items():
            name = bconfig.get("name", bid)
            desc = bconfig.get("description", "")
            max_level = bconfig.get("max_level", 3)
            
            if bid in owned_map:
                level = owned_map[bid]["level"]
                lines.append(f"✦ {name} Lv.{level}/{max_level}")
                lines.append(f"   {desc}")
                
                level_info = bconfig.get("levels", {}).get(str(level), {})
                buff_value = level_info.get("buff_value", 0)
                buff_type = level_info.get("buff_type", "")
                daily_acts = level_info.get("daily_activations", 0)
                
                if buff_type:
                    lines.append(f"   效果: +{buff_value}% | 每日可激活{daily_acts}次")
                
                if level < max_level:
                    next_info = bconfig.get("levels", {}).get(str(level + 1), {})
                    gold_cost = next_info.get("gold_cost", 0)
                    crystal_cost = next_info.get("crystal_cost", 0)
                    lines.append(f"   升级: {gold_cost}灵石 + {crystal_cost}灵晶")
            else:
                lines.append(f"🔒 {name} (未建造)")
                lines.append(f"   {desc}")
                first_level = bconfig.get("levels", {}).get("1", {})
                gold_cost = first_level.get("gold_cost", 0)
                crystal_cost = first_level.get("crystal_cost", 0)
                lines.append(f"   建造: {gold_cost}灵石 + {crystal_cost}灵晶")
            lines.append("")

        lines.append("指令：")
        lines.append("  建造建筑 <建筑名> - 建造新建筑")
        lines.append("  升级建筑 <建筑名> - 升级建筑")
        lines.append("  激活建筑 <建筑名> - 激活建筑Buff")
        lines.append("=" * 20)

        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_build(self, player: Player, event: AstrMessageEvent, building_name: str):
        """建造宗门建筑"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门。")
            return

        sect = await self.db.get_sect_by_id(player.sect_id)
        if sect["leader_id"] != player.user_id:
            yield event.plain_result("只有宗主可以建造建筑。")
            return

        building_id, building_config = self._find_building_by_name(building_name)
        if not building_config:
            yield event.plain_result(f"未找到建筑「{building_name}」。")
            return

        existing = await self.db.get_sect_building(player.sect_id, building_id)
        if existing:
            yield event.plain_result(f"「{building_name}」已存在，可使用「升级建筑 {building_name}」进行升级。")
            return

        first_level = building_config.get("levels", {}).get("1", {})
        gold_cost = first_level.get("gold_cost", 0)
        crystal_cost = first_level.get("crystal_cost", 0)

        if sect["funds"] < gold_cost:
            yield event.plain_result(f"宗门资金不足！需要{gold_cost}灵石，当前{sect['funds']}。")
            return

        player_crystals = self._get_player_crystals(player)
        if player_crystals < crystal_cost:
            yield event.plain_result(f"灵晶不足！需要{crystal_cost}个，你有{player_crystals}个。可在宗门商店兑换。")
            return

        await self.db.use_sect_funds(player.sect_id, gold_cost)
        self._consume_player_crystals(player, crystal_cost)
        await self.db.update_player(player)
        await self.db.create_sect_building(player.sect_id, building_id)

        yield event.plain_result(
            f"建造成功！\n"
            f"「{building_name}」已建成 Lv.1\n"
            f"消耗: {gold_cost}宗门灵石 + {crystal_cost}灵晶"
        )

    @player_required
    async def handle_upgrade_building(self, player: Player, event: AstrMessageEvent, building_name: str):
        """升级宗门建筑"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门。")
            return

        sect = await self.db.get_sect_by_id(player.sect_id)
        if sect["leader_id"] != player.user_id:
            yield event.plain_result("只有宗主可以升级建筑。")
            return

        building_id, building_config = self._find_building_by_name(building_name)
        if not building_config:
            yield event.plain_result(f"未找到建筑「{building_name}」。")
            return

        existing = await self.db.get_sect_building(player.sect_id, building_id)
        if not existing:
            yield event.plain_result(f"「{building_name}」尚未建造。")
            return

        current_level = existing["level"]
        max_level = building_config.get("max_level", 3)
        
        if current_level >= max_level:
            yield event.plain_result(f"「{building_name}」已达到最高等级 Lv.{max_level}。")
            return

        next_level = current_level + 1
        level_info = building_config.get("levels", {}).get(str(next_level), {})
        gold_cost = level_info.get("gold_cost", 0)
        crystal_cost = level_info.get("crystal_cost", 0)

        if sect["funds"] < gold_cost:
            yield event.plain_result(f"宗门资金不足！需要{gold_cost}灵石，当前{sect['funds']}。")
            return

        player_crystals = self._get_player_crystals(player)
        if player_crystals < crystal_cost:
            yield event.plain_result(f"灵晶不足！需要{crystal_cost}个，你有{player_crystals}个。")
            return

        await self.db.use_sect_funds(player.sect_id, gold_cost)
        self._consume_player_crystals(player, crystal_cost)
        await self.db.update_player(player)
        await self.db.upgrade_sect_building(player.sect_id, building_id, next_level)

        yield event.plain_result(
            f"升级成功！\n"
            f"「{building_name}」升至 Lv.{next_level}\n"
            f"消耗: {gold_cost}宗门灵石 + {crystal_cost}灵晶"
        )

    @player_required
    async def handle_activate_building(self, player: Player, event: AstrMessageEvent, building_name: str):
        """激活宗门建筑Buff"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门。")
            return

        building_id, building_config = self._find_building_by_name(building_name)
        if not building_config:
            yield event.plain_result(f"未找到建筑「{building_name}」。")
            return

        existing = await self.db.get_sect_building(player.sect_id, building_id)
        if not existing:
            yield event.plain_result(f"「{building_name}」尚未建造。")
            return

        level = existing["level"]
        level_info = building_config.get("levels", {}).get(str(level), {})
        daily_activations = level_info.get("daily_activations", 0)
        
        if daily_activations == 0:
            yield event.plain_result(f"「{building_name}」无法激活。")
            return

        today = datetime.now().strftime("%Y-%m-%d")
        activated_today = await self.db.get_sect_building_buff_count(player.sect_id, building_id, today)
        
        if activated_today >= daily_activations:
            yield event.plain_result(f"「{building_name}」今日激活次数已用完（{activated_today}/{daily_activations}）。")
            return

        duration_hours = level_info.get("duration_hours", 6)
        buff_type = level_info.get("buff_type", "")
        buff_value = level_info.get("buff_value", 0)

        expires_at = (datetime.now() + timedelta(hours=duration_hours)).strftime("%Y-%m-%d %H:%M:%S")
        await self.db.add_sect_building_buff(player.sect_id, building_id, expires_at)

        members = await self.db.get_sect_members(player.sect_id)
        for member in members:
            await self._apply_building_buff_to_player(member, buff_type, buff_value, duration_hours)

        yield event.plain_result(
            f"激活成功！\n"
            f"「{building_name}」已激活\n"
            f"效果: {self._get_buff_description(buff_type, buff_value)}\n"
            f"持续: {duration_hours}小时\n"
            f"今日剩余: {daily_activations - activated_today - 1}次"
        )

    def _find_building_by_name(self, name: str):
        """根据名称查找建筑配置"""
        for bid, bconfig in self.config_manager.sect_buildings_data.items():
            if bconfig.get("name") == name:
                return bid, bconfig
        return None, None

    def _get_player_crystals(self, player: Player) -> int:
        """获取玩家的灵晶数量"""
        extras = json.loads(player.extra_data) if player.extra_data else {}
        sect_mats = extras.get("sect_materials", {})
        return sect_mats.get("crystal", 0)

    def _consume_player_crystals(self, player: Player, amount: int):
        """消耗玩家的灵晶"""
        extras = json.loads(player.extra_data) if player.extra_data else {}
        sect_mats = extras.get("sect_materials", {})
        sect_mats["crystal"] = sect_mats.get("crystal", 0) - amount
        extras["sect_materials"] = sect_mats
        player.extra_data = json.dumps(extras)

    async def _apply_building_buff_to_player(self, player: Player, buff_type: str, buff_value: int, duration_hours: int):
        """给玩家应用建筑Buff"""
        import time
        buffs = json.loads(player.active_buffs) if player.active_buffs else []
        buff = {
            "type": buff_type,
            "value": buff_value,
            "source": "sect_building",
            "expires_at": time.time() + duration_hours * 3600
        }
        buffs.append(buff)
        player.active_buffs = json.dumps(buffs)
        await self.db.update_player(player)

    def _get_buff_description(self, buff_type: str, buff_value: int) -> str:
        """获取Buff描述"""
        desc_map = {
            "cultivation_speed": f"修炼速度+{buff_value}%",
            "alchemy_success": f"炼丹成功率+{buff_value}%",
        }
        return desc_map.get(buff_type, f"{buff_type}+{buff_value}")
