# core/combat_manager.py

import random
import time
from typing import Dict, List, Optional, Tuple, Any

from astrbot.api import logger, AstrBotConfig
from ..models import Player, Boss, ActiveWorldBoss, Monster
from ..data import DataBase
from ..config_manager import ConfigManager

class MonsterGenerator:
    """基于标签系统的怪物和Boss生成器"""

    @staticmethod
    def _generate_rewards(base_loot: List) -> Dict[str, int]:
        gained_items = {}
        for entry in base_loot:
            if random.random() < entry.get("chance", 0):
                quantity_range = entry.get("quantity", [1, 1])
                min_qty = quantity_range[0]
                max_qty = quantity_range[1] if len(quantity_range) > 1 else min_qty

                item_id = str(entry["item_id"])
                amount = random.randint(min_qty, max_qty)
                gained_items[item_id] = gained_items.get(item_id, 0) + amount
        return gained_items

    @classmethod
    def create_monster(cls, template_id: str, player_level_index: int, config_manager: ConfigManager) -> Optional[Monster]:
        template = config_manager.monster_data.get(template_id)
        if not template:
            logger.warning(f"尝试创建怪物失败：找不到模板ID {template_id}")
            return None

        base_hp = 15 * player_level_index + 60
        base_attack = 2 * player_level_index + 8
        base_defense = 1 * player_level_index + 4
        base_gold = 3 * player_level_index + 10
        base_exp = 5 * player_level_index + 20

        final_name = template["name"]
        final_hp = base_hp
        final_attack = base_attack
        final_defense = base_defense
        final_gold = base_gold
        final_exp = base_exp
        combined_loot_table = []

        for tag_name in template.get("tags", []):
            tag_effect = config_manager.tag_data.get(tag_name)
            if not tag_effect:
                continue

            if "name_prefix" in tag_effect:
                final_name = f"【{tag_effect['name_prefix']}】{final_name}"

            final_hp *= tag_effect.get("hp_multiplier", 1.0)
            final_attack *= tag_effect.get("attack_multiplier", 1.0)
            final_defense *= tag_effect.get("defense_multiplier", 1.0)
            final_gold *= tag_effect.get("gold_multiplier", 1.0)
            final_exp *= tag_effect.get("exp_multiplier", 1.0)

            if "add_to_loot" in tag_effect:
                combined_loot_table.extend(tag_effect["add_to_loot"])

        final_hp = int(final_hp)
        instance = Monster(
            id=template_id,
            name=final_name,
            hp=final_hp,
            max_hp=final_hp,
            attack=int(final_attack),
            defense=int(final_defense),
            rewards={
                "gold": int(final_gold),
                "experience": int(final_exp),
                "items": cls._generate_rewards(combined_loot_table)
            }
        )
        return instance

    @classmethod
    def create_boss(cls, template_id: str, player_level_index: int, config_manager: ConfigManager, difficulty_multiplier: float = 1.0) -> Optional[Boss]:
        template = config_manager.boss_data.get(template_id)
        if not template:
            logger.warning(f"尝试创建Boss失败：找不到模板ID {template_id}")
            return None

        base_hp = 200 * player_level_index + 1000
        base_attack = 15 * player_level_index + 60
        base_defense = 8 * player_level_index + 30
        base_gold = 80 * player_level_index + 1500
        base_exp = 150 * player_level_index + 3000

        final_name = template["name"]
        final_hp = base_hp
        final_attack = base_attack
        final_defense = base_defense
        final_gold = base_gold
        final_exp = base_exp
        combined_loot_table = []

        for tag_name in template.get("tags", []):
            tag_effect = config_manager.tag_data.get(tag_name, {})
            if "name_prefix" in tag_effect:
                final_name = f"【{tag_effect['name_prefix']}】{final_name}"
            final_hp *= tag_effect.get("hp_multiplier", 1.0)
            final_attack *= tag_effect.get("attack_multiplier", 1.0)
            final_defense *= tag_effect.get("defense_multiplier", 1.0)
            final_gold *= tag_effect.get("gold_multiplier", 1.0)
            final_exp *= tag_effect.get("exp_multiplier", 1.0)
            if "add_to_loot" in tag_effect:
                combined_loot_table.extend(tag_effect["add_to_loot"])
        
        final_hp *= difficulty_multiplier
        final_attack *= difficulty_multiplier
        final_defense *= difficulty_multiplier

        final_hp = int(final_hp)
        instance = Boss(
            id=template_id,
            name=final_name,
            hp=final_hp,
            max_hp=final_hp,
            attack=int(final_attack),
            defense=int(final_defense),
            cooldown_minutes=template["cooldown_minutes"],
            rewards={
                "gold": int(final_gold),
                "experience": int(final_exp),
                "items": cls._generate_rewards(combined_loot_table)
            }
        )
        return instance

