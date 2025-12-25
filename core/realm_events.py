# core/realm_events.py
"""秘境事件生成和处理模块"""
import random
from typing import Dict, Any, List, Tuple, Optional
from ..models import FloorEvent, Player
from ..config_manager import ConfigManager

class EventGenerator:
    """事件生成器工厂类"""
    
    # 秘境类型对应的事件权重
    REALM_TYPE_WEIGHTS = {
        "trial": {  # 试炼之地 - 平衡
            "monster": 0.35,
            "treasure": 0.20,
            "trap": 0.10,
            "choice": 0.15,
            "blessing": 0.08,
            "merchant": 0.05,
            "elite": 0.05,
            "mystery": 0.02,
        },
        "treasure": {  # 宝藏密室 - 宝箱多但有陷阱
            "monster": 0.15,
            "treasure": 0.40,
            "trap": 0.20,
            "choice": 0.10,
            "blessing": 0.05,
            "merchant": 0.05,
            "elite": 0.03,
            "mystery": 0.02,
        },
        "beast": {  # 妖兽巢穴 - 战斗密集
            "monster": 0.50,
            "treasure": 0.10,
            "trap": 0.05,
            "choice": 0.10,
            "blessing": 0.05,
            "merchant": 0.03,
            "elite": 0.15,
            "mystery": 0.02,
        },
        "ruin": {  # 古老遗迹 - 神秘事件多
            "monster": 0.20,
            "treasure": 0.25,
            "trap": 0.10,
            "choice": 0.15,
            "blessing": 0.10,
            "merchant": 0.05,
            "elite": 0.05,
            "mystery": 0.10,
        },
        "ghost": {  # 幽冥鬼域 - 危险但奖励丰厚
            "monster": 0.35,
            "treasure": 0.15,
            "trap": 0.15,
            "choice": 0.10,
            "blessing": 0.10,  # 可能是诅咒
            "merchant": 0.03,
            "elite": 0.10,
            "mystery": 0.02,
        }
    }
    
    @staticmethod
    def generate_event(realm_type: str, floor_num: int, total_floors: int, 
                      player_level: int, config_manager: ConfigManager) -> FloorEvent:
        """
        根据秘境类型、楼层位置生成合适的事件
        
        Args:
            realm_type: 秘境类型
            floor_num: 当前楼层（1-based）
            total_floors: 总楼层数
            player_level: 玩家等级
            config_manager: 配置管理器
        """
        # 获取权重配置
        weights = EventGenerator.REALM_TYPE_WEIGHTS.get(realm_type, EventGenerator.REALM_TYPE_WEIGHTS["trial"])
        
        # 前期降低陷阱概率，后期增加精英怪概率
        progress = floor_num / total_floors
        adjusted_weights = weights.copy()
        
        if progress < 0.3:  # 前30%楼层
            adjusted_weights["trap"] *= 0.5
            adjusted_weights["elite"] *= 0.5
            adjusted_weights["treasure"] *= 1.2
        elif progress > 0.7:  # 后30%楼层
            adjusted_weights["elite"] *= 1.5
            adjusted_weights["monster"] *= 1.2
        
        # 归一化权重
        total_weight = sum(adjusted_weights.values())
        normalized_weights = {k: v/total_weight for k, v in adjusted_weights.items()}
        
        # 随机选择事件类型
        event_types = list(normalized_weights.keys())
        event_weights = list(normalized_weights.values())
        event_type = random.choices(event_types, weights=event_weights, k=1)[0]
        
        # 生成对应事件
        if event_type == "monster":
            return EventGenerator._create_monster_event(config_manager, player_level)
        elif event_type == "treasure":
            return EventGenerator._create_treasure_event(player_level)
        elif event_type == "trap":
            return EventGenerator._create_trap_event(player_level)
        elif event_type == "choice":
            return EventGenerator._create_choice_event(player_level, realm_type)
        elif event_type == "blessing":
            return EventGenerator._create_blessing_event(player_level, realm_type)
        elif event_type == "merchant":
            return EventGenerator._create_merchant_event(player_level, config_manager)
        elif event_type == "elite":
            return EventGenerator._create_elite_event(config_manager, player_level)
        elif event_type == "mystery":
            return EventGenerator._create_mystery_event(player_level)
        else:
            return EventGenerator._create_treasure_event(player_level)
    
    @staticmethod
    def _create_monster_event(config_manager: ConfigManager, player_level: int) -> FloorEvent:
        """创建普通怪物事件"""
        monster_pool = list(config_manager.monster_data.keys())
        if not monster_pool:
            return EventGenerator._create_treasure_event(player_level)
        
        monster_id = random.choice(monster_pool)
        return FloorEvent(
            type="monster",
            data={"id": monster_id},
            description="前方传来妖兽的咆哮声..."
        )
    
    @staticmethod
    def _create_elite_event(config_manager: ConfigManager, player_level: int) -> FloorEvent:
        """创建精英怪物事件 - 奖励更好"""
        monster_pool = list(config_manager.monster_data.keys())
        if not monster_pool:
            return EventGenerator._create_treasure_event(player_level)
        
        monster_id = random.choice(monster_pool)
        return FloorEvent(
            type="elite",
            data={"id": monster_id, "reward_multiplier": 1.5},
            description="⚠️ 你感受到强大的气息，这里有一只精英妖兽！"
        )
    
    @staticmethod
    def _create_treasure_event(player_level: int) -> FloorEvent:
        """创建宝箱事件"""
        base_gold = random.randint(80, 200)
        gold_reward = int(base_gold * (1 + player_level * 0.5))
        
        descriptions = [
            "你发现了一个散发着灵光的宝箱！",
            "墙角处有一个古旧的木箱...",
            "地面上遗落着一个储物袋。"
        ]
        
        return FloorEvent(
            type="treasure",
            data={"rewards": {"gold": gold_reward}},
            description=random.choice(descriptions)
        )
    
    @staticmethod
    def _create_trap_event(player_level: int) -> FloorEvent:
        """创建陷阱事件"""
        trap_types = [
            {
                "name": "毒雾陷阱",
                "desc": "💀 你触发了一个毒雾陷阱！",
                "damage_percent": random.uniform(0.15, 0.30),
                "gold_loss": random.randint(50, 150) * (1 + player_level)
            },
            {
                "name": "落石陷阱",
                "desc": "💀 天花板突然坍塌，巨石砸落！",
                "damage_percent": random.uniform(0.20, 0.35),
                "gold_loss": 0
            },
            {
                "name": "灵力吸收阵",
                "desc": "💀 你踏入了一个灵力吸收法阵！",
                "damage_percent": random.uniform(0.10, 0.20),
                "gold_loss": random.randint(100, 300) * (1 + player_level)
            }
        ]
        
        trap = random.choice(trap_types)
        return FloorEvent(
            type="trap",
            data={
                "name": trap["name"],
                "damage_percent": trap["damage_percent"],
                "gold_loss": int(trap["gold_loss"])
            },
            description=trap["desc"]
        )
    
    @staticmethod
    def _create_choice_event(player_level: int, realm_type: str) -> FloorEvent:
        """创建选择事件 - 分岔路口"""
        choice_templates = [
            {
                "desc": "🔱 前方出现了三条岔路，你该如何选择？",
                "choices": [
                    {
                        "id": 1,
                        "text": "左路 - 隐约听到战斗声（高风险高回报）",
                        "result": {"type": "combat_intense", "risk": "high", "reward_mult": 1.8}
                    },
                    {
                        "id": 2,
                        "text": "中路 - 平坦宽阔的大道（平衡）",
                        "result": {"type": "balanced", "risk": "medium", "reward_mult": 1.0}
                    },
                    {
                        "id": 3,
                        "text": "右路 - 幽静的小径（低风险低回报）",
                        "result": {"type": "safe", "risk": "low", "reward_mult": 0.6}
                    }
                ]
            },
            {
                "desc": "🎁 你发现一个闪光的华丽宝箱，但周围有可疑的符文...",
                "choices": [
                    {
                        "id": 1,
                        "text": "直接打开（可能有陷阱或大奖）",
                        "result": {"type": "risky_chest", "trap_chance": 0.4, "reward_mult": 2.0}
                    },
                    {
                        "id": 2,
                        "text": "小心检查后再开（安全但可能减少奖励）",
                        "result": {"type": "safe_chest", "trap_chance": 0.1, "reward_mult": 1.2}
                    },
                    {
                        "id": 3,
                        "text": "放弃这个宝箱，继续前进",
                        "result": {"type": "skip", "reward_mult": 0}
                    }
                ]
            }
        ]
        
        template = random.choice(choice_templates)
        return FloorEvent(
            type="choice",
            data={"player_level": player_level},
            choices=template["choices"],
            description=template["desc"],
            requires_choice=True
        )
    
    @staticmethod
    def _create_blessing_event(player_level: int, realm_type: str) -> FloorEvent:
        """创建祝福/诅咒事件"""
        # 幽冥鬼域更容易触发诅咒
        curse_chance = 0.3 if realm_type == "ghost" else 0.2
        is_curse = random.random() < curse_chance
        
        if is_curse:
            curses = [
                {
                    "name": "虚弱诅咒",
                    "desc": "😈 你触碰了邪恶的雕像，感到力量被削弱...",
                    "effect": {"type": "attack_debuff", "value": -5, "duration": 3}
                },
                {
                    "name": "破甲诅咒",
                    "desc": "😈 黑暗能量侵蚀了你的防御...",
                    "effect": {"type": "defense_debuff", "value": -3, "duration": 3}
                }
            ]
            curse = random.choice(curses)
            return FloorEvent(
                type="blessing",
                data={
                    "is_blessing": False,
                    "name": curse["name"],
                    "effect": curse["effect"]
                },
                description=curse["desc"]
            )
        else:
            blessings = [
                {
                    "name": "力量祝福",
                    "desc": "✨ 你在古老的祭坛前祈祷，获得了力量的祝福！",
                    "effect": {"type": "attack_buff", "value": 8, "duration": 5}
                },
                {
                    "name": "守护祝福",
                    "desc": "✨ 神圣的光芒笼罩着你，防御力大幅提升！",
                    "effect": {"type": "defense_buff", "value": 5, "duration": 5}
                },
                {
                    "name": "生命祝福",
                    "desc": "✨ 温暖的能量流淌全身，生命值恢复了！",
                    "effect": {"type": "heal", "percent": 0.3}
                }
            ]
            blessing = random.choice(blessings)
            return FloorEvent(
                type="blessing",
                data={
                    "is_blessing": True,
                    "name": blessing["name"],
                    "effect": blessing["effect"]
                },
                description=blessing["desc"]
            )
    
    @staticmethod
    def _create_merchant_event(player_level: int, config_manager: ConfigManager) -> FloorEvent:
        """创建商人事件"""
        # 商人提供的商品
        offerings = []
        
        # 1. 恢复药水
        heal_cost = 100 + player_level * 30
        offerings.append({
            "id": "heal_potion",
            "name": "疗伤丹药",
            "desc": f"恢复30%生命值",
            "cost": heal_cost,
            "effect": {"type": "heal", "percent": 0.3}
        })
        
        # 2. 临时buff药水
        buff_cost = 150 + player_level * 40
        offerings.append({
            "id": "power_potion",
            "name": "爆发丹药",
            "desc": f"攻击力+10，持续3场战斗",
            "cost": buff_cost,
            "effect": {"type": "attack_buff", "value": 10, "duration": 3}
        })
        
        # 3. 随机选择一个道具出售（如果有道具数据）
        if config_manager.item_data:
            available_items = [item for item in config_manager.item_data.values() 
                             if item.rank in ["凡品", "珍品"] and item.type != "功法"]
            if available_items:
                random_item = random.choice(available_items)
                item_cost = int(random_item.price * 0.8)  # 商人打8折
                offerings.append({
                    "id": f"item_{random_item.id}",
                    "name": random_item.name,
                    "desc": random_item.description,
                    "cost": item_cost,
                    "effect": {"type": "item", "item_id": random_item.id}
                })
        
        return FloorEvent(
            type="merchant",
            data={"offerings": offerings},
            description="🧙 你遇到了一位神秘的商人...",
            requires_choice=True
        )
    
    @staticmethod
    def _create_mystery_event(player_level: int) -> FloorEvent:
        """创建神秘事件 - 随机好坏"""
        mystery_events = [
            {
                "desc": "🌟 你发现了一处灵泉，泉水散发着浓郁的灵气...",
                "good": True,
                "result": {"type": "heal_and_buff", "heal_percent": 0.5, "buff": {"type": "attack_buff", "value": 5, "duration": 3}}
            },
            {
                "desc": "💎 墙壁上镶嵌着一颗发光的宝石...",
                "good": True,
                "result": {"type": "gold_bonus", "gold": random.randint(200, 500) * (1 + player_level)}
            },
            {
                "desc": "⚡ 你不小心触发了一个传送阵，被传送到了未知区域...",
                "good": False,
                "result": {"type": "damage", "damage_percent": 0.15}
            },
            {
                "desc": "🕸️ 你走进了一片蛛网密布的区域...",
                "good": False,
                "result": {"type": "debuff", "effect": {"type": "defense_debuff", "value": -3, "duration": 2}}
            }
        ]
        
        event = random.choice(mystery_events)
        return FloorEvent(
            type="mystery",
            data={"result": event["result"]},
            description=event["desc"]
        )


