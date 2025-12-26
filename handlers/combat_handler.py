# handlers/combat_handler.py
import time
import datetime
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.core.message.components import At
from ..data import DataBase
from ..core import BattleManager
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

CMD_SPAR = "切磋"
CMD_FIGHT_BOSS = "讨伐boss"
CMD_DUEL = "奇斗"
CMD_BOSS_LOGS = "boss战报"

# PVP冷却时间（秒）
PVP_COOLDOWN_SECONDS = 300  # 5分钟

__all__ = ["CombatHandler"]

class CombatHandler:
    """战斗相关指令处理器 - 支持切磋、奇斗（灵石赌注）"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.battle_manager = BattleManager(db, config, config_manager)
        self.daily_task_handler = None  # 延迟注入
        self._context = None  # AstrBot context for broadcasting
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler

    def set_context(self, context):
        """注入AstrBot context以支持主动消息推送"""
        self._context = context
        broadcast_group = self.config.get("VALUES", {}).get("WORLD_BOSS_BROADCAST_GROUP", "")
        if broadcast_group and context:
            async def broadcast_callback(message: str):
                await self._broadcast_boss_kill(message)
            self.battle_manager.set_broadcast_callback(broadcast_callback)

    async def _broadcast_boss_kill(self, message: str):
        """向配置的群发送Boss击杀广播"""
        if not self._context:
            return
        broadcast_group = self.config.get("VALUES", {}).get("WORLD_BOSS_BROADCAST_GROUP", "")
        if not broadcast_group:
            return
        try:
            from astrbot.api.event import MessageChain
            unified_msg_origin = f"aiocqhttp:group:{broadcast_group}"
            chain = MessageChain().message(message)
            await self._context.send_message(unified_msg_origin, chain)
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"Boss击杀广播发送失败: {e}")

    def _get_mentioned_user(self, event: AstrMessageEvent):
        """从消息中获取被@的用户ID和名字"""
        message_obj = event.message_obj
        if hasattr(message_obj, "message"):
            for comp in message_obj.message:
                if isinstance(comp, At):
                    name = comp.name if hasattr(comp, 'name') else None
                    return str(comp.qq), name
        return None, None

    @player_required
    async def handle_spar(self, attacker: Player, event: AstrMessageEvent):
        """普通切磋 - 无赌注，仅记录胜负"""
        # 检查冷却
        now = time.time()
        cooldown = self.config.get("VALUES", {}).get("PVP_COOLDOWN_SECONDS", PVP_COOLDOWN_SECONDS)
        time_since_last = now - attacker.last_pvp_time
        if time_since_last < cooldown:
            remaining = int(cooldown - time_since_last)
            yield event.plain_result(f"切磋需要休息！冷却中，还需等待 {remaining} 秒。")
            return
        
        if attacker.hp < attacker.max_hp:
            yield event.plain_result("你当前气血不满，无法与人切磋，请先恢复。")
            return

        mentioned_user_id, defender_name = self._get_mentioned_user(event)

        if not mentioned_user_id:
            yield event.plain_result(f"请指定切磋对象，例如：`{CMD_SPAR} @张三`")
            return

        if mentioned_user_id == attacker.user_id:
            yield event.plain_result("道友，不可与自己为敌。")
            return

        defender = await self.db.get_player_by_id(mentioned_user_id)
        if not defender:
            yield event.plain_result("对方尚未踏入仙途，无法应战。")
            return

        if defender.hp < defender.max_hp:
            yield event.plain_result("对方气血不满，此时挑战非君子所为。")
            return

        attacker_name = event.get_sender_name()

        # 执行战斗
        winner, loser, report_lines = self.battle_manager.player_vs_player(
            attacker, defender, attacker_name, defender_name
        )
        
        # 更新PVP统计和冷却
        a_clone = attacker.clone()
        d_clone = defender.clone()
        a_clone.last_pvp_time = now
        d_clone.last_pvp_time = now
        
        if winner and winner.user_id == attacker.user_id:
            a_clone.pvp_wins += 1
            d_clone.pvp_losses += 1
            # 胜者获得少量修为奖励
            exp_reward = 50 + attacker.level_index * 10
            a_clone.experience += exp_reward
            report_lines.append(f"\n🎉 胜者获得 {exp_reward} 修为奖励！")
        elif winner:
            d_clone.pvp_wins += 1
            a_clone.pvp_losses += 1
            exp_reward = 50 + defender.level_index * 10
            d_clone.experience += exp_reward
            report_lines.append(f"\n🎉 胜者获得 {exp_reward} 修为奖励！")
        
        # 消耗buff
        a_clone.consume_buff_duration()
        d_clone.consume_buff_duration()
        
        await self.db.update_player(a_clone)
        await self.db.update_player(d_clone)
        
        # 完成每日任务（双方都完成）
        if self.daily_task_handler:
            completed_a = await self.daily_task_handler.complete_task(attacker.user_id, "spar")
            completed_d = await self.daily_task_handler.complete_task(defender.user_id, "spar")
            if completed_a:
                report_lines.append(f"\n🎯 {attacker_name} 完成每日任务「以武会友」！")
            if completed_d:
                report_lines.append(f"\n🎯 {defender_name or '对方'} 完成每日任务「以武会友」！")
        
        yield event.plain_result("\n".join(report_lines))

    @player_required
    async def handle_duel(self, attacker: Player, event: AstrMessageEvent):
        """奇斗 - 带灵石赌注的PVP"""
        # 从消息中解析赌注金额（格式：奇斗 @人 金额）
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        bet_amount = 100  # 默认赌注
        for part in parts:
            try:
                bet_amount = int(part)
                break
            except ValueError:
                continue
        
        if bet_amount < 10:
            yield event.plain_result("赌注最低10灵石！")
            return
        
        # 检查冷却
        now = time.time()
        cooldown = self.config.get("VALUES", {}).get("PVP_COOLDOWN_SECONDS", PVP_COOLDOWN_SECONDS)
        time_since_last = now - attacker.last_pvp_time
        if time_since_last < cooldown:
            remaining = int(cooldown - time_since_last)
            yield event.plain_result(f"需要休息！冷却中，还需等待 {remaining} 秒。")
            return
        
        if attacker.gold < bet_amount:
            yield event.plain_result(f"灵石不足！你只有 {attacker.gold} 灵石，无法押注 {bet_amount}。")
            return

        if attacker.hp < attacker.max_hp:
            yield event.plain_result("你当前气血不满，无法参与奇斗，请先恢复。")
            return

        mentioned_user_id, defender_name = self._get_mentioned_user(event)

        if not mentioned_user_id:
            yield event.plain_result(f"请指定对手，例如：`{CMD_DUEL} @张三 100`")
            return

        if mentioned_user_id == attacker.user_id:
            yield event.plain_result("道友，不可与自己为敌。")
            return

        defender = await self.db.get_player_by_id(mentioned_user_id)
        if not defender:
            yield event.plain_result("对方尚未踏入仙途，无法应战。")
            return

        if defender.hp < defender.max_hp:
            yield event.plain_result("对方气血不满，此时挑战非君子所为。")
            return
        
        if defender.gold < bet_amount:
            yield event.plain_result(f"对方灵石不足 {bet_amount}，无法接受挑战。")
            return

        attacker_name = event.get_sender_name()

        # 执行战斗
        winner, loser, report_lines = self.battle_manager.player_vs_player(
            attacker, defender, attacker_name, defender_name
        )
        
        # 更新PVP统计、灵石和冷却
        a_clone = attacker.clone()
        d_clone = defender.clone()
        a_clone.last_pvp_time = now
        d_clone.last_pvp_time = now
        
        # 灵石赌注结算
        if winner and winner.user_id == attacker.user_id:
            a_clone.pvp_wins += 1
            d_clone.pvp_losses += 1
            a_clone.gold += bet_amount
            d_clone.gold -= bet_amount
            report_lines.append(f"\n💰 {attacker_name} 赢得 {bet_amount} 灵石！")
        elif winner:
            d_clone.pvp_wins += 1
            a_clone.pvp_losses += 1
            d_clone.gold += bet_amount
            a_clone.gold -= bet_amount
            report_lines.append(f"\n💰 {defender_name or '对方'} 赢得 {bet_amount} 灵石！")
        
        # 消耗buff
        a_clone.consume_buff_duration()
        d_clone.consume_buff_duration()
        
        await self.db.update_player(a_clone)
        await self.db.update_player(d_clone)
        
        # 完成每日任务（双方都完成）
        if self.daily_task_handler:
            completed_a = await self.daily_task_handler.complete_task(attacker.user_id, "duel")
            completed_d = await self.daily_task_handler.complete_task(defender.user_id, "duel")
            if completed_a:
                report_lines.append(f"\n🎯 {attacker_name} 完成每日任务「奇斗赌局」！")
            if completed_d:
                report_lines.append(f"\n🎯 {defender_name or '对方'} 完成每日任务「奇斗赌局」！")
        
        yield event.plain_result("\n".join(report_lines))

    async def handle_boss_list(self, event: AstrMessageEvent):
        active_bosses_with_templates = await self.battle_manager.ensure_bosses_are_spawned()

        if not active_bosses_with_templates:
            yield event.plain_result("天地间一片祥和，暂无妖兽作乱。")
            return

        report = ["--- 当前可讨伐的世界Boss ---"]
        for instance, template in active_bosses_with_templates:
            report.append(
                f"【{template.name}】 (ID: {instance.boss_id})\n"
                f"  ❤️剩余生命: {instance.current_hp}/{instance.max_hp}"
            )
            participants = await self.db.get_boss_participants(instance.boss_id)
            if participants:
                report.append("  - 伤害贡献榜 -")
                for p_data in participants[:3]:
                    report.append(f"    - {p_data['user_name']}: {p_data['total_damage']} 伤害")

        report.append(f"\n使用「{CMD_FIGHT_BOSS} <Boss ID>」发起挑战！")
        yield event.plain_result("\n".join(report))

    @player_required
    async def handle_fight_boss(self, player: Player, event: AstrMessageEvent, boss_id: str):
        if not boss_id:
            yield event.plain_result(f"指令格式错误！请使用「{CMD_FIGHT_BOSS} <Boss ID>」。")
            return

        player_name = event.get_sender_name()
        result_msg = await self.battle_manager.player_fight_boss(player, boss_id, player_name)
        
        # 战斗后消耗buff
        p_clone = player.clone()
        p_clone.consume_buff_duration()
        await self.db.update_player(p_clone)
        
        # 完成每日任务
        if self.daily_task_handler:
            completed = await self.daily_task_handler.complete_task(player.user_id, "boss_fight")
            if completed:
                result_msg += "\n🎯 每日任务「斩妖除魔」已完成！"
        
        yield event.plain_result(result_msg)

    async def handle_boss_logs(self, event: AstrMessageEvent):
        logs = await self.db.get_boss_kill_logs(10)
        
        if not logs:
            yield event.plain_result("暂无Boss击杀记录。")
            return
        
        report = ["--- 近期Boss击杀战报 ---"]
        for log in logs:
            defeat_time = datetime.datetime.fromtimestamp(log['defeated_at'])
            time_str = defeat_time.strftime("%m-%d %H:%M")
            contributors = log['top_contributors']
            top_names = [c['user_name'] for c in contributors[:3]]
            mvp_text = "、".join(top_names) if top_names else "无"
            report.append(f"\n📜 【{log['boss_name']}】")
            report.append(f"   击杀时间: {time_str}")
            report.append(f"   功勋榜: {mvp_text}")
        
        yield event.plain_result("\n".join(report))