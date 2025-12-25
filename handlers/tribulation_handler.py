# handlers/tribulation_handler.py
"""天劫系统处理器 - 高境界突破时的特殊挑战"""

import random
import time
from typing import Dict, List, Tuple
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["TribulationHandler"]

# 天劫等级定义（根据境界触发不同等级的天劫）
TRIBULATION_LEVELS = {
    # 境界索引: 天劫信息
    10: {  # 尊者境
        "name": "小天劫",
        "description": "天空乌云密布，雷光闪烁，一道天雷劈下！",
        "damage_min": 50,
        "damage_max": 100,
        "waves": 3,
        "success_bonus_exp": 500,
        "success_bonus_gold": 300
    },
    15: {  # 真一境
        "name": "中天劫",
        "description": "九天之上，雷云翻涌，紫色天雷携带毁灭之力降临！",
        "damage_min": 100,
        "damage_max": 200,
        "waves": 5,
        "success_bonus_exp": 1000,
        "success_bonus_gold": 600
    },
    20: {  # 真仙境
        "name": "大天劫",
        "description": "天地变色，日月无光，九九八十一道天雷齐聚，这是渡仙劫！",
        "damage_min": 200,
        "damage_max": 400,
        "waves": 9,
        "success_bonus_exp": 3000,
        "success_bonus_gold": 1500
    },
    25: {  # 仙帝境
        "name": "帝劫",
        "description": "混沌雷海翻涌，天道法则显化，这是成就仙帝的最终考验！",
        "damage_min": 400,
        "damage_max": 800,
        "waves": 12,
        "success_bonus_exp": 8000,
        "success_bonus_gold": 5000
    }
}