class EventProcessor:
    """事件处理器 - 处理各种事件的结果"""
    
    @staticmethod
    def process_choice_result(choice_data: Dict[str, Any], choice_id: int, 
                            player: Player, player_level: int) -> Tuple[List[str], Player, Dict[str, int]]:
        """处理玩家选择的结果"""
        result = choice_data.get("result", {})
        result_type = result.get("type", "")
        log = []
        gained_items = {}
        p = player.clone()
        
        if result_type == "combat_intense":
            # 高风险路径 - 后续会触发精英怪物
            log.append("你选择了危险的道路，前方将面临激烈战斗！")
        elif result_type == "balanced":
            log.append("你选择了平衡的道路，稳步前进。")
        elif result_type == "safe":
            log.append("你选择了安全的道路，虽然奖励较少但很稳妥。")
            # 直接给予少量奖励
            safe_gold = random.randint(50, 100) * (1 + player_level)
            p.gold += safe_gold
            log.append(f"你在路上捡到了 {safe_gold} 灵石。")
        elif result_type == "risky_chest":
            trap_chance = result.get("trap_chance", 0.4)
            reward_mult = result.get("reward_mult", 2.0)
            if random.random() < trap_chance:
                # 触发陷阱
                damage = int(p.max_hp * 0.25)
                p.hp = max(1, p.hp - damage)
                log.append(f"💀 宝箱是个陷阱！你受到了 {damage} 点伤害。")
            else:
                # 获得大奖
                gold = int(random.randint(150, 300) * (1 + player_level) * reward_mult)
                p.gold += gold
                log.append(f"🎉 宝箱中装满了财宝！你获得了 {gold} 灵石！")
        elif result_type == "safe_chest":
            gold = int(random.randint(100, 200) * (1 + player_level) * 1.2)
            p.gold += gold
            log.append(f"你小心翼翼地打开宝箱，获得了 {gold} 灵石。")
        elif result_type == "skip":
            log.append("你决定不冒险，继续前进。")
        
        return log, p, gained_items
    
    @staticmethod
    def process_merchant_purchase(offering: Dict[str, Any], player: Player) -> Tuple[bool, str, Player]:
        """处理商人购买"""
        p = player.clone()
        cost = offering.get("cost", 0)
        
        if p.gold < cost:
            return False, f"你的灵石不足，需要 {cost} 灵石。", p
        
        p.gold -= cost
        effect = offering.get("effect", {})
        effect_type = effect.get("type", "")
        
        msg = f"你花费 {cost} 灵石购买了【{offering['name']}】。\n"
        
        if effect_type == "heal":
            heal_amount = int(p.max_hp * effect.get("percent", 0.3))
            p.hp = min(p.max_hp, p.hp + heal_amount)
            msg += f"生命值恢复了 {heal_amount} 点！"
        elif effect_type == "attack_buff":
            p.add_buff("attack_buff", effect.get("value", 10), effect.get("duration", 3))
            msg += f"攻击力提升 {effect.get('value', 10)} 点，持续 {effect.get('duration', 3)} 场战斗！"
        elif effect_type == "item":
            # 物品会在外部处理
            msg += "物品已添加到背包！"
        
        return True, msg, p
