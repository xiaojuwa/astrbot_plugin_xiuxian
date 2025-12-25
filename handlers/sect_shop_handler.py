# handlers/sect_shop_handler.py
"""宗门商店处理器 - v2.7.0"""

from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required
from datetime import date

__all__ = ["SectShopHandler"]

class SectShopHandler:
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    @player_required
    async def handle_sect_shop(self, player: Player, event: AstrMessageEvent):
        """显示宗门商店"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门，无法访问宗门商店。")
            return

        sect = await self.db.get_sect_by_id(player.sect_id)
        if not sect:
            yield event.plain_result("宗门信息异常。")
            return

        sect_level = sect.get('level', 1)
        
        lines = ["=== 宗门商店 ==="]
        lines.append(f"你的贡献度：{player.sect_contribution}")
        lines.append("")
        lines.append("【可兑换物品】")
        
        for item_id, item_info in self.config_manager.sect_shop_data.items():
            name = item_info.get('name', '未知')
            cost = item_info.get('contribution_cost', 0)
            required_level = item_info.get('sect_level_required', 1)
            daily_limit = item_info.get('daily_limit', 0)
            desc = item_info.get('description', '')
            
            if sect_level < required_level:
                lines.append(f"🔒 {name} - 需宗门Lv{required_level}")
                continue
            
            limit_str = f"(限{daily_limit}/天)" if daily_limit > 0 else ""
            lines.append(f"� {name} - {cost}贡献 {limit_str}")
            lines.append(f"   {desc}")
        
        lines.append("")
        lines.append("使用「兑换 <物品名> [数量]」进行兑换")
        lines.append("=" * 20)
        
        yield event.plain_result("\n".join(lines))

    @player_required  
    async def handle_sect_exchange(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: str = "1"):
        """兑换宗门商品"""
        if not player.sect_id:
            yield event.plain_result("你尚未加入任何宗门。")
            return

        try:
            qty = int(quantity)
            if qty <= 0:
                raise ValueError
        except:
            yield event.plain_result("数量必须为正整数。")
            return

        # 查找商品
        item_id = None
        item_info = None
        for iid, info in self.config_manager.sect_shop_data.items():
            if info.get('name') == item_name:
                item_id = iid
                item_info = info
                break
        
        if not item_info:
            yield event.plain_result(f"商店中没有「{item_name}」。")
            return

        # 检查宗门等级
        sect = await self.db.get_sect_by_id(player.sect_id)
        required_level = item_info.get('sect_level_required', 1)
        if sect.get('level', 1) < required_level:
            yield event.plain_result(f"宗门等级不足，需要Lv{required_level}。")
            return

        # 检查限购
        daily_limit = item_info.get('daily_limit', 0)
        if daily_limit > 0:
            today = date.today().isoformat()
            purchased = await self.db.get_sect_shop_purchase_count(player.user_id, item_id, today)
            if purchased + qty > daily_limit:
                yield event.plain_result(f"超过每日限购！今日已购{purchased}/{daily_limit}，最多还能买{daily_limit - purchased}个。")
                return

        # 检查贡献度
        total_cost = item_info.get('contribution_cost', 0) * qty
        if player.sect_contribution < total_cost:
            yield event.plain_result(f"贡献度不足！需要{total_cost}，你有{player.sect_contribution}。")
            return

        # 扣除贡献度
        player.sect_contribution -= total_cost
        
        # 发放奖励
        effect = item_info.get('effect', {})
        effect_type = effect.get('type')
        
        msg = f"兑换成功！消耗{total_cost}贡献度，剩余{player.sect_contribution}。\n"
        
        if effect_type == 'add_exp':
            player.experience += effect.get('value', 0) * qty
            msg += f"获得{effect.get('value', 0) * qty}修为。"
        elif effect_type == 'material':
            mat_id = effect.get('item_id')
            mat_qty = effect.get('quantity', 1) * qty
            await self.db.add_items_to_inventory_in_transaction(player.user_id, {mat_id: mat_qty})
            msg += f"获得材料x{mat_qty}。"
        elif effect_type == 'buff':
            # 添加Buff到active_buffs
            import json, time
            buffs = json.loads(player.active_buffs) if player.active_buffs else []
            buff = {
                "type": "combat",
                "attack": effect.get('attack', 0),
                "defense": effect.get('defense', 0),
                "duration": effect.get('duration', 5),
                "applied_at": time.time()
            }
            buffs.append(buff)
            player.active_buffs = json.dumps(buffs)
            msg += f"获得战斗Buff（攻击+{effect.get('attack',0)} 防御+{effect.get('defense',0)} {effect.get('duration',5)}场）。"
        else:
            msg += "物品效果已发放。"
        
        # 记录限购
        if daily_limit > 0:
            today = date.today().isoformat()
            await self.db.increment_sect_shop_purchase(player.user_id, item_id, today, qty)
        
        await self.db.update_player(player)
        yield event.plain_result(msg)
