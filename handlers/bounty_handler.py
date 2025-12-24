# handlers/bounty_handler.py
"""悬赏任务系统处理器 - 提供悬赏任务功能"""

import random
import time
from datetime import date
from typing import Dict, List, Optional
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["BountyHandler"]

# 悬赏任务模板
BOUNTY_TEMPLATES = {
    "hunt_demon": {
        "name": "猎杀妖兽",
        "description": "附近山林出现妖兽作乱，需要修士前往清剿。",
        "difficulty": "简单",
        "min_level": 0,
        "base_gold": 150,
        "base_exp": 80,
        "success_rate": 0.85,
        "hp_cost_min": 10,
        "hp_cost_max": 30
    },
    "escort_merchant": {
        "name": "护送商队",
        "description": "一支商队需要修士护送穿越危险地带。",
        "difficulty": "简单",
        "min_level": 0,
        "base_gold": 200,
        "base_exp": 50,
        "success_rate": 0.90,
        "hp_cost_min": 5,
        "hp_cost_max": 20
    },
    "collect_herbs": {
        "name": "采集灵药",
        "description": "药师需要一批珍稀灵药，需前往险地采集。",
        "difficulty": "普通",
        "min_level": 3,
        "base_gold": 250,
        "base_exp": 120,
        "success_rate": 0.80,
        "hp_cost_min": 15,
        "hp_cost_max": 40
    },
    "investigate_ruins": {
        "name": "探查遗迹",
        "description": "发现了一处上古遗迹，需要修士前往探查。",
        "difficulty": "普通",
        "min_level": 5,
        "base_gold": 350,
        "base_exp": 180,
        "success_rate": 0.75,
        "hp_cost_min": 25,
        "hp_cost_max": 60
    },
    "slay_evil_cultivator": {
        "name": "诛杀邪修",
        "description": "有邪修在附近为祸一方，需要正道修士前往诛杀。",
        "difficulty": "困难",
        "min_level": 8,
        "base_gold": 500,
        "base_exp": 300,
        "success_rate": 0.65,
        "hp_cost_min": 40,
        "hp_cost_max": 100
    },
    "seal_demon": {
        "name": "封印魔物",
        "description": "一只上古魔物即将破封而出，需要修士前往加固封印。",
        "difficulty": "困难",
        "min_level": 12,
        "base_gold": 800,
        "base_exp": 500,
        "success_rate": 0.55,
        "hp_cost_min": 60,
        "hp_cost_max": 150
    },
    "retrieve_artifact": {
        "name": "夺回神器",
        "description": "宗门神器被盗，需要修士追踪并夺回。",
        "difficulty": "极难",
        "min_level": 15,
        "base_gold": 1200,
        "base_exp": 800,
        "success_rate": 0.45,
        "hp_cost_min": 80,
        "hp_cost_max": 200
    }
}


