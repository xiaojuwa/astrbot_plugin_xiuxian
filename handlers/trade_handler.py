# handlers/trade_handler.py
"""玩家交易系统处理器"""

import time
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.core.message.components import At
from ..data import DataBase
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

__all__ = ["TradeHandler"]


class TradeHandler:
    """交易系统处理器 - 支持灵石转账和物品赠送"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.daily_task_handler = None  # 延迟注入
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler
    
    def _get_mentioned_user(self, event: AstrMessageEvent):
        """从消息中获取被@的用户ID"""
        message_obj = event.message_obj
        if hasattr(message_obj, "message"):
            for comp in message_obj.message:
                if isinstance(comp, At):
                    return str(comp.qq)
        return None

    @player_required
    async def handle_transfer(self, player: Player, event: AstrMessageEvent):
        """转账灵石给其他玩家"""
        # 从消息中解析金额（格式：转账 @人 数量）
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        amount = 0
        for part in parts:
            try:
                amount = int(part)
                break
            except ValueError:
                continue
        
        if amount <= 0:
            yield event.plain_result("请输入正确的转账金额，例如：`转账 @张三 100`")
            return
        
        target_user_id = self._get_mentioned_user(event)
        if not target_user_id:
            yield event.plain_result("请@你想转账的对象，例如：`转账 @张三 100`")
            return
        
        if target_user_id == player.user_id:
            yield event.plain_result("不能给自己转账哦。")
            return
        
        target_player = await self.db.get_player_by_id(target_user_id)
        if not target_player:
            yield event.plain_result("对方尚未踏入修仙之路，无法接收转账。")
            return
        
        # 计算税率（可配置，默认5%）
        tax_rate = self.config.get("VALUES", {}).get("TRADE_TAX_RATE", 0.05)
        tax = int(amount * tax_rate)
        actual_amount = amount - tax
        
        if player.gold < amount:
            yield event.plain_result(f"灵石不足！你只有 {player.gold} 灵石，无法转账 {amount} 灵石。")
            return
        
        # 执行转账
        p_clone = player.clone()
        t_clone = target_player.clone()
        
        p_clone.gold -= amount
        t_clone.gold += actual_amount
        
        await self.db.update_player(p_clone)
        await self.db.update_player(t_clone)
        
        # 记录交易日志
        await self.db.record_trade(player.user_id, target_user_id, "transfer", None, None, amount)
        
        tax_info = f"（扣除{int(tax_rate*100)}%交易税{tax}灵石）" if tax > 0 else ""
        msg = (
            f"转账成功！\n"
            f"你向对方转账了 {amount} 灵石{tax_info}\n"
            f"对方实际收到 {actual_amount} 灵石\n"
            f"你的余额：{p_clone.gold} 灵石"
        )
        
        # 完成每日任务
        if self.daily_task_handler:
            completed = await self.daily_task_handler.complete_task(player.user_id, "transfer")
            if completed:
                msg += "\n🎯 每日任务「乐善好施」已完成！"
        
        yield event.plain_result(msg)

    @player_required
    async def handle_gift(self, player: Player, event: AstrMessageEvent):
        """赠送物品给其他玩家"""
        # 从消息中解析物品名和数量（格式：赠送 @人 物品名 [数量]）
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        # 第一个是命令"赠送"，后面是物品名和可选数量
        item_name = None
        quantity = 1
        
        for i, part in enumerate(parts):
            if part in ["赠送", "送"]:
                continue
            try:
                # 尝试解析为数字（数量）
                quantity = int(part)
            except ValueError:
                # 不是数字，作为物品名
                if item_name is None:
                    item_name = part
        
        if not item_name:
            yield event.plain_result("请输入要赠送的物品名，例如：`赠送 @张三 引气丹 1`")
            return
        
        if quantity <= 0:
            yield event.plain_result("赠送数量必须大于0。")
            return
        
        target_user_id = self._get_mentioned_user(event)
        if not target_user_id:
            yield event.plain_result("请@你想赠送的对象，例如：`赠送 @张三 引气丹 1`")
            return
        
        if target_user_id == player.user_id:
            yield event.plain_result("不能赠送给自己哦。")
            return
        
        target_player = await self.db.get_player_by_id(target_user_id)
        if not target_player:
            yield event.plain_result("对方尚未踏入修仙之路，无法接收赠送。")
            return
        
        # 检查物品是否存在
        item_info = self.config_manager.get_item_by_name(item_name)
        if not item_info:
            yield event.plain_result(f"未找到名为「{item_name}」的物品。")
            return
        
        item_id, item_data = item_info
        
        # 检查背包中是否有足够的物品
        inventory_item = await self.db.get_item_from_inventory(player.user_id, item_id)
        if not inventory_item or inventory_item['quantity'] < quantity:
            current_qty = inventory_item['quantity'] if inventory_item else 0
            yield event.plain_result(f"你的「{item_name}」数量不足，当前拥有 {current_qty} 个。")
            return
        
        # 执行赠送
        await self.db.remove_item_from_inventory(player.user_id, item_id, quantity)
        await self.db.add_items_to_inventory_in_transaction(target_user_id, {item_id: quantity})
        
        # 记录交易日志
        await self.db.record_trade(player.user_id, target_user_id, "gift", item_id, quantity, 0)
        
        msg = f"赠送成功！\n你向对方赠送了「{item_name}」x{quantity}"
        
        # 完成每日任务
        if self.daily_task_handler:
            completed = await self.daily_task_handler.complete_task(player.user_id, "transfer")
            if completed:
                msg += "\n🎯 每日任务「乐善好施」已完成！"
        
        yield event.plain_result(msg)
