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
            lines.append(f"✦ {name} - {cost}贡献 {limit_str}")
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
            exp_gain = effect.get('value', 0) * qty
            player.experience += exp_gain
            msg += f"获得{exp_gain}修为。"
        elif effect_type == 'material':
            mat_id = effect.get('item_id')
            mat_qty = effect.get('quantity', 1) * qty
            await self.db.add_items_to_inventory_in_transaction(player.user_id, {mat_id: mat_qty})
            msg += f"获得材料x{mat_qty}。"
        elif effect_type == 'random_material':
            # 随机材料礼包
            import random
            count = effect.get('count', 1) * qty
            rank = effect.get('rank', '普通')
            materials = self.config_manager.get_materials_by_rank(rank)
            if materials:
                items_gained = {}
                for _ in range(count):
                    mat = random.choice(materials)
                    mat_id = mat.get('id')
                    if mat_id:
                        items_gained[mat_id] = items_gained.get(mat_id, 0) + 1
                await self.db.add_items_to_inventory_in_transaction(player.user_id, items_gained)
                msg += f"获得{count}个随机{rank}材料。"
            else:
                msg += "材料获取失败。"
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
        elif effect_type == 'cultivation_buff':
            # 修炼加速Buff
            import json, time
            buffs = json.loads(player.active_buffs) if player.active_buffs else []
            buff = {
                "type": "cultivation",
                "value": effect.get('value', 0),
                "expires_at": time.time() + effect.get('duration_minutes', 60) * 60
            }
            buffs.append(buff)
            player.active_buffs = json.dumps(buffs)
            msg += f"获得修炼加速Buff（+{effect.get('value',0)}% {effect.get('duration_minutes',60)}分钟）。"
        elif effect_type == 'breakthrough_bonus':
            # 突破加成丹药 - 存储到玩家状态
            import json
            extras = json.loads(player.extra_data) if player.extra_data else {}
            extras['breakthrough_bonus'] = extras.get('breakthrough_bonus', 0) + effect.get('value', 0) * qty
            player.extra_data = json.dumps(extras)
            msg += f"获得突破成功率+{effect.get('value', 0) * qty}%（下次突破生效）。"
        elif effect_type == 'permanent_buff':
            # 永久属性加成
            stat = effect.get('stat')
            value = effect.get('value', 0) * qty
            if stat == 'attack':
                player.base_attack += value
                msg += f"攻击永久+{value}。"
            elif stat == 'defense':
                player.base_defense += value
                msg += f"防御永久+{value}。"
            else:
                msg += "属性加成已生效。"
        elif effect_type == 'building_material':
            # 建筑材料 - 存入玩家的宗门材料
            import json
            extras = json.loads(player.extra_data) if player.extra_data else {}
            sect_mats = extras.get('sect_materials', {})
            mat_type = effect.get('material_type', 'unknown')
            sect_mats[mat_type] = sect_mats.get(mat_type, 0) + qty
            extras['sect_materials'] = sect_mats
            player.extra_data = json.dumps(extras)
            msg += f"获得宗门建材「{mat_type}」x{qty}。"
        elif effect_type == 'random_item':
            # 随机物品福袋
            import random
            min_rank = effect.get('min_rank', '普通')
            max_rank = effect.get('max_rank', '传说')
            items = self.config_manager.get_items_by_rank_range(min_rank, max_rank)
            if items:
                for _ in range(qty):
                    item = random.choice(items)
                    item_id = item.get('id')
                    if item_id:
                        await self.db.add_items_to_inventory_in_transaction(player.user_id, {item_id: 1})
                msg += f"从福袋中获得{qty}件物品！"
            else:
                msg += "福袋开启失败。"
        else:
            msg += "物品效果已发放。"
        
        # 记录限购
        if daily_limit > 0:
            today = date.today().isoformat()
            await self.db.increment_sect_shop_purchase(player.user_id, item_id, today, qty)
        
        await self.db.update_player(player)
        yield event.plain_result(msg)