class BattleManager:
    """战斗管理器"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self._broadcast_callback = None

    def set_broadcast_callback(self, callback):
        """设置Boss击杀广播回调函数"""
        self._broadcast_callback = callback

    async def ensure_bosses_are_spawned(self) -> List[Tuple[ActiveWorldBoss, Boss]]:
        active_boss_instances = await self.db.get_active_bosses()
        active_boss_map = {b.boss_id: b for b in active_boss_instances}
        all_boss_templates = self.config_manager.boss_data
        now = time.time()

        top_players = await self.db.get_top_players(self.config["VALUES"].get("WORLD_BOSS_TOP_PLAYERS_AVG", 5))
        difficulty_multiplier = self.config["VALUES"].get("WORLD_BOSS_DIFFICULTY_MULTIPLIER", 3.0)

        for boss_id, template in all_boss_templates.items():
            cooldown_minutes = template.get("cooldown_minutes", 1440)
            cooldown_seconds = cooldown_minutes * 60
            
            if boss_id in active_boss_map:
                instance = active_boss_map[boss_id]
                if instance.current_hp <= 0:
                    time_since_defeat = now - (getattr(instance, 'defeated_at', None) or instance.spawned_at)
                    if time_since_defeat >= cooldown_seconds:
                        await self.db.clear_boss_data(boss_id)
                        del active_boss_map[boss_id]
                        logger.info(f"Boss {template['name']} 冷却时间已过，准备重新生成...")
                    else:
                        remaining = int((cooldown_seconds - time_since_defeat) / 60)
                        logger.debug(f"Boss {template['name']} 仍在冷却中，剩余 {remaining} 分钟")
                        continue
                else:
                    continue
            else:
                last_defeat_time = await self.db.get_last_boss_defeat_time(boss_id)
                if last_defeat_time:
                    time_since_defeat = now - last_defeat_time
                    if time_since_defeat < cooldown_seconds:
                        remaining = int((cooldown_seconds - time_since_defeat) / 60)
                        logger.debug(f"Boss {template['name']} 仍在冷却中（从击杀记录），剩余 {remaining} 分钟")
                        continue
            
            logger.info(f"世界Boss {template['name']} (ID: {boss_id}) 当前未激活，开始生成...")

            avg_level_index = int(sum(p.level_index for p in top_players) / len(top_players)) if top_players else 1

            boss_with_stats = MonsterGenerator.create_boss(boss_id, avg_level_index, self.config_manager, difficulty_multiplier)
            if not boss_with_stats:
                logger.error(f"无法为Boss ID {boss_id} 生成属性，请检查配置。")
                continue

            new_boss_instance = ActiveWorldBoss(
                boss_id=boss_id,
                current_hp=boss_with_stats.max_hp,
                max_hp=boss_with_stats.max_hp,
                spawned_at=time.time(),
                level_index=avg_level_index
            )
            await self.db.create_active_boss(new_boss_instance)
            active_boss_map[boss_id] = new_boss_instance

        result = []
        difficulty_multiplier = self.config["VALUES"].get("WORLD_BOSS_DIFFICULTY_MULTIPLIER", 3.0)
        for boss_id, active_instance in active_boss_map.items():
            if active_instance.current_hp > 0:
                boss_template = MonsterGenerator.create_boss(boss_id, active_instance.level_index, self.config_manager, difficulty_multiplier)
                if boss_template:
                    result.append((active_instance, boss_template))
        return result

    async def player_fight_boss(self, player: Player, boss_id: str, player_name: str) -> str:
        active_boss_instance = next((b for b in await self.db.get_active_bosses() if b.boss_id == boss_id), None)
        if not active_boss_instance or active_boss_instance.current_hp <= 0:
            return f"来晚了一步，ID为【{boss_id}】的Boss已被击败或已消失！"

        player_cooldown_minutes = self.config["VALUES"].get("WORLD_BOSS_PLAYER_COOLDOWN_MINUTES", 120)
        last_attack = await self.db.get_player_last_boss_attack(boss_id, player.user_id)
        if last_attack:
            elapsed = time.time() - last_attack
            remaining = player_cooldown_minutes * 60 - elapsed
            if remaining > 0:
                remaining_min = int(remaining / 60)
                remaining_sec = int(remaining % 60)
                return f"你太过疲惫，需要休息后才能再次讨伐此Boss！剩余冷却时间：{remaining_min}分{remaining_sec}秒"

        difficulty_multiplier = self.config["VALUES"].get("WORLD_BOSS_DIFFICULTY_MULTIPLIER", 3.0)
        boss = MonsterGenerator.create_boss(boss_id, active_boss_instance.level_index, self.config_manager, difficulty_multiplier)
        if not boss:
            return "错误：无法加载Boss战斗数据！"

        p_clone = player.clone()
        p_stats = p_clone.get_combat_stats(self.config_manager) # 获取最终战斗属性
        boss_hp = active_boss_instance.current_hp

        total_damage_dealt = 0
        total_damage_taken = 0
        turn = 0
        max_turns = 50

        while p_clone.hp > 1 and boss_hp > 0 and turn < max_turns:
            turn += 1
            damage_to_boss = max(1, p_stats['attack'] - boss.defense)
            damage_to_boss = min(damage_to_boss, boss_hp)
            boss_hp -= damage_to_boss
            total_damage_dealt += damage_to_boss

            if boss_hp <= 0:
                break

            damage_to_player = max(1, boss.attack - p_stats['defense'])
            p_clone.hp -= damage_to_player
            total_damage_taken += damage_to_player

        if p_clone.hp < 1:
            p_clone.hp = 1

        combat_summary = [f"你向【{boss.name}】发起了挑战！", "……激战过后……"]
        if p_clone.hp <= 1 and boss_hp > 0:
            combat_summary.append("✗ 你不敌妖兽，力竭倒下！")
        else:
            combat_summary.append("✓ 你坚持到了最后！")

        combat_summary.append(f"- 战斗历时: {turn}回合")
        combat_summary.append(f"- 总计伤害: {total_damage_dealt}点")
        combat_summary.append(f"- 承受伤害: {total_damage_taken}点")

        final_report = ["\n".join(combat_summary)]
        player.hp = p_clone.hp
        await self.db.update_player(player)
        await self.db.update_active_boss_hp(boss_id, boss_hp)
        if total_damage_dealt > 0:
            await self.db.record_boss_damage(boss_id, player.user_id, player_name, total_damage_dealt)
            final_report.append(f"\n你本次共对Boss贡献了 {total_damage_dealt} 点伤害！")

        if boss_hp <= 0:
            final_report.append(f"\n**惊天动地！【{boss.name}】在众位道友的合力之下倒下了！**")
            final_report.append(await self._end_battle(boss, active_boss_instance))

        return "\n".join(final_report)

    async def _end_battle(self, boss_template: Boss, boss_instance: ActiveWorldBoss) -> str:
        participants = await self.db.get_boss_participants(boss_instance.boss_id)
        if not participants:
            await self.db.clear_boss_data(boss_instance.boss_id)
            return "但似乎无人对此Boss造成伤害，奖励无人获得。"
        
        total_damage_dealt = sum(p['total_damage'] for p in participants) or 1
        reward_report = ["\n--- 战利品结算 ---"]
        updated_players = []
        
        rank_bonus_gold = self.config["VALUES"].get("WORLD_BOSS_RANK_BONUS_GOLD", [2000, 1000, 500])
        rank_bonus_exp = self.config["VALUES"].get("WORLD_BOSS_RANK_BONUS_EXP", [5000, 2500, 1000])
        
        item_rewards = boss_template.rewards.get('items', {})
        
        for rank, p_data in enumerate(participants):
            player_obj = await self.db.get_player_by_id(p_data['user_id'])
            if player_obj:
                damage_contribution = p_data['total_damage'] / total_damage_dealt
                gold_reward = int(boss_template.rewards['gold'] * damage_contribution)
                exp_reward = int(boss_template.rewards['experience'] * damage_contribution)
                
                bonus_gold = 0
                bonus_exp = 0
                rank_title = ""
                
                if rank < len(rank_bonus_gold) or rank < len(rank_bonus_exp):
                    bonus_gold = rank_bonus_gold[rank] if rank < len(rank_bonus_gold) else 0
                    bonus_exp = rank_bonus_exp[rank] if rank < len(rank_bonus_exp) else 0
                    rank_titles = ["🥇第一", "🥈第二", "🥉第三"]
                    rank_title = rank_titles[rank] if rank < len(rank_titles) else ""
                
                total_gold = gold_reward + bonus_gold
                total_exp = exp_reward + bonus_exp
                player_obj.gold += total_gold
                player_obj.experience += total_exp
                updated_players.append(player_obj)
                
                reward_text = f"道友 {p_data['user_name']} 获得灵石 {total_gold}，修为 {total_exp}"
                if rank_title:
                    reward_text = f"{rank_title} {reward_text}（含排名奖励）"
                reward_report.append(reward_text)
                
                if rank == 0 and item_rewards:
                    await self.db.add_items_to_inventory_in_transaction(player_obj.user_id, item_rewards)
                    item_names = []
                    for item_id, qty in item_rewards.items():
                        item_info = self.config_manager.item_data.get(item_id)
                        item_name = item_info.name if item_info else f"物品{item_id}"
                        item_names.append(f"{item_name}x{qty}")
                    if item_names:
                        reward_report.append(f"  🎁 首功奖励: {', '.join(item_names)}")
        
        if updated_players:
            await self.db.update_players_in_transaction(updated_players)
        
        top_contributors = [{"user_name": p["user_name"], "damage": p["total_damage"]} for p in participants[:5]]
        await self.db.log_boss_kill(boss_instance.boss_id, boss_template.name, top_contributors)
        
        await self.db.clear_boss_data(boss_instance.boss_id)
        
        cooldown_minutes = boss_template.cooldown_minutes
        cooldown_hours = cooldown_minutes // 60
        reward_report.append(f"\n⏰ 此Boss将在 {cooldown_hours} 小时后重新刷新")
        
        if self._broadcast_callback:
            broadcast_msg = self._build_broadcast_message(boss_template.name, top_contributors, cooldown_hours)
            await self._broadcast_callback(broadcast_msg)
        
        return "\n".join(reward_report)

    def _build_broadcast_message(self, boss_name: str, top_contributors: list, cooldown_hours: int) -> str:
        lines = [f"📢 世界Boss【{boss_name}】已被击杀！", ""]
        lines.append("🏆 功勋榜：")
        rank_icons = ["🥇", "🥈", "🥉", "4.", "5."]
        for i, c in enumerate(top_contributors[:5]):
            icon = rank_icons[i] if i < len(rank_icons) else f"{i+1}."
            lines.append(f"  {icon} {c['user_name']} - {c['damage']}伤害")
        lines.append(f"\n⏰ Boss将在 {cooldown_hours} 小时后重新刷新")
        return "\n".join(lines)

    def player_vs_monster(self, player: Player, monster) -> Tuple[bool, List[str], Player]:
        p_clone = player.clone()
        p_stats = p_clone.get_combat_stats(self.config_manager) # 获取最终战斗属性
        monster_hp = monster.hp

        total_damage_dealt = 0
        total_damage_taken = 0
        turn = 0

        while p_clone.hp > 1 and monster_hp > 0:
            turn += 1
            damage_to_monster = max(1, p_stats['attack'] - monster.defense)
            monster_hp -= damage_to_monster
            total_damage_dealt += damage_to_monster

            if monster_hp <= 0:
                break

            damage_to_player = max(1, monster.attack - p_stats['defense'])
            p_clone.hp -= damage_to_player
            total_damage_taken += damage_to_player

        if p_clone.hp < 1:
            p_clone.hp = 1

        victory = monster_hp <= 0

        combat_summary = [f"你遭遇了【{monster.name}】！", "……激战过后……"]
        if victory:
            combat_summary.append("✓ 你获得了胜利！")
        else:
            combat_summary.append("✗ 你不敌对手，力竭倒下！")

        combat_summary.append(f"- 战斗历时: {turn}回合")
        combat_summary.append(f"- 总计伤害: {total_damage_dealt}点")
        combat_summary.append(f"- 承受伤害: {total_damage_taken}点")

        return victory, combat_summary, p_clone

    def player_vs_player(self, attacker: Player, defender: Player, attacker_name: Optional[str], defender_name: Optional[str]) -> Tuple[Optional[Player], Optional[Player], List[str]]:
        p1 = attacker.clone()
        p2 = defender.clone()
        
        p1_stats = p1.get_combat_stats(self.config_manager)
        p2_stats = p2.get_combat_stats(self.config_manager)

        p1_display = attacker_name or attacker.user_id[-4:]
        p2_display = defender_name or defender.user_id[-4:]

        p1_damage_dealt = 0
        p2_damage_dealt = 0
        turn = 0
        max_turns = 30

        while p1.hp > 1 and p2.hp > 1 and turn < max_turns:
            turn += 1
            damage_to_p2 = max(1, p1_stats['attack'] - p2_stats['defense'])
            p2.hp -= damage_to_p2
            p1_damage_dealt += damage_to_p2
            if p2.hp <= 1:
                p2.hp = 1
                break

            damage_to_p1 = max(1, p2_stats['attack'] - p1_stats['defense'])
            p1.hp -= damage_to_p1
            p2_damage_dealt += damage_to_p1
            if p1.hp <= 1:
                p1.hp = 1
                break

        combat_summary = [f"⚔️【切磋】{p1_display} vs {p2_display}", "……一番激斗……"]

        winner = None
        winner_display = ""
        if p1.hp <= 1:
            winner = defender
            winner_display = p2_display
            combat_summary.append(f"🏆 {winner_display} 技高一筹，获得了胜利！")
        elif p2.hp <= 1:
            winner = attacker
            winner_display = p1_display
            combat_summary.append(f"🏆 {winner_display} 技高一筹，获得了胜利！")
        else:
            combat_summary.append("平【平局】双方大战三十回合，未分胜负！")

        combat_summary.append(f"\n--- {p1_display} 战报 ---")
        combat_summary.append(f"- 总计伤害: {p1_damage_dealt}点")
        combat_summary.append(f"- 承受伤害: {p2_damage_dealt}点")
        combat_summary.append(f"- 剩余生命: {p1.hp}/{p1.max_hp}")

        combat_summary.append(f"\n--- {p2_display} 战报 ---")
        combat_summary.append(f"- 总计伤害: {p2_damage_dealt}点")
        combat_summary.append(f"- 承受伤害: {p1_damage_dealt}点")
        combat_summary.append(f"- 剩余生命: {p2.hp}/{p2.max_hp}")

        if winner == attacker:
            return attacker, defender, combat_summary
        elif winner == defender:
            return defender, attacker, combat_summary
        else:
            return None, None, combat_summary