class BountyHandler:
    """悬赏任务相关指令处理器"""

    # 每日悬赏任务次数上限
    MAX_DAILY_BOUNTIES = 5

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.daily_task_handler = None  # 延迟注入
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler

    @player_required
    async def handle_bounty_list(self, player: Player, event: AstrMessageEvent):
        """查看可接取的悬赏任务"""
        today = date.today().isoformat()
        current_count = await self.db.get_daily_bounty_count(player.user_id, today)
        remaining = max(0, self.MAX_DAILY_BOUNTIES - current_count)

        lines = [
            "━━ 悬赏榜 ━━",
            f"📅 今日剩余次数: {remaining}/{self.MAX_DAILY_BOUNTIES}",
            ""
        ]

        # 根据玩家等级筛选可接任务
        available_bounties = []
        for bounty_id, bounty in BOUNTY_TEMPLATES.items():
            if player.level_index >= bounty["min_level"]:
                available_bounties.append((bounty_id, bounty))

        if not available_bounties:
            lines.append("暂无可接取的悬赏任务。")
        else:
            for bounty_id, bounty in available_bounties:
                difficulty_icon = self._get_difficulty_icon(bounty["difficulty"])
                level_name = self.config_manager.level_data[bounty["min_level"]]["level_name"] if bounty["min_level"] > 0 else "无"

                lines.extend([
                    f"{difficulty_icon} 【{bounty['name']}】",
                    f"   {bounty['description']}",
                    f"   难度: {bounty['difficulty']} | 最低境界: {level_name}",
                    f"   奖励: 💰{bounty['base_gold']} 📈{bounty['base_exp']}",
                    f"   指令: 接取悬赏 {bounty['name']}",
                    ""
                ])

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_accept_bounty(self, player: Player, event: AstrMessageEvent, bounty_name: str):
        """接取并执行悬赏任务"""
        today = date.today().isoformat()

        # 检查每日次数
        current_count = await self.db.get_daily_bounty_count(player.user_id, today)
        if current_count >= self.MAX_DAILY_BOUNTIES:
            yield event.plain_result(
                f"道友今日的悬赏次数已用尽，明日再来吧。\n"
                f"（每日悬赏次数上限：{self.MAX_DAILY_BOUNTIES}次）"
            )
            return

        # 检查玩家状态
        if player.state != "空闲":
            yield event.plain_result(f"道友当前正在「{player.state}」中，无法接取悬赏。")
            return

        # 查找悬赏任务
        bounty = None
        bounty_id = None
        for bid, b in BOUNTY_TEMPLATES.items():
            if b["name"] == bounty_name:
                bounty = b
                bounty_id = bid
                break

        if not bounty:
            yield event.plain_result(f"未找到名为「{bounty_name}」的悬赏任务。\n请使用「悬赏榜」查看可接取的任务。")
            return

        # 检查等级要求
        if player.level_index < bounty["min_level"]:
            min_level_name = self.config_manager.level_data[bounty["min_level"]]["level_name"]
            yield event.plain_result(f"道友境界不足，需要达到「{min_level_name}」才能接取此悬赏。")
            return

        # 执行悬赏任务
        result = await self._execute_bounty(player, bounty, bounty_id, today)
        yield event.plain_result(result)

    async def _execute_bounty(self, player: Player, bounty: Dict, bounty_id: str, today: str) -> str:
        """执行悬赏任务"""
        lines = [
            f"━━ {bounty['name']} ━━",
            "",
            bounty["description"],
            "",
            "--- 任务进行中 ---",
        ]

        p_clone = player.clone()
        combat_stats = p_clone.get_combat_stats(self.config_manager)

        # 计算成功率（根据玩家属性有加成）
        base_success_rate = bounty["success_rate"]
        # 攻击力加成：每100点攻击增加5%成功率
        attack_bonus = min(0.15, combat_stats["attack"] / 100 * 0.05)
        # 防御力加成：每50点防御增加3%成功率
        defense_bonus = min(0.10, combat_stats["defense"] / 50 * 0.03)
        final_success_rate = min(0.95, base_success_rate + attack_bonus + defense_bonus)

        # 判定成功与否
        success = random.random() < final_success_rate

        # 计算HP消耗
        hp_cost = random.randint(bounty["hp_cost_min"], bounty["hp_cost_max"])
        # 防御可以减少HP消耗
        hp_cost = max(1, hp_cost - combat_stats["defense"] // 10)

        if success:
            # 成功 - 计算奖励（根据境界有加成）
            level_bonus = 1 + player.level_index * 0.03
            gold_reward = int(bounty["base_gold"] * level_bonus)
            exp_reward = int(bounty["base_exp"] * level_bonus)

            p_clone.gold += gold_reward
            p_clone.experience += exp_reward
            p_clone.hp = max(1, p_clone.hp - hp_cost)

            lines.extend([
                self._get_success_description(bounty_id),
                "",
                "🎉 【任务成功】 🎉",
                "",
                f"消耗生命: -{hp_cost}",
                f"获得灵石: +{gold_reward}",
                f"获得修为: +{exp_reward}",
            ])
        else:
            # 失败 - 只消耗HP，无奖励
            hp_cost = int(hp_cost * 1.5)  # 失败时HP消耗更多
            p_clone.hp = max(1, p_clone.hp - hp_cost)

            lines.extend([
                self._get_failure_description(bounty_id),
                "",
                "💔 【任务失败】 💔",
                "",
                f"消耗生命: -{hp_cost}",
                "未能获得任何奖励...",
            ])

        # 更新数据
        await self.db.update_player(p_clone)
        await self.db.increment_bounty_count(player.user_id, today)

        # 完成每日任务（只有成功才算完成）
        if success and self.daily_task_handler:
            task_completed = await self.daily_task_handler.complete_task(player.user_id, "bounty")
            if task_completed:
                lines.append("\n🎯 每日任务「悬赏猎人」已完成！")

        # 显示剩余次数
        remaining = self.MAX_DAILY_BOUNTIES - await self.db.get_daily_bounty_count(player.user_id, today)
        lines.extend([
            "",
            f"当前生命: {p_clone.hp}/{combat_stats['max_hp']}",
            f"今日剩余悬赏次数: {remaining}/{self.MAX_DAILY_BOUNTIES}",
            "━━━━━━━━━━━━"
        ])

        return "\n".join(lines)

    def _get_difficulty_icon(self, difficulty: str) -> str:
        """获取难度图标"""
        icons = {
            "简单": "🟢",
            "普通": "🟡",
            "困难": "🟠",
            "极难": "🔴"
        }
        return icons.get(difficulty, "⚪")

    def _get_success_description(self, bounty_id: str) -> str:
        """获取成功描述"""
        descriptions = {
            "hunt_demon": "道友身手矫健，三两下便将妖兽斩杀！",
            "escort_merchant": "一路平安无事，商队顺利抵达目的地。",
            "collect_herbs": "道友在险地中找到了所需的灵药，满载而归。",
            "investigate_ruins": "遗迹中虽有危险，但道友成功探明了情况。",
            "slay_evil_cultivator": "经过一番激战，邪修已被道友诛杀！",
            "seal_demon": "道友成功加固了封印，魔物暂时无法脱困。",
            "retrieve_artifact": "历经艰险，道友终于夺回了宗门神器！"
        }
        return descriptions.get(bounty_id, "任务顺利完成！")

    def _get_failure_description(self, bounty_id: str) -> str:
        """获取失败描述"""
        descriptions = {
            "hunt_demon": "妖兽狡猾异常，道友不敌只能撤退...",
            "escort_merchant": "途中遭遇强敌，商队损失惨重...",
            "collect_herbs": "灵药生长之地危机四伏，道友无功而返...",
            "investigate_ruins": "遗迹中机关重重，道友被迫退出...",
            "slay_evil_cultivator": "邪修修为深厚，道友不是对手...",
            "seal_demon": "魔物力量太强，封印加固失败...",
            "retrieve_artifact": "神器守卫森严，道友未能得手..."
        }
        return descriptions.get(bounty_id, "任务失败了...")

    @player_required
    async def handle_bounty_status(self, player: Player, event: AstrMessageEvent):
        """查看今日悬赏状态"""
        today = date.today().isoformat()
        current_count = await self.db.get_daily_bounty_count(player.user_id, today)
        remaining = max(0, self.MAX_DAILY_BOUNTIES - current_count)

        lines = [
            "━━ 悬赏状态 ━━",
            f"📅 日期: {today}",
            f"📋 今日已完成: {current_count} 次",
            f"✨ 剩余次数: {remaining} 次",
            "",
            "💡 使用「悬赏榜」查看可接取的任务",
            "━━━━━━━━━━━━"
        ]

        yield event.plain_result("\n".join(lines))
