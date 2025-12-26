# models.py

import json
from dataclasses import dataclass, field, replace, asdict
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .config_manager import ConfigManager

@dataclass
class Item:
    """物品数据模型"""

    id: str
    name: str
    type: str
    rank: str
    description: str
    price: int
    effect: Optional[Dict[str, Any]] = None
    subtype: Optional[str] = None  # 装备子类型，如'武器', '防具'
    equip_effects: Optional[Dict[str, Any]] = None  # 装备属性加成
    skill_effects: Optional[Dict[str, Any]] = None  # 功法永久属性加成
    buff_effect: Optional[Dict[str, Any]] = None  # 丹药buff效果

@dataclass
class FloorEvent:
    """秘境层级事件数据模型"""

    type: str  # 事件类型：monster, boss, treasure, trap, choice, blessing, merchant, elite, mystery, environment
    data: Dict[str, Any] = field(default_factory=dict)
    choices: Optional[List[Dict[str, Any]]] = None  # 玩家可选择的选项，每个选项包含 {"id": int, "text": str, "result": dict}
    description: str = ""  # 事件描述文本
    requires_choice: bool = False  # 是否需要玩家做出选择

@dataclass
class RealmInstance:
    """秘境实例数据模型"""

    id: str
    total_floors: int
    floors: List[FloorEvent]
    realm_type: str = "trial"  # 秘境类型：trial(试炼), treasure(宝藏), beast(妖兽), ruin(遗迹), ghost(幽冥)
    difficulty: str = "normal"  # 难度：normal(普通), hard(困难), hell(地狱)
    theme_modifiers: Dict[str, Any] = field(default_factory=dict)  # 主题修正值

