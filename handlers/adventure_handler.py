# handlers/adventure_handler.py
"""奇遇系统处理器 - 提供随机奇遇事件功能"""

import random
import time
from datetime import date
from typing import Dict, List, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["AdventureHandler"]

# 奇遇事件定义
ADVENTURE_EVENTS = {
    "treasure_cave": {
        "name": "发现宝藏洞府",
        "description": "道友在山间漫步时，发现了一处隐秘的洞府，里面藏有前人遗留的宝物。",
        "weight": 15,
        "rewards": {"gold_min": 200, "gold_max": 500, "exp_min": 50, "exp_max": 150}
    },
    "herb_garden": {
        "name": "误入灵药园",
        "description": "道友误入一片灵气充沛的药园，采集到了珍贵的灵药。",
        "weight": 20,
        "rewards": {"gold_min": 100, "gold_max": 300, "exp_min": 100, "exp_max": 200}
    },
    "ancient_scroll": {
        "name": "获得古卷",
        "description": "道友在古迹中发现了一卷泛黄的功法残卷，参悟后修为大增。",
        "weight": 10,
        "rewards": {"gold_min": 0, "gold_max": 100, "exp_min": 200, "exp_max": 500}
    },
    "merchant_encounter": {
        "name": "偶遇行商",
        "description": "道友在路上遇到一位神秘商人，以极低的价格购得了一批灵石。",
        "weight": 18,
        "rewards": {"gold_min": 300, "gold_max": 800, "exp_min": 0, "exp_max": 50}
    },
    "spirit_beast": {
        "name": "灵兽赠宝",
        "description": "道友救助了一只受伤的灵兽，灵兽为表感谢，赠予了一颗灵珠。",
        "weight": 12,
        "rewards": {"gold_min": 150, "gold_max": 400, "exp_min": 80, "exp_max": 180}
    },
    "meditation_insight": {
        "name": "顿悟天机",
        "description": "道友在静坐时突然心有所感，对大道有了更深的领悟。",
        "weight": 8,
        "rewards": {"gold_min": 0, "gold_max": 50, "exp_min": 300, "exp_max": 600}
    },
    "fallen_cultivator": {
        "name": "陨落修士遗物",
        "description": "道友发现了一位陨落修士的遗骸，从其储物袋中获得了一些遗物。",
        "weight": 10,
        "rewards": {"gold_min": 250, "gold_max": 600, "exp_min": 100, "exp_max": 250}
    },
    "nothing": {
        "name": "平淡无奇",
        "description": "道友四处游历，但今日似乎运气不佳，并未遇到什么特别的事情。",
        "weight": 7,
        "rewards": {"gold_min": 10, "gold_max": 50, "exp_min": 10, "exp_max": 30}
    }
}

# 特殊奇遇（低概率高收益）
RARE_ADVENTURES = {
    "immortal_inheritance": {
        "name": "仙人传承",
        "description": "道友机缘巧合之下，获得了一位飞升仙人留下的传承！",
        "weight": 2,
        "rewards": {"gold_min": 1000, "gold_max": 3000, "exp_min": 500, "exp_max": 1500}
    },
    "dragon_treasure": {
        "name": "龙宫宝藏",
        "description": "道友意外进入了一处上古龙宫遗迹，获得了大量宝物！",
        "weight": 1,
        "rewards": {"gold_min": 2000, "gold_max": 5000, "exp_min": 300, "exp_max": 800}
    }
}


class AdventureHandler:
    """奇遇系统相关指令处理器"""

    # 每日奇遇次数上限
    MAX_DAILY_ADVENTURES = 3

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    @player_required
    async def handle_adventure(self, player: Player, event: AstrMessageEvent):
        """触发一次奇遇"""
        today = date.today().isoformat()
        user_id = player.user_id

        # 检查每日次数限制
        current_count = await self.db.get_daily_adventure_count(user_id, today)
        if current_count >= self.MAX_DAILY_ADVENTURES:
            yield event.plain_result(
                f"道友今日的气运已尽，明日再来探索吧。\n"
                f"（每日奇遇次数上限：{self.MAX_DAILY_ADVENTURES}次）"
            )
            return

        # 检查玩家状态
        if player.state != "空闲":
            yield event.plain_result(f"道友当前正在「{player.state}」中，无法外出探索奇遇。")
            return

        # 随机选择奇遇事件
        adventure = self._select_adventure()
        rewards = adventure["rewards"]

        # 计算实际奖励（根据玩家境界有加成）
        level_bonus = 1 + player.level_index * 0.05  # 每个境界5%加成
        gold_reward = int(random.randint(rewards["gold_min"], rewards["gold_max"]) * level_bonus)
        exp_reward = int(random.randint(rewards["exp_min"], rewards["exp_max"]) * level_bonus)

        # 更新玩家数据
        p_clone = player.clone()
        p_clone.gold += gold_reward
        p_clone.experience += exp_reward
        await self.db.update_player(p_clone)

        # 记录奇遇
        await self.db.increment_adventure_count(user_id, today)
        await self.db.add_adventure_log(
            user_id, today, adventure["name"],
            adventure["description"], gold_reward, exp_reward, time.time()
        )

        # 构建响应消息
        remaining = self.MAX_DAILY_ADVENTURES - current_count - 1
        rarity_prefix = ""
        if adventure["name"] in [v["name"] for v in RARE_ADVENTURES.values()]:
            rarity_prefix = "🌟【稀有奇遇】🌟\n"

        lines = [
            f"{rarity_prefix}═══ 【{adventure['name']}】 ═══",
            "",
            adventure["description"],
            "",
            "--- 获得奖励 ---",
        ]

        if gold_reward > 0:
            lines.append(f"💰 灵石: +{gold_reward}")
        if exp_reward > 0:
            lines.append(f"📈 修为: +{exp_reward}")

        lines.extend([
            "",
            f"今日剩余奇遇次数: {remaining}/{self.MAX_DAILY_ADVENTURES}",
            "═══════════════════"
        ])

        yield event.plain_result("\n".join(lines))

    def _select_adventure(self) -> Dict:
        """根据权重随机选择奇遇事件"""
        # 合并普通奇遇和稀有奇遇
        all_adventures = {**ADVENTURE_EVENTS, **RARE_ADVENTURES}

        # 计算总权重
        total_weight = sum(adv["weight"] for adv in all_adventures.values())

        # 随机选择
        rand_val = random.uniform(0, total_weight)
        cumulative = 0

        for adv_id, adv_info in all_adventures.items():
            cumulative += adv_info["weight"]
            if rand_val <= cumulative:
                return adv_info

        # 默认返回最后一个
        return list(all_adventures.values())[-1]

    @player_required
    async def handle_adventure_status(self, player: Player, event: AstrMessageEvent):
        """查看今日奇遇状态"""
        today = date.today().isoformat()
        current_count = await self.db.get_daily_adventure_count(player.user_id, today)
        remaining = max(0, self.MAX_DAILY_ADVENTURES - current_count)

        lines = [
            "═══ 【奇遇状态】 ═══",
            f"📅 日期: {today}",
            f"🎲 今日已探索: {current_count} 次",
            f"✨ 剩余次数: {remaining} 次",
            "",
            "💡 使用「奇遇」指令开始探索",
            "═══════════════════"
        ]

        yield event.plain_result("\n".join(lines))
