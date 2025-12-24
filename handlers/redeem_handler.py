# handlers/redeem_handler.py
"""激活码兑换处理器 - 橘的恩赐"""

from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig, logger
from ..data import DataBase
from ..models import Player
from ..config_manager import ConfigManager
from .utils import player_required

__all__ = ["RedeemHandler"]

class RedeemHandler:
    """激活码兑换处理器"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    def _get_redeem_codes(self) -> list:
        """获取配置的激活码列表"""
        return self.config.get("REDEEM_CODES", [])

    def _find_redeem_code(self, code: str) -> dict:
        """查找激活码配置"""
        redeem_codes = self._get_redeem_codes()
        for redeem_config in redeem_codes:
            if redeem_config.get("code") == code:
                return redeem_config
        return None

    @player_required
    async def handle_redeem(self, player: Player, event: AstrMessageEvent, code: str):
        """处理激活码兑换"""
        user_id = event.get_sender_id()
        
        # 查找激活码配置
        redeem_config = self._find_redeem_code(code)
        if not redeem_config:
            yield event.plain_result("此激活码不存在或已失效。")
            return
        
        # 检查玩家是否已使用过此激活码
        has_used = await self.db.has_used_redeem_code(user_id, code)
        if has_used:
            yield event.plain_result("道友已领取过此恩赐，不可重复领取。")
            return
        
        # 检查激活码使用次数是否已达上限
        max_uses = redeem_config.get("max_uses", 0)
        if max_uses > 0:
            current_uses = await self.db.get_redeem_code_use_count(code)
            if current_uses >= max_uses:
                yield event.plain_result("此激活码已被领取完毕。")
                return
        
        # 开始发放奖励
        rewards_msg = []
        
        # 发放灵石
        gold_reward = redeem_config.get("gold", 0)
        if gold_reward > 0:
            player.gold += gold_reward
            rewards_msg.append(f"💰 灵石 x{gold_reward}")
        
        # 发放修为
        exp_reward = redeem_config.get("exp", 0)
        if exp_reward > 0:
            player.experience += exp_reward
            rewards_msg.append(f"✨ 修为 x{exp_reward}")
        
        # 发放物品
        items_reward = redeem_config.get("items", [])
        items_to_add = {}
        for item_config in items_reward:
            item_name = item_config.get("name", "")
            quantity = item_config.get("quantity", 1)
            
            if not item_name or quantity <= 0:
                continue
            
            # 查找物品ID
            item_id = None
            for iid, idata in self.config_manager.item_data.items():
                if idata.name == item_name:
                    item_id = iid
                    break
            
            if item_id:
                items_to_add[item_id] = quantity
                rewards_msg.append(f"📦 {item_name} x{quantity}")
            else:
                logger.warning(f"[激活码] 物品「{item_name}」不存在，跳过发放")
        
        # 更新玩家数据
        await self.db.update_player(player)
        
        # 添加物品到背包
        if items_to_add:
            await self.db.add_items_to_inventory_in_transaction(user_id, items_to_add)
        
        # 记录激活码使用
        await self.db.record_redeem_code_use(user_id, code)
        
        # 构建回复消息
        description = redeem_config.get("description", "")
        desc_line = f"「{description}」\n" if description else ""
        
        if rewards_msg:
            rewards_str = "\n".join(rewards_msg)
            reply = (
                f"🎁 橘的恩赐 🎁\n"
                f"{desc_line}"
                f"道友 {event.get_sender_name()} 成功领取：\n"
                f"{rewards_str}"
            )
        else:
            reply = f"🎁 橘的恩赐 🎁\n{desc_line}激活码已兑换，但未配置任何奖励。"
        
        logger.info(f"[激活码] 玩家 {user_id} 使用激活码「{code}」成功")
        yield event.plain_result(reply)