@dataclass
class Player:
    """玩家数据模型"""

    user_id: str
    level_index: int = 0
    spiritual_root: str = "未知"
    experience: int = 0
    gold: int = 0
    last_check_in: float = 0.0
    state: str = "空闲"
    state_start_time: float = 0.0
    sect_id: Optional[int] = None
    sect_name: Optional[str] = None
    hp: int = 100
    max_hp: int = 100
    attack: int = 10
    defense: int = 5
    realm_id: Optional[str] = None
    realm_floor: int = 0
    realm_data: Optional[str] = None
    realm_pending_choice: Optional[str] = None  # JSON存储待选择的事件数据
    
    # 装备槽位
    equipped_weapon: Optional[str] = None
    equipped_armor: Optional[str] = None
    equipped_accessory: Optional[str] = None
    
    # v2.3.0 新增字段
    learned_skills: str = "[]"  # JSON存储已学功法ID列表
    active_buffs: str = "[]"    # JSON存储当前激活的buff列表
    pvp_wins: int = 0           # PVP胜场
    pvp_losses: int = 0         # PVP败场
    last_pvp_time: float = 0.0  # 上次PVP时间戳
    sect_contribution: int = 0   # 宗门贡献度
    
    # v2.4.0 炼丹/炼器系统
    alchemy_level: int = 1      # 炼丹师等级
    alchemy_exp: int = 0        # 炼丹熟练度
    smithing_level: int = 1     # 炼器师等级
    smithing_exp: int = 0       # 炼器熟练度
    furnace_level: int = 1      # 丹炉等级
    forge_level: int = 1        # 炼器台等级
    unlocked_recipes: str = "[]"  # JSON存储已解锁配方ID列表
    
    # v2.5.0 昵称
    nickname: str = ""          # 玩家昵称（群昵称）

    def get_level(self, config_manager: "ConfigManager") -> str:
        if 0 <= self.level_index < len(config_manager.level_data):
            return config_manager.level_data[self.level_index]["level_name"]
        return "未知境界"

    def get_learned_skills_list(self) -> List[str]:
        """获取已学习功法ID列表"""
        try:
            return json.loads(self.learned_skills) if self.learned_skills else []
        except json.JSONDecodeError:
            return []
    
    def set_learned_skills_list(self, skills: List[str]):
        """设置已学习功法ID列表"""
        self.learned_skills = json.dumps(skills)

    def get_active_buffs_list(self) -> List[Dict[str, Any]]:
        """获取当前激活的buff列表"""
        try:
            return json.loads(self.active_buffs) if self.active_buffs else []
        except json.JSONDecodeError:
            return []
    
    def set_active_buffs_list(self, buffs: List[Dict[str, Any]]):
        """设置当前激活的buff列表"""
        self.active_buffs = json.dumps(buffs)
    
    def add_buff(self, buff_type: str, value: int, duration: int):
        """添加一个buff (duration为剩余战斗次数)"""
        buffs = self.get_active_buffs_list()
        # 检查是否已有同类型buff，如果有则刷新
        for b in buffs:
            if b.get("type") == buff_type:
                b["value"] = max(b["value"], value)
                b["duration"] = max(b["duration"], duration)
                self.set_active_buffs_list(buffs)
                return
        # 添加新buff
        buffs.append({"type": buff_type, "value": value, "duration": duration})
        self.set_active_buffs_list(buffs)
    
    def consume_buff_duration(self):
        """战斗后消耗buff持续次数，移除已过期的buff"""
        buffs = self.get_active_buffs_list()
        new_buffs = []
        for b in buffs:
            b["duration"] -= 1
            if b["duration"] > 0:
                new_buffs.append(b)
        self.set_active_buffs_list(new_buffs)

    def get_combat_stats(self, config_manager: "ConfigManager") -> Dict[str, Any]:
        """计算并返回玩家的最终战斗属性（基础属性+装备加成+功法加成+buff加成）"""
        stats = {
            "hp": self.hp,
            "max_hp": self.max_hp,
            "attack": self.attack,
            "defense": self.defense,
        }
        
        # 装备加成
        equipment_ids = [self.equipped_weapon, self.equipped_armor, self.equipped_accessory]
        for item_id in equipment_ids:
            if item_id:
                item = config_manager.item_data.get(str(item_id))
                if item and item.equip_effects:
                    for key, value in item.equip_effects.items():
                        if key in stats:
                            stats[key] += value
        
        # 功法永久加成
        learned = self.get_learned_skills_list()
        for skill_id in learned:
            skill_item = config_manager.item_data.get(str(skill_id))
            if skill_item and hasattr(skill_item, 'skill_effects') and skill_item.skill_effects:
                for key, value in skill_item.skill_effects.items():
                    if key in stats:
                        stats[key] += value
        
        # Buff临时加成
        for buff in self.get_active_buffs_list():
            buff_type = buff.get("type", "")
            buff_value = buff.get("value", 0)
            if buff_type == "attack_buff":
                stats["attack"] += buff_value
            elif buff_type == "defense_buff":
                stats["defense"] += buff_value
            elif buff_type == "hp_buff":
                stats["max_hp"] += buff_value
        
        return stats
    
    def get_pvp_win_rate(self) -> float:
        """获取PVP胜率"""
        total = self.pvp_wins + self.pvp_losses
        return (self.pvp_wins / total * 100) if total > 0 else 0.0

    def get_unlocked_recipes_list(self) -> List[str]:
        """获取已解锁配方ID列表"""
        try:
            return json.loads(self.unlocked_recipes) if self.unlocked_recipes else []
        except json.JSONDecodeError:
            return []
    
    def set_unlocked_recipes_list(self, recipes: List[str]):
        """设置已解锁配方ID列表"""
        self.unlocked_recipes = json.dumps(recipes)
    
    def unlock_recipe(self, recipe_id: str) -> bool:
        """解锁一个配方，返回是否是新解锁"""
        recipes = self.get_unlocked_recipes_list()
        if recipe_id in recipes:
            return False
        recipes.append(recipe_id)
        self.set_unlocked_recipes_list(recipes)
        return True

    def get_realm_instance(self) -> Optional[RealmInstance]:
        if not self.realm_data:
            return None
        try:
            data = json.loads(self.realm_data)
            floors = [FloorEvent(**f) for f in data.get("floors", [])]
            data["floors"] = floors
            return RealmInstance(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_realm_instance(self, instance: Optional[RealmInstance]):
        if instance is None:
            self.realm_data = None
        else:
            self.realm_data = json.dumps(asdict(instance))

    def clone(self) -> "Player":
        return replace(self)

@dataclass
class PlayerEffect:
    experience: int = 0
    gold: int = 0
    hp: int = 0

@dataclass
class Boss:
    """世界Boss数据模型"""

    id: str
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    cooldown_minutes: int
    rewards: dict

@dataclass
class ActiveWorldBoss:
    """当前活跃的世界Boss数据模型"""

    boss_id: str
    current_hp: int
    max_hp: int
    spawned_at: float
    level_index: int
    defeated_at: Optional[float] = None

@dataclass
class Monster:
    """怪物数据模型"""

    id: str
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    rewards: dict

@dataclass
class AttackResult:
    """战斗结果数据模型"""

    success: bool
    message: str
    battle_over: bool = False
    updated_players: List[Player] = field(default_factory=list)