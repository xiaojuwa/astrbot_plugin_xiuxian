# handlers/daily_task_handler.py
"""每日任务处理器 - 提供每日任务系统功能"""

import random
from datetime import date
from typing import Dict, List, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["DailyTaskHandler"]

# 每日任务定义
DAILY_TASKS = {
    "cultivation": {
        "name": "勤修苦练",
        "description": "完成一次闭关修炼（至少5分钟）",
        "reward_gold": 100,
        "reward_exp": 50
    },
    "check_in": {
        "name": "晨钟暮鼓",
        "description": "完成每日签到",
        "reward_gold": 50,
        "reward_exp": 0
    },
    "realm_explore": {
        "name": "秘境探险",
        "description": "完成一次秘境探索",
        "reward_gold": 150,
        "reward_exp": 100
    },
    "boss_fight": {
        "name": "斩妖除魔",
        "description": "参与一次世界Boss讨伐",
        "reward_gold": 200,
        "reward_exp": 150
    },
    "spar": {
        "name": "以武会友",
        "description": "与其他修士切磋一次",
        "reward_gold": 80,
        "reward_exp": 30
    }
}


class DailyTaskHandler:
    """每日任务相关指令处理器"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    @player_required
    async def handle_daily_tasks(self, player: Player, event: AstrMessageEvent):
        """查看每日任务列表"""
        today = date.today().isoformat()
        task_progress = await self.db.get_daily_task_progress(player.user_id, today)

        lines = ["═══ 【每日任务】 ═══", f"📅 {today}", ""]

        for task_id, task_info in DAILY_TASKS.items():
            completed = task_progress.get(task_id, False)
            status = "✅" if completed else "⬜"
            reward_text = f"💰{task_info['reward_gold']}"
            if task_info['reward_exp'] > 0:
                reward_text += f" 📈{task_info['reward_exp']}"

            lines.append(f"{status} {task_info['name']}")
            lines.append(f"   {task_info['description']}")
            lines.append(f"   奖励: {reward_text}")
            lines.append("")

        # 统计完成情况
        completed_count = sum(1 for v in task_progress.values() if v)
        total_count = len(DAILY_TASKS)
        lines.append(f"完成进度: {completed_count}/{total_count}")

        # 全部完成额外奖励提示
        if completed_count == total_count:
            lines.append("🎉 今日任务已全部完成！")
        else:
            lines.append(f"💡 全部完成可额外获得 500 灵石奖励！")

        lines.append("═══════════════════")
        lines.append("使用「领取任务奖励」领取已完成任务的奖励")

        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_claim_daily_rewards(self, player: Player, event: AstrMessageEvent):
        """领取每日任务奖励"""
        today = date.today().isoformat()
        task_progress = await self.db.get_daily_task_progress(player.user_id, today)
        claimed_tasks = await self.db.get_claimed_daily_tasks(player.user_id, today)

        total_gold = 0
        total_exp = 0
        claimed_names = []

        for task_id, task_info in DAILY_TASKS.items():
            # 检查任务是否完成且未领取
            if task_progress.get(task_id, False) and task_id not in claimed_tasks:
                total_gold += task_info['reward_gold']
                total_exp += task_info['reward_exp']
                claimed_names.append(task_info['name'])
                await self.db.mark_daily_task_claimed(player.user_id, today, task_id)

        # 检查是否全部完成（额外奖励）
        all_completed = all(task_progress.get(tid, False) for tid in DAILY_TASKS.keys())
        bonus_claimed = await self.db.is_daily_bonus_claimed(player.user_id, today)

        if all_completed and not bonus_claimed:
            total_gold += 500
            claimed_names.append("全勤奖励")
            await self.db.mark_daily_bonus_claimed(player.user_id, today)

        if not claimed_names:
            yield event.plain_result("道友暂无可领取的任务奖励。\n请先完成每日任务后再来领取！")
            return

        # 发放奖励
        p_clone = player.clone()
        p_clone.gold += total_gold
        p_clone.experience += total_exp
        await self.db.update_player(p_clone)

        lines = [
            "═══ 【奖励领取成功】 ═══",
            f"已领取任务: {', '.join(claimed_names)}",
            f"获得灵石: +{total_gold}",
        ]
        if total_exp > 0:
            lines.append(f"获得修为: +{total_exp}")
        lines.append(f"当前灵石: {p_clone.gold}")
        lines.append("═══════════════════")

        yield event.plain_result("\n".join(lines))

    async def complete_task(self, user_id: str, task_id: str):
        """标记任务完成（供其他处理器调用）"""
        if task_id not in DAILY_TASKS:
            return
        today = date.today().isoformat()
        await self.db.complete_daily_task(user_id, today, task_id)
