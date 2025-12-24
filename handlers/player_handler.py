# handlers/player_handler.py
from datetime import date, timedelta
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..core import CultivationManager
from ..models import Player
from ..config_manager import ConfigManager
from .utils import player_required

CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_CHECK_IN = "签到"

__all__ = ["PlayerHandler"]

class PlayerHandler:
    # 玩家相关指令处理器
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.cultivation_manager = CultivationManager(config, config_manager)
        self.daily_task_handler = None  # 延迟注入
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler

    async def handle_start_xiuxian(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        if await self.db.get_player_by_id(user_id):
            yield event.plain_result("道友，你已踏入仙途，无需重复此举。")
            return

        new_player = self.cultivation_manager.generate_new_player_stats(user_id)
        # 保存初始昵称
        new_player.nickname = event.get_sender_name() or ""
        await self.db.create_player(new_player)
        reply_msg = (
            f"恭喜道友 {event.get_sender_name()} 踏上仙途！\n"
            f"初始灵根：【{new_player.spiritual_root}】\n"
            f"启动资金：【{new_player.gold}】灵石\n"
            f"发送「{CMD_PLAYER_INFO}」查看状态，「{CMD_CHECK_IN}」领取福利！"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_player_info(self, player: Player, event: AstrMessageEvent):
        sect_info = f"宗门：{player.sect_name if player.sect_name else '逍遥散人'}"
        combat_stats = player.get_combat_stats(self.config_manager)

        # 构建装备显示部分
        equipped_items_lines = []
        slot_map = {"武器": player.equipped_weapon, "防具": player.equipped_armor, "饰品": player.equipped_accessory}
        for slot, item_id in slot_map.items():
            item_name = "(无)"
            if item_id:
                item_data = self.config_manager.item_data.get(str(item_id))
                if item_data:
                    item_name = f"「{item_data.name}」"
            equipped_items_lines.append(f"  {slot}: {item_name}")

        equipped_info = "\n".join(equipped_items_lines)

        reply_msg = (
            f"--- 道友 {event.get_sender_name()} 的信息 ---\n"
            f"境界：{player.get_level(self.config_manager)}\n"
            f"灵根：{player.spiritual_root}\n"
            f"修为：{player.experience}\n"
            f"灵石：{player.gold}\n"
            f"{sect_info}\n"
            f"状态：{player.state}\n"
            "--- 战斗属性 (含装备加成) ---\n"
            f"❤️生命: {combat_stats['hp']}/{combat_stats['max_hp']}\n"
            f"⚔️攻击: {combat_stats['attack']}\n"
            f"🛡️防御: {combat_stats['defense']}\n"
            "--- 穿戴装备 ---\n"
            f"{equipped_info}\n"
            f"--------------------------"
        )
        yield event.plain_result(reply_msg)

    @player_required
    async def handle_check_in(self, player: Player, event: AstrMessageEvent):
        success, msg, updated_player = self.cultivation_manager.handle_check_in(player)
        if success and updated_player:
            # 更新昵称
            sender_name = event.get_sender_name()
            if sender_name and sender_name != updated_player.nickname:
                updated_player.nickname = sender_name
            
            await self.db.update_player(updated_player)
            
            # 更新连续签到记录
            today = date.today().isoformat()
            last_check_in = await self.db.get_last_check_in_date(player.user_id)
            
            if last_check_in:
                last_date = date.fromisoformat(last_check_in)
                today_date = date.today()
                if (today_date - last_date).days == 1:
                    # 连续签到
                    current_streak = await self.db.get_check_in_streak(player.user_id)
                    new_streak = current_streak + 1
                else:
                    # 断签，重新开始
                    new_streak = 1
            else:
                new_streak = 1
            
            await self.db.update_check_in_streak(player.user_id, new_streak, today)
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "check_in")
                if completed:
                    msg += "\n🎯 每日任务「晨钟暮鼓」已完成！"
        
        yield event.plain_result(msg)

    @player_required
    async def handle_start_cultivation(self, player: Player, event: AstrMessageEvent):
        success, msg, updated_player = self.cultivation_manager.handle_start_cultivation(player)
        if success and updated_player:
            await self.db.update_player(updated_player)
        yield event.plain_result(msg)

    @player_required
    async def handle_end_cultivation(self, player: Player, event: AstrMessageEvent):
        success, msg, updated_player = self.cultivation_manager.handle_end_cultivation(player)
        if success and updated_player:
            await self.db.update_player(updated_player)
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "cultivation")
                if completed:
                    msg += "\n🎯 每日任务「闭关修炼」已完成！"
        
        yield event.plain_result(msg)

    @player_required
    async def handle_breakthrough(self, player: Player, event: AstrMessageEvent):
        # 内部已经包含了状态检查，但为了统一，装饰器的检查是第一道防线
        success, msg, updated_player = self.cultivation_manager.handle_breakthrough(player)
        if success and updated_player:
            await self.db.update_player(updated_player)
        yield event.plain_result(msg)
        
    @player_required
    async def handle_reroll_spirit_root(self, player: Player, event: AstrMessageEvent):
        success, msg, updated_player = self.cultivation_manager.handle_reroll_spirit_root(player)
        if success and updated_player:
            await self.db.update_player(updated_player)
        yield event.plain_result(msg)

    @player_required
    async def handle_my_buff(self, player: Player, event: AstrMessageEvent):
        """查看当前激活的buff"""
        buffs = player.get_active_buffs_list()
        
        if not buffs:
            yield event.plain_result("你当前没有任何buff加成。\n提示：使用「筑基丹」「大力丸」等丹药可获得临时buff！")
            return
        
        buff_names = {"attack_buff": "攻击加成", "defense_buff": "防御加成", "hp_buff": "生命加成"}
        
        lines = ["--- 当前激活的buff ---"]
        for buff in buffs:
            buff_type = buff.get("type", "")
            buff_value = buff.get("value", 0)
            duration = buff.get("duration", 0)
            buff_name = buff_names.get(buff_type, buff_type)
            lines.append(f"  💫 {buff_name}：+{buff_value}（剩余{duration}场战斗）")
        
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_my_skills(self, player: Player, event: AstrMessageEvent):
        """查看已学习的功法"""
        learned = player.get_learned_skills_list()
        
        if not learned:
            yield event.plain_result("你尚未修炼任何功法。\n提示：购买功法后使用「使用 <功法名>」即可修炼，获得永久属性加成！")
            return
        
        lines = ["--- 已修炼的功法 ---"]
        for skill_id in learned:
            skill_item = self.config_manager.item_data.get(str(skill_id))
            if skill_item:
                effect_parts = []
                if hasattr(skill_item, 'skill_effects') and skill_item.skill_effects:
                    stat_names = {"attack": "攻击", "defense": "防御", "max_hp": "生命"}
                    for stat, value in skill_item.skill_effects.items():
                        stat_name = stat_names.get(stat, stat)
                        effect_parts.append(f"{stat_name}+{value}")
                effect_str = "，".join(effect_parts) if effect_parts else "未知效果"
                lines.append(f"  📖 【{skill_item.name}】（{skill_item.rank}）：{effect_str}")
            else:
                lines.append(f"  📖 功法ID: {skill_id} (数据丢失)")
        
        yield event.plain_result("\n".join(lines))