# core/realm_manager.py
import random
import time
import json
from typing import Tuple, Dict, Any, List, Optional

from astrbot.api import logger, AstrBotConfig
from ..models import Player, FloorEvent, RealmInstance
from ..config_manager import ConfigManager
from ..data import DataBase
from .combat_manager import BattleManager, MonsterGenerator
from .realm_events import EventGenerator, EventProcessor

class RealmGenerator:
    """秘境生成器"""
    
    # 秘境类型配置
    REALM_TYPES = {
        "trial": {"name": "试炼之地", "desc": "平衡型秘境，适合稳定探索"},
        "treasure": {"name": "宝藏密室", "desc": "宝箱丰富，但陷阱众多"},
        "beast": {"name": "妖兽巢穴", "desc": "战斗密集，经验丰富"},
        "ruin": {"name": "古老遗迹", "desc": "神秘事件多，可能获得珍稀奖励"},
        "ghost": {"name": "幽冥鬼域", "desc": "极度危险，奖励丰厚"}
    }
    
    # 难度配置
    DIFFICULTIES = {
        "normal": {"name": "普通", "cost_mult": 1.0, "reward_mult": 1.0},
        "hard": {"name": "困难", "cost_mult": 1.5, "reward_mult": 2.0},
        "hell": {"name": "地狱", "cost_mult": 2.0, "reward_mult": 3.0}
    }
    
    @staticmethod
    def generate_for_player(player: Player, config: AstrBotConfig, config_manager: ConfigManager,
                          realm_type: str = "trial", difficulty: str = "normal") -> Optional[RealmInstance]:
        """
        为玩家生成秘境
        
        Args:
            player: 玩家对象
            config: 配置
            config_manager: 配置管理器
            realm_type: 秘境类型 (trial/treasure/beast/ruin/ghost)
            difficulty: 难度 (normal/hard/hell)
        """
        level_index = player.level_index

        # 验证秘境类型和难度
        if realm_type not in RealmGenerator.REALM_TYPES:
            realm_type = "trial"
        if difficulty not in RealmGenerator.DIFFICULTIES:
            difficulty = "normal"

        # 计算总楼层数
        base_floors = config["REALM_RULES"]["REALM_BASE_FLOORS"]
        floors_per_level = config["REALM_RULES"]["REALM_FLOORS_PER_LEVEL_DIVISOR"]
        total_floors = base_floors + (level_index // floors_per_level)

        monster_pool = list(config_manager.monster_data.keys())
        boss_pool = list(config_manager.boss_data.keys())

        if not monster_pool or not boss_pool:
            logger.error("秘境生成失败：怪物池或Boss池为空，请检check monsters.json 和 bosses.json。")
            return None

        floor_events: List[FloorEvent] = []

        # 使用新的事件生成器生成各楼层事件
        for floor_num in range(1, total_floors):
            event = EventGenerator.generate_event(
                realm_type=realm_type,
                floor_num=floor_num,
                total_floors=total_floors,
                player_level=level_index,
                config_manager=config_manager
            )
            floor_events.append(event)

        # 最后一层必定是Boss
        final_boss_id = random.choice(boss_pool)
        boss_event = FloorEvent(
            type="boss",
            data={"id": final_boss_id},
            description="⚔️ 前方传来强大的威压，最终Boss就在眼前！"
        )
        floor_events.append(boss_event)

        realm_id = f"{realm_type}_{difficulty}_{player.level_index}_{int(time.time())}"

        # 创建秘境实例
        return RealmInstance(
            id=realm_id,
            total_floors=total_floors,
            floors=floor_events,
            realm_type=realm_type,
            difficulty=difficulty,
            theme_modifiers={
                "reward_multiplier": RealmGenerator.DIFFICULTIES[difficulty]["reward_mult"]
            }
        )

class RealmManager:
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.battle_logic = BattleManager(db, config, config_manager)

    async def start_session(self, player: Player, cmd_realm_advance: str, 
                          realm_type: str = "trial", difficulty: str = "normal") -> Tuple[bool, str, Player]:
        """
        开启秘境探索
        
        Args:
            player: 玩家
            cmd_realm_advance: 前进指令名称
            realm_type: 秘境类型
            difficulty: 难度
        """
        p = player.clone()
        if p.realm_id is not None:
             current_realm_instance = p.get_realm_instance()
             if current_realm_instance:
                 type_name = RealmGenerator.REALM_TYPES.get(current_realm_instance.realm_type, {}).get("name", "未知秘境")
                 current_realm_name = f"{type_name}·{p.get_level(self.config_manager)}修士的{current_realm_instance.difficulty}试炼"
             else:
                 current_realm_name = "未知的秘境"
             return False, f"你已身在【{current_realm_name}】之中，无法分心他顾。", p

        # 根据难度计算消耗
        base_cost = 50 + (p.level_index * 25)
        difficulty_mult = RealmGenerator.DIFFICULTIES.get(difficulty, {}).get("cost_mult", 1.0)
        cost = int(base_cost * difficulty_mult)

        if p.gold < cost:
            return False, f"本次历练需要 {cost} 灵石作为盘缠，你的灵石不足。", p

        realm_instance = RealmGenerator.generate_for_player(p, self.config, self.config_manager, realm_type, difficulty)
        if not realm_instance:
             return False, "天机混乱，秘境生成失败，请稍后再试。", p

        p.gold -= cost
        p.realm_id = realm_instance.id
        p.realm_floor = 0
        p.set_realm_instance(realm_instance)
        p.realm_pending_choice = None  # 清空待选择事件

        # 构建秘境名称
        type_info = RealmGenerator.REALM_TYPES.get(realm_type, {})
        difficulty_info = RealmGenerator.DIFFICULTIES.get(difficulty, {})
        realm_name = f"{type_info.get('name', '未知秘境')}·{p.get_level(self.config_manager)}修士的{difficulty_info.get('name', '普通')}试炼"

        msg = (f"你消耗了 {cost} 灵石，开启了一场与你修为匹配的试炼。\n"
               f"📜 秘境：【{realm_name}】\n"
               f"   类型：{type_info.get('desc', '')}\n"
               f"   难度：{difficulty_info.get('name', '普通')}（奖励倍率×{difficulty_info.get('reward_mult', 1.0)}）\n"
               f"   楼层：共 {realm_instance.total_floors} 层\n\n"
               f"使用「{cmd_realm_advance}」指令向前探索。")
        return True, msg, p

    async def advance_session(self, player: Player) -> Tuple[bool, str, Player, Dict[str, int]]:
        """推进秘境探索"""
        p = player.clone()
        realm_instance = p.get_realm_instance()

        if not p.realm_id or not realm_instance:
            return False, "你不在任何秘境中。", p, {}

        # 检查是否有待选择的事件
        if p.realm_pending_choice:
            return False, "当前有事件需要你做出选择！请使用「选择 数字」指令。", p, {}

        p.realm_floor += 1
        current_floor_index = p.realm_floor - 1

        if not (0 <= current_floor_index < len(realm_instance.floors)):
            p.realm_id = None
            p.realm_floor = 0
            p.set_realm_instance(None)
            p.realm_pending_choice = None
            return False, "秘境探索数据异常，已将你传送出来。", p, {}

        event = realm_instance.floors[current_floor_index]
        event_log = [f"--- 第 {p.realm_floor}/{realm_instance.total_floors} 层 ---"]
        
        # 添加事件描述
        if event.description:
            event_log.append(event.description)

        gained_items = {}
        victory = True
        reward_mult = realm_instance.theme_modifiers.get("reward_multiplier", 1.0)
        
        # 根据事件类型调用不同的处理器
        if event.type == "monster":
            victory, log, p, gained_items = await self._handle_monster_event(p, event, p.level_index, reward_mult)
            event_log.extend(log)
        elif event.type == "boss":
            victory, log, p, gained_items = await self._handle_monster_event(p, event, p.level_index, reward_mult)
            event_log.extend(log)
        elif event.type == "elite":
            victory, log, p, gained_items = await self._handle_elite_event(p, event, p.level_index, reward_mult)
            event_log.extend(log)
        elif event.type == "treasure":
            log, p, gained_items = self._handle_treasure_event(p, event, reward_mult)
            event_log.extend(log)
        elif event.type == "trap":
            log, p = self._handle_trap_event(p, event)
            event_log.extend(log)
        elif event.type == "blessing":
            log, p = self._handle_blessing_event(p, event)
            event_log.extend(log)
        elif event.type == "choice":
            # 选择事件需要玩家输入
            log, p = self._handle_choice_event_start(p, event)
            event_log.extend(log)
            victory = True  # 不会结束秘境
        elif event.type == "merchant":
            log, p = self._handle_merchant_event_start(p, event)
            event_log.extend(log)
            victory = True
        elif event.type == "mystery":
            log, p = self._handle_mystery_event(p, event, reward_mult)
            event_log.extend(log)
        else:
            event_log.append("此地异常安静，你谨慎地探索着，未发生任何事。")

        # 如果战斗失败，退出秘境
        if not victory:
            p.realm_id = None
            p.realm_floor = 0
            p.set_realm_instance(None)
            p.realm_pending_choice = None

        # 如果完成所有楼层
        if victory and p.realm_id is not None and p.realm_floor >= realm_instance.total_floors:
            type_name = RealmGenerator.REALM_TYPES.get(realm_instance.realm_type, {}).get("name", "未知秘境")
            difficulty_name = RealmGenerator.DIFFICULTIES.get(realm_instance.difficulty, {}).get("name", "普通")
            realm_name = f"{type_name}{difficulty_name}试炼"
            
            # 完成奖励
            completion_bonus = int(200 * (1 + p.level_index) * reward_mult)
            p.gold += completion_bonus
            event_log.append(f"\n 恭喜！你成功探索完了【{realm_name}】的所有区域！")
            event_log.append(f"获得完成奖励：{completion_bonus} 灵石")
            
            p.realm_id = None
            p.realm_floor = 0
            p.set_realm_instance(None)
            p.realm_pending_choice = None
            
        return victory, "\n".join(event_log), p, gained_items

    async def _handle_monster_event(self, p: Player, event: FloorEvent, player_level_index: int, 
                                   reward_mult: float = 1.0) -> Tuple[bool, List[str], Player, Dict[str, int]]:
        """处理普通怪物和Boss事件"""
        monster_template_id = event.data["id"]
        
        if event.type == "boss":
            scaling_factor = self.config["REALM_RULES"].get("REALM_BOSS_SCALING_FACTOR", 1.0)
            enemy = MonsterGenerator.create_boss(monster_template_id, player_level_index, self.config_manager, scaling_factor=scaling_factor)
        else:
            enemy = MonsterGenerator.create_monster(monster_template_id, player_level_index, self.config_manager)

        if not enemy:
            return False, ["怪物生成失败！"], p, {}

        victory, combat_log, p_after_combat = self.battle_logic.player_vs_monster(p, enemy)

        p = p_after_combat
        gained_items = {}
        if victory:
            rewards = enemy.rewards
            # 应用奖励倍率
            p.gold += int(rewards.get('gold', 0) * reward_mult)
            p.experience += int(rewards.get('experience', 0) * reward_mult)
            gained_items = rewards.get('items', {})

            if event.type == "boss":
                 combat_log.append(f"\n 成功击败最终头目！")

        return victory, combat_log, p, gained_items

    async def _handle_elite_event(self, p: Player, event: FloorEvent, player_level_index: int,
                                 reward_mult: float = 1.0) -> Tuple[bool, List[str], Player, Dict[str, int]]:
        """处理精英怪物事件 - 更强但奖励更好"""
        monster_template_id = event.data["id"]
        elite_mult = event.data.get("reward_multiplier", 1.5)
        
        enemy = MonsterGenerator.create_monster(monster_template_id, player_level_index, self.config_manager)
        if not enemy:
            return False, ["怪物生成失败！"], p, {}
        
        # 精英怪物更强
        enemy.hp = int(enemy.hp * 1.3)
        enemy.max_hp = int(enemy.max_hp * 1.3)
        enemy.attack = int(enemy.attack * 1.2)
        enemy.defense = int(enemy.defense * 1.2)

        victory, combat_log, p_after_combat = self.battle_logic.player_vs_monster(p, enemy)
        p = p_after_combat
        gained_items = {}
        
        if victory:
            rewards = enemy.rewards
            # 精英怪物的奖励更高
            p.gold += int(rewards.get('gold', 0) * elite_mult * reward_mult)
            p.experience += int(rewards.get('experience', 0) * elite_mult * reward_mult)
            gained_items = rewards.get('items', {})
            combat_log.append(f"\n 击败精英怪物，获得额外奖励！")

        return victory, combat_log, p, gained_items

    def _handle_treasure_event(self, p: Player, event: FloorEvent, reward_mult: float = 1.0) -> Tuple[List[str], Player, Dict[str, int]]:
        """处理宝箱事件"""
        log = []
        gold_gained = event.data.get("rewards", {}).get("gold", 50)
        # 应用奖励倍率
        gold_gained = int(gold_gained * reward_mult)
        p.gold += gold_gained
        log.append(f" 获得了 {gold_gained} 灵石！")
        return log, p, {}

    def _handle_trap_event(self, p: Player, event: FloorEvent) -> Tuple[List[str], Player]:
        """处理陷阱事件"""
        log = []
        damage_percent = event.data.get("damage_percent", 0.2)
        gold_loss = event.data.get("gold_loss", 0)
        trap_name = event.data.get("name", "陷阱")
        
        # 造成伤害
        damage = int(p.max_hp * damage_percent)
        p.hp = max(1, p.hp - damage)
        log.append(f"受到了 {damage} 点伤害！（当前生命：{p.hp}/{p.max_hp}）")
        
        # 损失灵石
        if gold_loss > 0:
            actual_loss = min(p.gold, gold_loss)
            p.gold -= actual_loss
            if actual_loss > 0:
                log.append(f" 损失了 {actual_loss} 灵石！")
        
        return log, p

    def _handle_blessing_event(self, p: Player, event: FloorEvent) -> Tuple[List[str], Player]:
        """处理祝福/诅咒事件"""
        log = []
        is_blessing = event.data.get("is_blessing", True)
        effect = event.data.get("effect", {})
        name = event.data.get("name", "未知效果")
        
        effect_type = effect.get("type", "")
        
        if effect_type == "heal":
            heal_percent = effect.get("percent", 0.3)
            heal_amount = int(p.max_hp * heal_percent)
            p.hp = min(p.max_hp, p.hp + heal_amount)
            log.append(f" 生命值恢复了 {heal_amount} 点！（当前：{p.hp}/{p.max_hp}）")
        elif "buff" in effect_type or "debuff" in effect_type:
            value = effect.get("value", 0)
            duration = effect.get("duration", 3)
            if "attack" in effect_type:
                buff_type = "attack_buff" if value > 0 else "attack_debuff"
                p.add_buff(buff_type, abs(value), duration)
                if value > 0:
                    log.append(f" 获得【{name}】：攻击力+{value}，持续{duration}场战斗")
                else:
                    log.append(f" 受到【{name}】：攻击力{value}，持续{duration}场战斗")
            elif "defense" in effect_type:
                buff_type = "defense_buff" if value > 0 else "defense_debuff"
                p.add_buff(buff_type, abs(value), duration)
                if value > 0:
                    log.append(f" 获得【{name}】：防御力+{value}，持续{duration}场战斗")
                else:
                    log.append(f" 受到【{name}】：防御力{value}，持续{duration}场战斗")
        
        return log, p

    def _handle_choice_event_start(self, p: Player, event: FloorEvent) -> Tuple[List[str], Player]:
        """处理选择事件的开始 - 显示选项"""
        log = []
        choices = event.choices or []
        
        if not choices:
            log.append("事件异常，自动跳过。")
            return log, p
        
        log.append("\n请选择你的行动：")
        for choice in choices:
            log.append(f"  {choice['id']}. {choice['text']}")
        log.append("\n使用「选择 数字」指令做出选择（例如：选择 1）")
        
        # 保存待选择事件到玩家数据
        p.realm_pending_choice = json.dumps({"event_data": event.data, "choices": choices})
        
        return log, p

    def _handle_merchant_event_start(self, p: Player, event: FloorEvent) -> Tuple[List[str], Player]:
        """处理商人事件的开始 - 显示商品"""
        log = []
        offerings = event.data.get("offerings", [])
        
        if not offerings:
            log.append("商人没有商品出售，继续前进...")
            return log, p
        
        log.append(f"\n当前灵石：{p.gold}")
        log.append("商人的商品：")
        for i, offer in enumerate(offerings, 1):
            log.append(f"  {i}. 【{offer['name']}】- {offer['desc']} - {offer['cost']} 灵石")
        log.append(f"  {len(offerings) + 1}. 不购买，继续前进")
        log.append("\n使用「选择 数字」指令购买或离开")
        
        # 保存商人事件
        p.realm_pending_choice = json.dumps({"type": "merchant", "offerings": offerings})
        
        return log, p

    def _handle_mystery_event(self, p: Player, event: FloorEvent, reward_mult: float = 1.0) -> Tuple[List[str], Player]:
        """处理神秘事件"""
        log = []
        result = event.data.get("result", {})
        result_type = result.get("type", "")
        
        if result_type == "heal_and_buff":
            # 治疗并加buff
            heal_percent = result.get("heal_percent", 0.5)
            heal_amount = int(p.max_hp * heal_percent)
            p.hp = min(p.max_hp, p.hp + heal_amount)
            log.append(f" 沐浴在灵泉中，生命值恢复了 {heal_amount} 点！")
            
            buff_data = result.get("buff", {})
            if buff_data:
                p.add_buff(buff_data.get("type", "attack_buff"), buff_data.get("value", 5), buff_data.get("duration", 3))
                log.append(f" 并且获得了力量提升！")
        
        elif result_type == "gold_bonus":
            gold = int(result.get("gold", 300) * reward_mult)
            p.gold += gold
            log.append(f" 获得了 {gold} 灵石！")
        
        elif result_type == "damage":
            damage_percent = result.get("damage_percent", 0.15)
            damage = int(p.max_hp * damage_percent)
            p.hp = max(1, p.hp - damage)
            log.append(f" 受到了 {damage} 点伤害！（当前：{p.hp}/{p.max_hp}）")
        
        elif result_type == "debuff":
            effect = result.get("effect", {})
            p.add_buff(effect.get("type", "defense_debuff"), effect.get("value", 3), effect.get("duration", 2))
            log.append(f" 你被困住了，属性暂时降低！")
        
        return log, p

    async def handle_player_choice(self, player: Player, choice_num: int) -> Tuple[bool, str, Player, Dict[str, int]]:
        """
        处理玩家在秘境中的选择
        
        Args:
            player: 玩家对象
            choice_num: 玩家选择的编号
            
        Returns:
            (success, message, updated_player, gained_items)
        """
        p = player.clone()
        
        if not p.realm_pending_choice:
            return False, "当前没有需要选择的事件。", p, {}
        
        try:
            choice_data = json.loads(p.realm_pending_choice)
        except (json.JSONDecodeError, TypeError):
            p.realm_pending_choice = None
            return False, "选择数据异常，已清除。", p, {}
        
        choice_type = choice_data.get("type", "choice")
        
        if choice_type == "merchant":
            # 商人事件
            offerings = choice_data.get("offerings", [])
            if choice_num == len(offerings) + 1:
                # 选择不购买
                p.realm_pending_choice = None
                return True, "你决定不购买任何东西，继续前进。", p, {}
            elif 1 <= choice_num <= len(offerings):
                offering = offerings[choice_num - 1]
                success, msg, p = EventProcessor.process_merchant_purchase(offering, p)
                
                # 如果购买了物品类型，需要添加到背包
                gained_items = {}
                if success and offering.get("effect", {}).get("type") == "item":
                    item_id = offering["effect"]["item_id"]
                    gained_items[item_id] = 1
                
                p.realm_pending_choice = None
                return success, msg, p, gained_items
            else:
                return False, f"无效的选择，请选择 1-{len(offerings) + 1}。", p, {}
        
        else:
            # 选择事件（分岔路口等）
            choices = choice_data.get("choices", [])
            event_data = choice_data.get("event_data", {})
            
            # 查找选择的选项
            selected_choice = None
            for choice in choices:
                if choice.get("id") == choice_num:
                    selected_choice = choice
                    break
            
            if not selected_choice:
                return False, f"无效的选择，请选择 {', '.join([str(c['id']) for c in choices])} 中的一个。", p, {}
            
            # 处理选择结果
            realm_instance = p.get_realm_instance()
            reward_mult = 1.0
            if realm_instance:
                reward_mult = realm_instance.theme_modifiers.get("reward_multiplier", 1.0)
            
            log, p, gained_items = EventProcessor.process_choice_result(
                selected_choice, choice_num, p, p.level_index
            )
            
            p.realm_pending_choice = None
            return True, "\n".join(log), p, gained_items
