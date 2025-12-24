# handlers/daily_task_handler.py
"""每日任务处理器 - 全新重构版本，更有趣且奖励可正常领取"""

import random
import hashlib
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["DailyTaskHandler"]

# ========== 任务池定义 ==========
# 基础任务（每天必有）
FIXED_TASKS = {
    "check_in": {
        "name": "🌅 晨钟暮鼓",
        "description": "完成每日签到",
        "reward_gold": 50,
        "reward_exp": 20,
        "category": "basic"
    },
}

# 随机任务池（每天随机抽取3个）
RANDOM_TASK_POOL = {
    "cultivation": {
        "name": "🧘 闭关修炼",
        "description": "完成一次闭关修炼（出关即可）",
        "reward_gold": 100,
        "reward_exp": 80,
        "category": "cultivation"
    },
    "realm_explore": {
        "name": "🗺️ 秘境探险",
        "description": "进入秘境探索一次",
        "reward_gold": 120,
        "reward_exp": 100,
        "category": "exploration"
    },
    "realm_advance": {
        "name": "⚔️ 秘境深入",
        "description": "在秘境中前进至少3层",
        "reward_gold": 200,
        "reward_exp": 150,
        "target": 3,
        "category": "exploration"
    },
    "boss_fight": {
        "name": "👹 斩妖除魔",
        "description": "参与一次世界Boss讨伐",
        "reward_gold": 180,
        "reward_exp": 120,
        "category": "combat"
    },
    "spar": {
        "name": "🤺 以武会友",
        "description": "与其他修士切磋一次",
        "reward_gold": 80,
        "reward_exp": 50,
        "category": "combat"
    },
    "duel": {
        "name": "💰 奇斗赌局",
        "description": "参与一次奇斗（灵石对决）",
        "reward_gold": 150,
        "reward_exp": 60,
        "category": "combat"
    },
    "adventure": {
        "name": "🎲 奇遇探索",
        "description": "触发一次奇遇",
        "reward_gold": 100,
        "reward_exp": 80,
        "category": "exploration"
    },
    "bounty": {
        "name": "📜 悬赏猎人",
        "description": "完成一次悬赏任务",
        "reward_gold": 150,
        "reward_exp": 100,
        "category": "quest"
    },
    "shop_buy": {
        "name": "🛒 仙市淘宝",
        "description": "在商店购买任意物品",
        "reward_gold": 30,
        "reward_exp": 20,
        "category": "economy"
    },
    "use_item": {
        "name": "💊 丹药养生",
        "description": "使用一件物品（丹药/装备/功法）",
        "reward_gold": 50,
        "reward_exp": 30,
        "category": "economy"
    },
    "alchemy": {
        "name": "🔥 炼丹一炉",
        "description": "进行一次炼丹",
        "reward_gold": 120,
        "reward_exp": 80,
        "category": "crafting"
    },
    "smithing": {
        "name": "🔨 锻造神兵",
        "description": "进行一次炼器",
        "reward_gold": 120,
        "reward_exp": 80,
        "category": "crafting"
    },
    "sect_donate": {
        "name": "🏛️ 宗门贡献",
        "description": "向宗门捐献灵石",
        "reward_gold": 80,
        "reward_exp": 100,
        "category": "social"
    },
    "transfer": {
        "name": "🤝 乐善好施",
        "description": "向其他修士转账或赠送物品",
        "reward_gold": 60,
        "reward_exp": 40,
        "category": "social"
    },
}

# 连续签到奖励
STREAK_REWARDS = {
    3: {"gold": 200, "name": "三日勤修"},
    7: {"gold": 500, "name": "七日精进"},
    14: {"gold": 1000, "name": "半月苦修"},
    30: {"gold": 3000, "name": "月满功成"},
}

# 全勤奖励
ALL_COMPLETE_BONUS = {
    "gold": 300,
    "exp": 200,
    "name": "🎊 全勤大礼"
}


