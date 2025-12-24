# handlers/shop_handler.py
import random
from datetime import datetime, date
from typing import Optional, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player, PlayerEffect, Item
from .utils import player_required

CMD_BUY = "购买"
CMD_USE_ITEM = "使用"
CMD_SELL = "出售"
MAX_DAILY_SELL = 5  # 每日最大回购次数
SELL_RATIO = 0.4    # 回购价格比例（40%）

__all__ = ["ShopHandler"]

def calculate_item_effect(item_info: Optional[Item], quantity: int) -> Tuple[Optional[PlayerEffect], str]:
    if not item_info or not (effect_config := item_info.effect):
        return None, f"【{item_info.name if item_info else '未知物品'}】似乎只是凡物，无法使用。"

    effect = PlayerEffect()
    messages = []

    effect_type = effect_config.get("type")
    value = effect_config.get("value", 0) * quantity

    if effect_type == "add_experience":
        effect.experience = value
        messages.append(f"修为增加了 {value} 点")
    elif effect_type == "add_gold":
        effect.gold = value
        messages.append(f"灵石增加了 {value} 点")
    elif effect_type == "add_hp":
        effect.hp = value
        messages.append(f"恢复了 {value} 点生命")
    else:
         return None, f"你研究了半天，也没能参透【{item_info.name}】的用法。"

    full_message = f"你使用了 {quantity} 个【{item_info.name}】，" + "，".join(messages) + "！"
    return effect, full_message

