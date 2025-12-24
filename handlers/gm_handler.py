# handlers/gm_handler.py
"""GM管理员指令处理器 - 用于修改游戏数据"""

from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig, logger
from ..data import DataBase
from ..models import Player
from ..config_manager import ConfigManager
from .utils import player_required

__all__ = ["GMHandler"]

# 固定的超级管理员QQ（硬编码，不可修改）
SUPER_ADMIN_QQ = "1733533842"

class GMHandler:
    """GM管理员指令处理器"""
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager

    def is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        if str(user_id) == SUPER_ADMIN_QQ:
            return True
        admin_list = self.config.get("ACCESS_CONTROL", {}).get("ADMIN_QQ_LIST", [SUPER_ADMIN_QQ])
        return str(user_id) in [str(qq) for qq in admin_list]

    def _parse_at_user(self, event: AstrMessageEvent) -> str:
        """从消息中解析被@的用户ID"""
        message = event.message_obj.message
        for comp in message:
            if hasattr(comp, 'qq'):
                return str(comp.qq)
        return ""

    async def handle_gm_add_gold(self, event: AstrMessageEvent, amount: int):
        """GM添加灵石"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM加灵石 @玩家 1000")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        player.gold += amount
        if player.gold < 0:
            player.gold = 0
        await self.db.update_player(player)
        
        action = "增加" if amount >= 0 else "扣除"
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 为玩家 {target_id} {action}了 {abs(amount)} 灵石")
        yield event.plain_result(f"✅ 已为玩家{action} {abs(amount)} 灵石\n当前灵石：{player.gold}")

    async def handle_gm_add_exp(self, event: AstrMessageEvent, amount: int):
        """GM添加修为"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM加修为 @玩家 10000")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        player.experience += amount
        if player.experience < 0:
            player.experience = 0
        await self.db.update_player(player)
        
        action = "增加" if amount >= 0 else "扣除"
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 为玩家 {target_id} {action}了 {abs(amount)} 修为")
        yield event.plain_result(f"✅ 已为玩家{action} {abs(amount)} 修为\n当前修为：{player.experience}")

    async def handle_gm_set_level(self, event: AstrMessageEvent, level_index: int):
        """GM设置境界"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM设境界 @玩家 10")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        max_level = len(self.config_manager.level_data) - 1
        if level_index < 0 or level_index > max_level:
            yield event.plain_result(f"境界索引无效，有效范围：0-{max_level}")
            return
        
        old_level = player.get_level(self.config_manager)
        player.level_index = level_index
        
        level_config = self.config_manager.level_data[level_index]
        player.max_hp = level_config.get("base_hp", 100)
        player.hp = player.max_hp
        player.attack = level_config.get("base_attack", 10)
        player.defense = level_config.get("base_defense", 5)
        
        await self.db.update_player(player)
        
        new_level = player.get_level(self.config_manager)
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 将玩家 {target_id} 境界从 {old_level} 修改为 {new_level}")
        yield event.plain_result(f"✅ 已将玩家境界修改为：{new_level}\n基础属性已同步更新")

    async def handle_gm_add_item(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        """GM添加物品"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM加物品 @玩家 聚气丹 10")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        item_id = None
        item_data = None
        for iid, idata in self.config_manager.item_data.items():
            if idata.name == item_name:
                item_id = iid
                item_data = idata
                break
        
        if not item_id:
            yield event.plain_result(f"未找到物品「{item_name}」")
            return
        
        if quantity <= 0:
            yield event.plain_result("数量必须大于0")
            return
        
        await self.db.add_items_to_inventory_in_transaction(target_id, {item_id: quantity})
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 为玩家 {target_id} 添加了 {quantity}x {item_name}")
        yield event.plain_result(f"✅ 已为玩家添加 {quantity}x「{item_name}」({item_data.rank})")

    async def handle_gm_set_hp(self, event: AstrMessageEvent, hp: int):
        """GM设置生命值"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM设生命 @玩家 1000")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        if hp < 0:
            yield event.plain_result("生命值不能为负数")
            return
        
        player.hp = min(hp, player.max_hp)
        await self.db.update_player(player)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 将玩家 {target_id} 生命值设为 {player.hp}")
        yield event.plain_result(f"✅ 已将玩家生命值设为：{player.hp}/{player.max_hp}")

    async def handle_gm_reset_player(self, event: AstrMessageEvent):
        """GM重置玩家"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM重置玩家 @玩家")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        initial_gold = self.config.get("VALUES", {}).get("INITIAL_GOLD", 100)
        
        player.level_index = 0
        player.experience = 0
        player.gold = initial_gold
        player.state = "空闲"
        player.state_start_time = 0.0
        player.hp = 100
        player.max_hp = 100
        player.attack = 10
        player.defense = 5
        player.equipped_weapon = None
        player.equipped_armor = None
        player.equipped_accessory = None
        player.learned_skills = "[]"
        player.active_buffs = "[]"
        player.realm_id = None
        player.realm_floor = 0
        player.realm_data = None
        player.alchemy_level = 1
        player.alchemy_exp = 0
        player.smithing_level = 1
        player.smithing_exp = 0
        player.furnace_level = 1
        player.forge_level = 1
        player.unlocked_recipes = "[]"
        
        await self.db.update_player(player)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 重置了玩家 {target_id}")
        yield event.plain_result(f"✅ 已重置玩家数据\n境界：{player.get_level(self.config_manager)}\n灵石：{player.gold}")

    async def handle_gm_view_player(self, event: AstrMessageEvent):
        """GM查看玩家详细信息"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM查看玩家 @玩家")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        combat_stats = player.get_combat_stats(self.config_manager)
        
        info = (
            f"=== GM查看玩家信息 ===\n"
            f"用户ID：{player.user_id}\n"
            f"昵称：{player.nickname or '未知'}\n"
            f"境界：{player.get_level(self.config_manager)} (索引:{player.level_index})\n"
            f"灵根：{player.spiritual_root}\n"
            f"修为：{player.experience}\n"
            f"灵石：{player.gold}\n"
            f"状态：{player.state}\n"
            f"--- 属性 ---\n"
            f"生命：{player.hp}/{combat_stats['max_hp']}\n"
            f"攻击：{combat_stats['attack']} (基础:{player.attack})\n"
            f"防御：{combat_stats['defense']} (基础:{player.defense})\n"
            f"--- 宗门 ---\n"
            f"宗门：{player.sect_name or '无'}\n"
            f"贡献度：{player.sect_contribution}\n"
            f"--- PVP ---\n"
            f"胜场：{player.pvp_wins} | 败场：{player.pvp_losses}\n"
            f"胜率：{player.get_pvp_win_rate():.1f}%\n"
            f"--- 炼丹/炼器 ---\n"
            f"炼丹等级：{player.alchemy_level} (熟练度:{player.alchemy_exp})\n"
            f"炼器等级：{player.smithing_level} (熟练度:{player.smithing_exp})\n"
            f"丹炉等级：{player.furnace_level}\n"
            f"炼器台等级：{player.forge_level}\n"
            f"========================"
        )
        yield event.plain_result(info)

    async def handle_gm_list_levels(self, event: AstrMessageEvent):
        """GM查看所有境界列表"""
        lines = ["=== 境界列表 ==="]
        for idx, level in enumerate(self.config_manager.level_data):
            lines.append(f"{idx}: {level['level_name']}")
        lines.append("================")
        yield event.plain_result("\n".join(lines))

    async def handle_gm_list_items(self, event: AstrMessageEvent, item_type: str = ""):
        """GM查看物品列表"""
        lines = ["=== 物品列表 ==="]
        for item_id, item in self.config_manager.item_data.items():
            if item_type and item.type != item_type:
                continue
            lines.append(f"[{item_id}] {item.name} ({item.type}/{item.rank}) - {item.price}灵石")
        
        if len(lines) > 50:
            lines = lines[:50]
            lines.append("... (显示前50条)")
        
        lines.append("================")
        yield event.plain_result("\n".join(lines))

    async def handle_gm_clear_state(self, event: AstrMessageEvent):
        """GM清除玩家状态（解除闭关/秘境等）"""
        target_id = self._parse_at_user(event)
        if not target_id:
            yield event.plain_result("请@一个玩家，例如：GM清状态 @玩家")
            return
        
        player = await self.db.get_player_by_id(target_id)
        if not player:
            yield event.plain_result("目标玩家尚未踏入仙途。")
            return
        
        old_state = player.state
        player.state = "空闲"
        player.state_start_time = 0.0
        player.realm_id = None
        player.realm_floor = 0
        player.realm_data = None
        
        await self.db.update_player(player)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 清除了玩家 {target_id} 的状态 ({old_state} -> 空闲)")
        yield event.plain_result(f"✅ 已清除玩家状态\n原状态：{old_state} → 空闲")

    # ========== 激活码管理指令 ==========
    
    async def handle_gm_add_code(self, event: AstrMessageEvent, code: str, gold: int = 0, exp: int = 0, max_uses: int = 100, description: str = ""):
        """GM添加激活码
        用法：GM添加激活码 <激活码> [灵石] [修为] [次数] [描述]
        例如：GM添加激活码 新年快乐2025 1000 500 100 新年福利
        """
        if not code:
            yield event.plain_result("请输入激活码，例如：GM添加激活码 新年快乐2025 1000 500 100 新年福利")
            return
        
        # 检查激活码是否已存在
        existing = await self.db.get_gm_redeem_code(code)
        if existing:
            yield event.plain_result(f"激活码「{code}」已存在，请使用其他名称或先删除。")
            return
        
        # 添加激活码到数据库
        await self.db.add_gm_redeem_code(code, gold, exp, max_uses, description)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 添加了激活码「{code}」")
        yield event.plain_result(
            f"✅ 激活码添加成功\n"
            f"激活码：{code}\n"
            f"灵石：{gold}\n"
            f"修为：{exp}\n"
            f"最大使用次数：{max_uses if max_uses > 0 else '无限制'}\n"
            f"描述：{description or '无'}"
        )

    async def handle_gm_del_code(self, event: AstrMessageEvent, code: str):
        """GM删除激活码"""
        if not code:
            yield event.plain_result("请输入要删除的激活码，例如：GM删除激活码 新年快乐2025")
            return
        
        existing = await self.db.get_gm_redeem_code(code)
        if not existing:
            yield event.plain_result(f"激活码「{code}」不存在。")
            return
        
        await self.db.delete_gm_redeem_code(code)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 删除了激活码「{code}」")
        yield event.plain_result(f"✅ 已删除激活码「{code}」")

    async def handle_gm_list_codes(self, event: AstrMessageEvent):
        """GM查看激活码列表"""
        codes = await self.db.get_all_gm_redeem_codes()
        
        if not codes:
            yield event.plain_result("当前没有任何激活码。\n使用「GM添加激活码 <激活码> [灵石] [修为] [次数] [描述]」添加")
            return
        
        lines = ["=== 激活码列表 ==="]
        for c in codes:
            use_count = await self.db.get_redeem_code_use_count(c['code'])
            max_uses_str = str(c['max_uses']) if c['max_uses'] > 0 else "∞"
            lines.append(
                f"📜 {c['code']}\n"
                f"   💰{c['gold']} ✨{c['exp']} | 已用:{use_count}/{max_uses_str}\n"
                f"   {c['description'] or '无描述'}"
            )
        lines.append("==================")
        yield event.plain_result("\n".join(lines))

    async def handle_gm_add_code_item(self, event: AstrMessageEvent, code: str, item_name: str, quantity: int = 1):
        """GM为激活码添加物品奖励"""
        if not code or not item_name:
            yield event.plain_result("用法：GM激活码加物品 <激活码> <物品名> [数量]")
            return
        
        existing = await self.db.get_gm_redeem_code(code)
        if not existing:
            yield event.plain_result(f"激活码「{code}」不存在，请先添加激活码。")
            return
        
        # 验证物品是否存在
        item_id = None
        for iid, idata in self.config_manager.item_data.items():
            if idata.name == item_name:
                item_id = iid
                break
        
        if not item_id:
            yield event.plain_result(f"未找到物品「{item_name}」")
            return
        
        if quantity <= 0:
            yield event.plain_result("数量必须大于0")
            return
        
        await self.db.add_gm_redeem_code_item(code, item_name, quantity)
        
        logger.info(f"[GM] 管理员 {event.get_sender_id()} 为激活码「{code}」添加了 {quantity}x {item_name}")
        yield event.plain_result(f"✅ 已为激活码「{code}」添加奖励：{quantity}x「{item_name}」")