class DailyTaskHandler:
    """每日任务处理器 - 支持随机任务、连续签到、进度追踪"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    def _get_today_seed(self, user_id: str) -> str:
        """生成今日随机种子（基于日期+用户ID，确保每人每天任务不同但固定）"""
        today = date.today().isoformat()
        seed_str = f"{today}_{user_id}_xiuxian_daily"
        return hashlib.md5(seed_str.encode()).hexdigest()

    def _get_today_random_tasks(self, user_id: str) -> Dict[str, dict]:
        """获取今日随机任务（每人每天固定3个随机任务）"""
        seed = self._get_today_seed(user_id)
        random.seed(seed)
        
        task_ids = list(RANDOM_TASK_POOL.keys())
        selected_ids = random.sample(task_ids, min(3, len(task_ids)))
        
        random.seed()  # 重置随机种子
        
        return {tid: RANDOM_TASK_POOL[tid] for tid in selected_ids}

    def get_today_tasks(self, user_id: str) -> Dict[str, dict]:
        """获取今日所有任务（固定任务 + 随机任务）"""
        tasks = dict(FIXED_TASKS)
        tasks.update(self._get_today_random_tasks(user_id))
        return tasks

    @player_required
    async def handle_daily_tasks(self, player: Player, event: AstrMessageEvent):
        """查看每日任务列表"""
        today = date.today().isoformat()
        today_tasks = self.get_today_tasks(player.user_id)
        
        # 获取任务进度和已领取状态
        task_progress = await self.db.get_daily_task_progress(player.user_id, today)
        claimed_tasks = await self.db.get_claimed_daily_tasks(player.user_id, today)
        
        # 获取连续签到天数
        streak = await self._get_check_in_streak(player.user_id)

        lines = [
            "━━ 📋 每日任务 ━━",
            f"📅 {today}",
            f"🔥 连续签到: {streak}天",
            ""
        ]

        # 按类别分组显示
        categories = {
            "basic": "【基础任务】",
            "cultivation": "【修炼任务】",
            "combat": "【战斗任务】",
            "exploration": "【探索任务】",
            "quest": "【悬赏任务】",
            "economy": "【经济任务】",
            "crafting": "【炼制任务】",
            "social": "【社交任务】"
        }
        
        completed_count = 0
        total_count = len(today_tasks)
        
        for task_id, task_info in today_tasks.items():
            completed = task_progress.get(task_id, False)
            claimed = task_id in claimed_tasks
            
            if completed:
                completed_count += 1
                if claimed:
                    status = "✅ 已领取"
                else:
                    status = "🎁 可领取"
            else:
                status = "⬜ 未完成"
            
            reward_text = f"💰{task_info['reward_gold']}"
            if task_info.get('reward_exp', 0) > 0:
                reward_text += f" 📈{task_info['reward_exp']}"

            lines.append(f"{status} {task_info['name']}")
            lines.append(f"  └ {task_info['description']}")
            lines.append(f"  └ 奖励: {reward_text}")

        lines.append("")
        lines.append(f"📊 进度: {completed_count}/{total_count}")
        
        # 全勤奖励提示
        bonus_claimed = await self.db.is_daily_bonus_claimed(player.user_id, today)
        if completed_count == total_count:
            if bonus_claimed:
                lines.append("🎊 全勤奖励已领取!")
            else:
                lines.append(f"🎊 全勤奖励可领取! (+{ALL_COMPLETE_BONUS['gold']}💰)")
        else:
            remaining = total_count - completed_count
            lines.append(f"💡 再完成{remaining}个任务可领全勤奖励!")
        
        # 连续签到奖励提示
        next_streak = self._get_next_streak_milestone(streak)
        if next_streak:
            days_to_next = next_streak - streak
            reward = STREAK_REWARDS[next_streak]
            lines.append(f"🔥 再签到{days_to_next}天可获「{reward['name']}」!")
        
        lines.append("")
        lines.append("💡 使用「领取任务奖励」领取")
        lines.append("━━━━━━━━━━━━")

        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_claim_daily_rewards(self, player: Player, event: AstrMessageEvent):
        """领取每日任务奖励"""
        today = date.today().isoformat()
        today_tasks = self.get_today_tasks(player.user_id)
        
        task_progress = await self.db.get_daily_task_progress(player.user_id, today)
        claimed_tasks = await self.db.get_claimed_daily_tasks(player.user_id, today)

        total_gold = 0
        total_exp = 0
        claimed_names = []

        # 领取已完成但未领取的任务奖励
        for task_id, task_info in today_tasks.items():
            if task_progress.get(task_id, False) and task_id not in claimed_tasks:
                total_gold += task_info['reward_gold']
                total_exp += task_info.get('reward_exp', 0)
                claimed_names.append(task_info['name'])
                await self.db.mark_daily_task_claimed(player.user_id, today, task_id)

        # 检查全勤奖励
        all_completed = all(task_progress.get(tid, False) for tid in today_tasks.keys())
        bonus_claimed = await self.db.is_daily_bonus_claimed(player.user_id, today)

        if all_completed and not bonus_claimed:
            total_gold += ALL_COMPLETE_BONUS['gold']
            total_exp += ALL_COMPLETE_BONUS['exp']
            claimed_names.append(ALL_COMPLETE_BONUS['name'])
            await self.db.mark_daily_bonus_claimed(player.user_id, today)

        # 检查连续签到奖励
        streak = await self._get_check_in_streak(player.user_id)
        streak_reward = STREAK_REWARDS.get(streak)
        if streak_reward:
            streak_claimed = await self._is_streak_reward_claimed(player.user_id, streak)
            if not streak_claimed:
                total_gold += streak_reward['gold']
                claimed_names.append(f"🔥 {streak_reward['name']}")
                await self._mark_streak_reward_claimed(player.user_id, streak)

        if not claimed_names:
            yield event.plain_result(
                "道友暂无可领取的任务奖励。\n"
                "请先完成每日任务后再来领取！\n"
                "💡 提示：使用「每日任务」查看任务列表"
            )
            return

        # 发放奖励
        p_clone = player.clone()
        p_clone.gold += total_gold
        p_clone.experience += total_exp
        await self.db.update_player(p_clone)

        lines = [
            "━━ 🎁 奖励领取成功 ━━",
        ]
        for name in claimed_names:
            lines.append(f"✓ {name}")
        lines.append("")
        lines.append(f"💰 灵石: +{total_gold}")
        if total_exp > 0:
            lines.append(f"📈 修为: +{total_exp}")
        lines.append(f"💎 当前灵石: {p_clone.gold}")
        lines.append("━━━━━━━━━━━━")

        yield event.plain_result("\n".join(lines))

    async def complete_task(self, user_id: str, task_id: str) -> bool:
        """
        标记任务完成（供其他处理器调用）
        返回是否成功标记（任务存在且之前未完成返回True）
        """
        today = date.today().isoformat()
        today_tasks = self.get_today_tasks(user_id)
        
        # 检查任务是否在今日任务列表中
        if task_id not in today_tasks:
            return False
        
        # 检查是否已完成
        progress = await self.db.get_daily_task_progress(user_id, today)
        if progress.get(task_id, False):
            return False  # 已完成
        
        await self.db.complete_daily_task(user_id, today, task_id)
        return True

    async def add_task_progress(self, user_id: str, task_id: str, amount: int = 1) -> Tuple[bool, Optional[str]]:
        """
        增加任务进度（用于需要多次完成的任务，如秘境前进3层）
        返回 (是否完成任务, 提示消息)
        """
        today = date.today().isoformat()
        today_tasks = self.get_today_tasks(user_id)
        
        if task_id not in today_tasks:
            return False, None
        
        task_info = today_tasks[task_id]
        target = task_info.get('target', 1)
        
        # 获取当前进度
        current = await self.db.get_task_counter(user_id, today, task_id)
        new_progress = current + amount
        
        await self.db.set_task_counter(user_id, today, task_id, new_progress)
        
        if new_progress >= target:
            completed = await self.complete_task(user_id, task_id)
            if completed:
                return True, f"🎯 每日任务「{task_info['name']}」已完成！"
        
        return False, None

    async def _get_check_in_streak(self, user_id: str) -> int:
        """获取连续签到天数"""
        return await self.db.get_check_in_streak(user_id)

    def _get_next_streak_milestone(self, current_streak: int) -> Optional[int]:
        """获取下一个连续签到里程碑"""
        milestones = sorted(STREAK_REWARDS.keys())
        for m in milestones:
            if m > current_streak:
                return m
        return None

    async def _is_streak_reward_claimed(self, user_id: str, streak: int) -> bool:
        """检查连续签到奖励是否已领取"""
        return await self.db.is_streak_reward_claimed(user_id, streak)

    async def _mark_streak_reward_claimed(self, user_id: str, streak: int):
        """标记连续签到奖励已领取"""
        await self.db.mark_streak_reward_claimed(user_id, streak)