class TribulationHandler:
    """天劫系统相关指令处理器"""

    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    def get_tribulation_for_level(self, level_index: int) -> Dict:
        """获取对应境界的天劫信息"""
        # 找到小于等于当前境界的最高天劫等级
        applicable_levels = [lvl for lvl in TRIBULATION_LEVELS.keys() if lvl <= level_index]
        if not applicable_levels:
            return None
        return TRIBULATION_LEVELS[max(applicable_levels)]

    def should_trigger_tribulation(self, current_level: int, target_level: int) -> bool:
        """判断是否需要触发天劫"""
        # 检查目标境界是否是天劫触发点
        return target_level in TRIBULATION_LEVELS

    @player_required
    async def handle_tribulation_info(self, player: Player, event: AstrMessageEvent):
        """查看天劫信息"""
        current_level = player.level_index
        next_tribulation_level = None

        # 找到下一个天劫境界
        for level in sorted(TRIBULATION_LEVELS.keys()):
            if level > current_level:
                next_tribulation_level = level
                break

        lines = ["━━ 天劫信息 ━━", ""]

        if next_tribulation_level:
            trib_info = TRIBULATION_LEVELS[next_tribulation_level]
            target_level_name = self.config_manager.level_data[next_tribulation_level]["level_name"]

            lines.extend([
                f"📍 当前境界: {player.get_level(self.config_manager)}",
                f"⚡ 下一天劫: {trib_info['name']}",
                f"🎯 触发境界: {target_level_name}",
                "",
                "--- 天劫详情 ---",
                f"雷劫波数: {trib_info['waves']} 波",
                f"每波伤害: {trib_info['damage_min']}-{trib_info['damage_max']}",
                "",
                "--- 渡劫成功奖励 ---",
                f"💰 灵石: +{trib_info['success_bonus_gold']}",
                f"📈 修为: +{trib_info['success_bonus_exp']}",
            ])
        else:
            lines.append("道友已渡过所有天劫，天道已无法奈何于你！")

        # 显示所有天劫等级
        lines.extend(["", "--- 天劫等级一览 ---"])
        for level, info in sorted(TRIBULATION_LEVELS.items()):
            level_name = self.config_manager.level_data[level]["level_name"]
            status = "✅" if current_level >= level else "⬜"
            lines.append(f"{status} {info['name']} - {level_name} ({info['waves']}波)")

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_challenge_tribulation(self, player: Player, event: AstrMessageEvent):
        """主动挑战天劫（用于已达到天劫境界但未渡劫的情况）"""
        current_level = player.level_index

        # 检查是否有可挑战的天劫
        tribulation = self.get_tribulation_for_level(current_level)
        if not tribulation:
            yield event.plain_result("道友境界尚浅，还未到渡劫之时。")
            return

        # 检查是否在天劫境界
        if current_level not in TRIBULATION_LEVELS:
            yield event.plain_result("道友当前境界无需渡劫，继续修炼突破即可。")
            return

        # v2.6.4: 检查每日次数限制（3次/天）
        from datetime import date
        today = date.today().isoformat()
        current_count = await self.db.get_daily_tribulation_count(player.user_id, today)
        MAX_DAILY_TRIBULATION = 3
        
        if current_count >= MAX_DAILY_TRIBULATION:
            yield event.plain_result(
                f"今日渡劫次数已用完（{current_count}/{MAX_DAILY_TRIBULATION}）。\n"
                f"天劫乃逆天而行，不可操之过急，明日再试吧。"
            )
            return

        # 检查玩家状态
        if player.state != "空闲":
            yield event.plain_result(f"道友当前正在「{player.state}」中，无法渡劫。")
            return

        # 开始渡劫前增加计数
        await self.db.increment_tribulation_count(player.user_id, today)
        
        # 开始渡劫
        result = await self._process_tribulation(player, tribulation)
        
        # 添加剩余次数提示
        remaining = MAX_DAILY_TRIBULATION - current_count - 1
        result += f"\n\n今日剩余渡劫次数：{remaining}/{MAX_DAILY_TRIBULATION}"
        
        yield event.plain_result(result)

    async def _process_tribulation(self, player: Player, tribulation: Dict) -> str:
        """处理天劫过程"""
        lines = [
            f"━━ {tribulation['name']} ━━",
            "",
            tribulation["description"],
            "",
            "--- 渡劫开始 ---",
        ]

        p_clone = player.clone()
        combat_stats = p_clone.get_combat_stats(self.config_manager)
        current_hp = combat_stats["hp"]
        max_hp = combat_stats["max_hp"]
        defense = combat_stats["defense"]

        total_damage_taken = 0
        survived = True

        for wave in range(1, tribulation["waves"] + 1):
            # 计算本波伤害（防御可以减免部分伤害）
            base_damage = random.randint(tribulation["damage_min"], tribulation["damage_max"])
            actual_damage = max(1, base_damage - defense // 2)

            current_hp -= actual_damage
            total_damage_taken += actual_damage

            # 随机生成渡劫描述
            wave_desc = self._get_wave_description(wave, tribulation["waves"])
            lines.append(f"第{wave}波: {wave_desc} (-{actual_damage} HP)")

            if current_hp <= 0:
                survived = False
                lines.append(f"💀 道友在第{wave}波天雷中陨落...")
                break

        lines.append("")

        if survived:
            # 渡劫成功
            p_clone.hp = max(1, current_hp)  # 保留剩余血量
            p_clone.gold += tribulation["success_bonus_gold"]
            p_clone.experience += tribulation["success_bonus_exp"]

            lines.extend([
                "🎉 【渡劫成功】 🎉",
                "",
                f"剩余生命: {current_hp}/{max_hp}",
                f"获得灵石: +{tribulation['success_bonus_gold']}",
                f"获得修为: +{tribulation['success_bonus_exp']}",
                "",
                "道友成功渡过天劫，修为更进一步！"
            ])
        else:
            # 渡劫失败 - 损失部分修为和灵石
            exp_loss = int(p_clone.experience * 0.1)  # 损失10%修为
            gold_loss = int(p_clone.gold * 0.05)  # 损失5%灵石
            p_clone.experience = max(0, p_clone.experience - exp_loss)
            p_clone.gold = max(0, p_clone.gold - gold_loss)
            p_clone.hp = int(max_hp * 0.1)  # 复活后只有10%血量

            lines.extend([
                "💔 【渡劫失败】 💔",
                "",
                f"损失修为: -{exp_loss}",
                f"损失灵石: -{gold_loss}",
                "",
                "道友渡劫失败，被天雷击落，幸得一缕残魂逃脱...",
                "请养好伤势后再次尝试渡劫。"
            ])

        await self.db.update_player(p_clone)
        lines.append("━━━━━━━━━━━━")

        return "\n".join(lines)

    def _get_wave_description(self, wave: int, total_waves: int) -> str:
        """获取天雷波次描述"""
        descriptions = [
            "一道紫雷劈下",
            "雷光闪烁，天雷降临",
            "轰隆巨响，雷霆万钧",
            "九天神雷，威势惊人",
            "雷海翻涌，电蛇狂舞",
            "天罚之雷，毁天灭地",
            "混沌雷劫，法则显化",
            "天道之怒，雷霆审判",
            "终极天雷，万劫不复"
        ]

        if wave == total_waves:
            return "最后一道天雷，携带毁灭之力！"
        elif wave == 1:
            return "第一道天雷试探而来"
        else:
            return random.choice(descriptions)

    async def process_breakthrough_tribulation(self, player: Player, target_level: int) -> Tuple[bool, str]:
        """
        处理突破时的天劫（供其他处理器调用）
        返回: (是否成功, 结果消息)
        """
        if target_level not in TRIBULATION_LEVELS:
            return True, ""  # 不需要渡劫

        tribulation = TRIBULATION_LEVELS[target_level]
        result_msg = await self._process_tribulation(player, tribulation)

        # 检查是否成功（通过检查消息中是否包含成功标记）
        success = "渡劫成功" in result_msg
        return success, result_msg