class ShopHandler:
    # 坊市相关指令处理器
    
    def __init__(self, db: DataBase, config_manager: ConfigManager, config: AstrBotConfig):
        self.db = db
        self.config_manager = config_manager
        self.config = config
        self.daily_task_handler = None  # 延迟注入
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler

    async def handle_shop(self, event: AstrMessageEvent):
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 获取所有可售卖的商品
        all_sellable_items = [item for item in self.config_manager.item_data.values() if item.price > 0]
        
        # 从配置中获取每日商品数量
        item_count = self.config["VALUES"].get("SHOP_DAILY_ITEM_COUNT", 8)

        if not all_sellable_items:
            yield event.plain_result("今日坊市暂无商品。")
            return
        
        # 确保每日商城必有回血药
        healing_items = [item for item in all_sellable_items 
                        if item.effect and item.effect.get("type") == "add_hp"]
        other_items = [item for item in all_sellable_items 
                      if item not in healing_items]
        
        # 使用当天日期作为随机种子，确保每日商品固定
        today_seed = int(datetime.now().strftime('%Y%m%d'))
        rng = random.Random(today_seed)
        
        # 必定包含1-2个回血药，剩余随机
        daily_items = []
        if healing_items:
            heal_count = min(2, len(healing_items))
            daily_items.extend(rng.sample(healing_items, heal_count))
        
        remaining_count = item_count - len(daily_items)
        if remaining_count > 0 and other_items:
            sample_count = min(remaining_count, len(other_items))
            daily_items.extend(rng.sample(other_items, sample_count))
        
        sorted_items = sorted(daily_items, key=lambda item: item.price)

        lines = [f"─── 坊市 {today} ───"]
        
        for info in sorted_items:
            effect_desc = self._get_item_effect_desc(info)
            lines.append(f"【{info.name}】{info.price}灵石")
            lines.append(f"  {effect_desc}")
        
        lines.append("───────────────")
        lines.append(f"「{CMD_BUY} <名> [数量]」购买")
        
        yield event.plain_result("\n".join(lines))

    def _get_item_effect_desc(self, item: Item) -> str:
        """获取物品效果的简短描述"""
        parts = [f"[{item.rank}]"]
        
        # 丹药效果
        if item.effect:
            effect_type = item.effect.get("type", "")
            value = item.effect.get("value", 0)
            if effect_type == "add_hp":
                parts.append(f"❤️恢复{value}生命")
            elif effect_type == "add_experience":
                parts.append(f"📈+{value}修为")
            elif effect_type == "add_gold":
                parts.append(f"💰+{value}灵石")
        
        # 丹药Buff
        if item.buff_effect:
            buff_type = item.buff_effect.get("type", "")
            value = item.buff_effect.get("value", 0)
            duration = item.buff_effect.get("duration", 0)
            buff_names = {"attack_buff": "攻击", "defense_buff": "防御", "hp_buff": "生命"}
            buff_name = buff_names.get(buff_type, "属性")
            parts.append(f"💫{buff_name}+{value}({duration}场战斗)")
        
        # 装备效果
        if item.equip_effects:
            effects = []
            if item.equip_effects.get("attack"):
                effects.append(f"⚔️+{item.equip_effects['attack']}")
            if item.equip_effects.get("defense"):
                effects.append(f"🛡️+{item.equip_effects['defense']}")
            if item.equip_effects.get("max_hp"):
                effects.append(f"❤️+{item.equip_effects['max_hp']}")
            if effects:
                parts.append(" ".join(effects))
        
        # 功法效果
        if item.skill_effects:
            effects = []
            if item.skill_effects.get("attack"):
                effects.append(f"⚔️永久+{item.skill_effects['attack']}")
            if item.skill_effects.get("defense"):
                effects.append(f"🛡️永久+{item.skill_effects['defense']}")
            if item.skill_effects.get("max_hp"):
                effects.append(f"❤️永久+{item.skill_effects['max_hp']}")
            if effects:
                parts.append(" ".join(effects))
        
        # 材料类无效果
        if len(parts) == 1 and item.type == "材料":
            parts.append("炼器/炼丹材料")
        
        return " ".join(parts)

    @player_required
    async def handle_backpack(self, player: Player, event: AstrMessageEvent):
        inventory = await self.db.get_inventory_by_user_id(player.user_id, self.config_manager)
        if not inventory:
            yield event.plain_result("道友的背包空空如也。")
            return

        reply_msg = f"--- {event.get_sender_name()} 的背包 ---\n"
        for item in inventory:
            reply_msg += f"【{item['name']}】x{item['quantity']} - {item['description']}\n"
        reply_msg += "--------------------------"
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_buy(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: int):
        if not item_name or quantity <= 0:
            yield event.plain_result(f"指令格式错误。正确用法: `{CMD_BUY} <物品名> [数量]`。")
            return

        item_to_buy = self.config_manager.get_item_by_name(item_name)
        if not item_to_buy or item_to_buy[1].price <= 0:
            yield event.plain_result(f"道友，小店中并无「{item_name}」这件商品。")
            return

        item_id_to_add, target_item_info = item_to_buy
        total_cost = target_item_info.price * quantity

        success, reason = await self.db.transactional_buy_item(player.user_id, item_id_to_add, quantity, total_cost)

        if success:
            updated_player = await self.db.get_player_by_id(player.user_id)
            msg = f"购买成功！花费{total_cost}灵石，购得「{item_name}」x{quantity}。"
            if updated_player:
                msg += f"剩余灵石 {updated_player.gold}。"
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "shop_buy")
                if completed:
                    msg += "\n🎯 每日任务「仙市淘宝」已完成！"
            
            yield event.plain_result(msg)
        else:
            if reason == "ERROR_INSUFFICIENT_FUNDS":
                yield event.plain_result(f"灵石不足！购买 {quantity}个「{item_name}」需{total_cost}灵石，你只有{player.gold}。")
            else:
                yield event.plain_result("购买失败，坊市交易繁忙，请稍后再试。")

    @player_required
    async def handle_use(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        if not item_name or quantity <= 0:
            yield event.plain_result(f"指令格式错误。正确用法: `{CMD_USE_ITEM} <物品名> [数量]`。")
            return

        item_to_use = self.config_manager.get_item_by_name(item_name)
        if not item_to_use:
            yield event.plain_result(f"背包中似乎没有名为「{item_name}」的物品。")
            return
        
        target_item_id, target_item_info = item_to_use
        
        # 检查背包数量
        inventory_item = await self.db.get_item_from_inventory(player.user_id, target_item_id)
        if not inventory_item or inventory_item['quantity'] < quantity:
            yield event.plain_result(f"使用失败！你的「{item_name}」数量不足 {quantity} 个。")
            return

        # 根据物品类型执行不同功能
        if target_item_info.type == "法器":
            # 执行装备逻辑
            if quantity > 1:
                yield event.plain_result(f"每次只能装备一件法器。")
                return

            p_clone = player.clone()
            unequipped_item_id = None
            slot_name = target_item_info.subtype

            if slot_name == "武器":
                if p_clone.equipped_weapon: unequipped_item_id = p_clone.equipped_weapon
                p_clone.equipped_weapon = target_item_id
            elif slot_name == "防具":
                if p_clone.equipped_armor: unequipped_item_id = p_clone.equipped_armor
                p_clone.equipped_armor = target_item_id
            elif slot_name == "饰品":
                if p_clone.equipped_accessory: unequipped_item_id = p_clone.equipped_accessory
                p_clone.equipped_accessory = target_item_id
            else:
                yield event.plain_result(f"「{item_name}」似乎不是一件可穿戴的法器。")
                return

            # 更新数据库
            await self.db.remove_item_from_inventory(player.user_id, target_item_id, 1)
            if unequipped_item_id:
                await self.db.add_items_to_inventory_in_transaction(player.user_id, {unequipped_item_id: 1})
            
            await self.db.update_player(p_clone)
            msg = f"已成功装备【{item_name}】。"
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "use_item")
                if completed:
                    msg += "\n🎯 每日任务「丹药养生」已完成！"
            
            yield event.plain_result(msg)

        elif target_item_info.type == "功法":
            # 学习功法 - 永久属性加成
            if quantity > 1:
                yield event.plain_result(f"每次只能学习一本功法。")
                return
            
            p_clone = player.clone()
            learned = p_clone.get_learned_skills_list()
            
            # 检查是否已学
            if target_item_id in learned:
                yield event.plain_result(f"你已经修炼过「{item_name}」了，无法重复修炼。")
                return
            
            # 学习功法
            learned.append(target_item_id)
            p_clone.set_learned_skills_list(learned)
            
            # 消耗物品
            await self.db.remove_item_from_inventory(player.user_id, target_item_id, 1)
            await self.db.update_player(p_clone)
            
            # 构建效果提示
            effect_lines = []
            if hasattr(target_item_info, 'skill_effects') and target_item_info.skill_effects:
                for stat, value in target_item_info.skill_effects.items():
                    stat_names = {"attack": "攻击", "defense": "防御", "max_hp": "生命上限"}
                    stat_name = stat_names.get(stat, stat)
                    effect_lines.append(f"{stat_name}+{value}")
            
            effect_msg = "，".join(effect_lines) if effect_lines else "属性提升"
            msg = f"恭喜！你成功修炼了「{item_name}」！\n永久获得：{effect_msg}"
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "use_item")
                if completed:
                    msg += "\n🎯 每日任务「丹药养生」已完成！"
            
            yield event.plain_result(msg)

        elif target_item_info.buff_effect:
            # 丹药buff - 临时属性加成
            p_clone = player.clone()
            buff = target_item_info.buff_effect
            buff_type = buff.get("type", "attack_buff")
            buff_value = buff.get("value", 0) * quantity
            buff_duration = buff.get("duration", 3)
            
            # 添加buff
            p_clone.add_buff(buff_type, buff_value, buff_duration)
            
            # 消耗物品
            await self.db.remove_item_from_inventory(player.user_id, target_item_id, quantity)
            await self.db.update_player(p_clone)
            
            buff_names = {"attack_buff": "攻击", "defense_buff": "防御", "hp_buff": "生命上限"}
            buff_name = buff_names.get(buff_type, "未知")
            msg = (
                f"你使用了 {quantity} 个「{item_name}」！\n"
                f"获得buff：{buff_name}+{buff_value}，持续{buff_duration}场战斗"
            )
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "use_item")
                if completed:
                    msg += "\n🎯 每日任务「丹药养生」已完成！"
            
            yield event.plain_result(msg)

        elif target_item_info.effect:
            effect_type = target_item_info.effect.get("type")
            
            # 特殊效果：重置灵根
            if effect_type == "reroll_spirit_root":
                if quantity > 1:
                    yield event.plain_result("逆天改命丹每次只能使用一颗。")
                    return
                
                # 消耗物品
                await self.db.remove_item_from_inventory(player.user_id, target_item_id, 1)
                
                # 重置灵根
                import random
                root_types = ["金", "木", "水", "火", "土", "异", "天", "融合", "混沌"]
                old_root = player.spiritual_root
                new_root_name = random.choice(root_types)
                
                p_clone = player.clone()
                p_clone.spiritual_root = f"{new_root_name}灵根"
                await self.db.update_player(p_clone)
                
                msg = (
                    f"你服下了「{item_name}」，体内灵气翻涌！\n"
                    f"原有的「{old_root}」已化为全新的「{p_clone.spiritual_root}」！\n"
                    f"祝道友仙途坦荡，大道可期！"
                )
                
                # 完成每日任务
                if self.daily_task_handler:
                    completed = await self.daily_task_handler.complete_task(player.user_id, "use_item")
                    if completed:
                        msg += "\n🎯 每日任务「丹药养生」已完成！"
                
                yield event.plain_result(msg)
                return
            
            # 消耗品 - 直接效果
            effect, msg = calculate_item_effect(target_item_info, quantity)
            if not effect:
                yield event.plain_result(msg)
                return

            success = await self.db.transactional_apply_item_effect(player.user_id, target_item_id, quantity, effect)

            if success:
                # 完成每日任务
                if self.daily_task_handler:
                    completed = await self.daily_task_handler.complete_task(player.user_id, "use_item")
                    if completed:
                        msg += "\n🎯 每日任务「丹药养生」已完成！"
                yield event.plain_result(msg)
            else:
                yield event.plain_result(f"使用失败！可能发生了未知错误。")
        
        else:
            yield event.plain_result(f"「{item_name}」似乎无法使用。")

    @player_required
    async def handle_sell(self, player: Player, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        """出售物品给商店"""
        if not item_name or quantity <= 0:
            yield event.plain_result(f"指令格式错误。正确用法: `{CMD_SELL} <物品名> [数量]`。")
            return
        
        today = date.today().isoformat()
        current_sell_count = await self.db.get_daily_sell_count(player.user_id, today)
        if current_sell_count >= MAX_DAILY_SELL:
            yield event.plain_result(
                f"今日回购次数已用完（{MAX_DAILY_SELL}/{MAX_DAILY_SELL}）。\n"
                f"明日0点刷新。"
            )
            return
        
        item_to_sell = self.config_manager.get_item_by_name(item_name)
        if not item_to_sell:
            yield event.plain_result(f"未找到名为「{item_name}」的物品。")
            return
        
        item_id, item_info = item_to_sell
        
        if item_info.price <= 0:
            yield event.plain_result(f"「{item_name}」无法出售。")
            return
        
        inventory_item = await self.db.get_item_from_inventory(player.user_id, item_id)
        if not inventory_item or inventory_item['quantity'] < quantity:
            current_qty = inventory_item['quantity'] if inventory_item else 0
            yield event.plain_result(f"出售失败！你只有 {current_qty} 个「{item_name}」。")
            return
        
        sell_price = int(item_info.price * SELL_RATIO * quantity)
        
        success, reason = await self.db.transactional_sell_item(player.user_id, item_id, quantity, sell_price)
        
        if success:
            await self.db.increment_sell_count(player.user_id, today)
            remaining = MAX_DAILY_SELL - current_sell_count - 1
            
            updated_player = await self.db.get_player_by_id(player.user_id)
            new_gold = updated_player.gold if updated_player else player.gold + sell_price
            
            yield event.plain_result(
                f"出售成功！\n"
                f"卖出「{item_name}」x{quantity}，获得 {sell_price} 灵石。\n"
                f"当前灵石：{new_gold}\n"
                f"今日剩余回购次数：{remaining}/{MAX_DAILY_SELL}"
            )
        else:
            if reason == "ERROR_INSUFFICIENT_ITEMS":
                yield event.plain_result(f"出售失败！物品数量不足。")
            else:
                yield event.plain_result("出售失败，请稍后再试。")