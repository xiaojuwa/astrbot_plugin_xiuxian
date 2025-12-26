from pathlib import Path
from astrbot.api import logger, AstrBotConfig
from astrbot.api.star import Context, Star, register
from astrbot.api.event import AstrMessageEvent, filter
from .data import DataBase, MigrationManager
from .config_manager import ConfigManager
from .handlers import (
    MiscHandler, PlayerHandler, ShopHandler, SectHandler, SectShopHandler, SectBuildingHandler,
    CombatHandler, RealmHandler, EquipmentHandler, RankingHandler, DailyTaskHandler, 
    AdventureHandler, TribulationHandler, BountyHandler, TradeHandler, CraftingHandler, 
    GMHandler, RedeemHandler
)

# 指令定义
CMD_HELP = "修仙帮助"
CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_CHECK_IN = "签到"
CMD_START_CULTIVATION = "闭关"
CMD_END_CULTIVATION = "出关"
CMD_BREAKTHROUGH = "突破"
CMD_REROLL_SPIRIT_ROOT = "重入仙途"
CMD_SHOP = "商店"
CMD_BACKPACK = "我的背包"
CMD_BUY = "购买"
CMD_USE_ITEM = "使用"
# 宗门相关指令
CMD_CREATE_SECT = "创建宗门"
CMD_JOIN_SECT = "加入宗门"
CMD_LEAVE_SECT = "离开宗门"
CMD_MY_SECT = "我的宗门"
CMD_SECT_SHOP = "宗门商店"
CMD_SECT_EXCHANGE = "兑换"
CMD_SECT_BUILDINGS = "宗门建筑"
CMD_BUILD = "建造建筑"
CMD_UPGRADE_BUILDING = "升级建筑"
CMD_ACTIVATE_BUILDING = "激活建筑"
CMD_SPAR = "切磋"
CMD_BOSS_LIST = "查看世界boss"
CMD_FIGHT_BOSS = "讨伐boss"
CMD_BOSS_LOGS = "boss战报"
CMD_ENTER_REALM = "探索秘境"
CMD_REALM_ADVANCE = "前进"
CMD_LEAVE_REALM = "离开秘境"
CMD_REALM_CHOICE = "选择"  # 秘境中的选择指令

# 装备相关指令
CMD_UNEQUIP = "卸下"
CMD_MY_EQUIPMENT = "我的装备"

# 排行榜相关指令
CMD_REALM_RANKING = "境界排行"
CMD_WEALTH_RANKING = "财富排行"
CMD_COMBAT_RANKING = "战力排行"
CMD_MY_RANKING = "我的排名"

# 每日任务相关指令
CMD_DAILY_TASKS = "每日任务"
CMD_CLAIM_DAILY_REWARDS = "领取任务奖励"

# 奇遇系统相关指令
CMD_ADVENTURE = "奇遇"
CMD_ADVENTURE_STATUS = "奇遇状态"

# 天劫系统相关指令
CMD_TRIBULATION_INFO = "天劫信息"
CMD_CHALLENGE_TRIBULATION = "渡劫"

# 悬赏任务相关指令
CMD_BOUNTY_LIST = "悬赏榜"
CMD_ACCEPT_BOUNTY = "接取悬赏"
CMD_BOUNTY_STATUS = "悬赏状态"

# v2.3.0 新增指令
CMD_DUEL = "奇斗"
CMD_PVP_RANKING = "PVP排行"
CMD_TRANSFER = "转账"
CMD_GIFT = "赠送"
CMD_SECT_DONATE = "宗门捐献"
CMD_MY_BUFF = "我的buff"
CMD_MY_SKILLS = "我的功法"

# v2.4.0 炼丹/炼器系统指令
CMD_ALCHEMY = "炼丹"
CMD_SMITHING = "炼器"
CMD_UPGRADE_FURNACE = "升级丹炉"
CMD_UPGRADE_FORGE = "升级炼器台"
CMD_RECIPE_INFO = "配方"
CMD_RECIPE_LIST = "配方图鉴"
CMD_MATERIALS = "材料图鉴"
CMD_SELL = "出售"

# v2.5.0 GM管理员指令
CMD_GM_ADD_GOLD = "GM加灵石"
CMD_GM_ADD_EXP = "GM加修为"
CMD_GM_SET_LEVEL = "GM设境界"
CMD_GM_ADD_ITEM = "GM加物品"
CMD_GM_SET_HP = "GM设生命"
CMD_GM_RESET_PLAYER = "GM重置玩家"
CMD_GM_VIEW_PLAYER = "GM查看玩家"
CMD_GM_LIST_LEVELS = "GM境界列表"
CMD_GM_LIST_ITEMS = "GM物品列表"
CMD_GM_CLEAR_STATE = "GM清状态"
CMD_GM_ADD_CODE = "GM添加激活码"
CMD_GM_DEL_CODE = "GM删除激活码"
CMD_GM_LIST_CODES = "GM激活码列表"
CMD_GM_ADD_CODE_ITEM = "GM激活码加物品"

# v2.5.0 激活码系统
CMD_REDEEM = "橘的恩赐"

@register(
    "astrbot_plugin_xiuxian",
    "xiaojuwa",
    "基于astrbot框架的文字修仙游戏",
    "v2.8.0", # 版本号 - 世界Boss系统增强
    "https://github.com/xiaojuwa/astrbot_plugin_xiuxian"
)
class XiuXianPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        _current_dir = Path(__file__).parent
        self.config_manager = ConfigManager(_current_dir)
        
        files_config = self.config.get("FILES", {})
        db_file = files_config.get("DATABASE_FILE", "xiuxian_data.db")
        self.db = DataBase(db_file)

        self.misc_handler = MiscHandler(self.db)
        self.player_handler = PlayerHandler(self.db, self.config, self.config_manager)
        self.shop_handler = ShopHandler(self.db, self.config_manager, self.config) # 传入config
        self.sect_handler = SectHandler(self.db, self.config, self.config_manager)
        self.sect_shop_handler = SectShopHandler(self.db, self.config, self.config_manager)
        self.sect_building_handler = SectBuildingHandler(self.db, self.config, self.config_manager)
        self.combat_handler = CombatHandler(self.db, self.config, self.config_manager)
        self.realm_handler = RealmHandler(self.db, self.config, self.config_manager)
        self.equipment_handler = EquipmentHandler(self.db, self.config_manager)
        self.ranking_handler = RankingHandler(self.db, self.config_manager)
        self.daily_task_handler = DailyTaskHandler(self.db, self.config, self.config_manager)
        self.adventure_handler = AdventureHandler(self.db, self.config, self.config_manager)
        self.tribulation_handler = TribulationHandler(self.db, self.config, self.config_manager)
        self.bounty_handler = BountyHandler(self.db, self.config, self.config_manager)
        self.trade_handler = TradeHandler(self.db, self.config, self.config_manager)
        self.crafting_handler = CraftingHandler(self.db, self.config, self.config_manager)
        self.gm_handler = GMHandler(self.db, self.config, self.config_manager)
        self.redeem_handler = RedeemHandler(self.db, self.config, self.config_manager)

        # 注入每日任务处理器到各个处理器
        self.player_handler.set_daily_task_handler(self.daily_task_handler)
        self.combat_handler.set_daily_task_handler(self.daily_task_handler)
        self.combat_handler.set_context(context)  # 注入context以支持Boss击杀广播
        self.realm_handler.set_daily_task_handler(self.daily_task_handler)
        self.adventure_handler.set_daily_task_handler(self.daily_task_handler)
        self.bounty_handler.set_daily_task_handler(self.daily_task_handler)
        self.shop_handler.set_daily_task_handler(self.daily_task_handler)
        self.sect_handler.set_daily_task_handler(self.daily_task_handler)
        self.crafting_handler.set_daily_task_handler(self.daily_task_handler)
        self.trade_handler.set_daily_task_handler(self.daily_task_handler)

        access_control_config = self.config.get("ACCESS_CONTROL", {})
        self.whitelist_groups = [str(g) for g in access_control_config.get("WHITELIST_GROUPS", [])]
        
        logger.info("【修仙插件】XiuXianPlugin __init__ 方法成功执行完毕。")

    def _check_access(self, event: AstrMessageEvent) -> bool:
        """检查访问权限，支持群聊白名单控制
        
        返回值:
        - True: 允许访问
        - False: 拒绝访问
        """
        # 如果没有配置白名单，允许所有访问
        if not self.whitelist_groups:
            return True
        
        # 获取群组ID，私聊时为None
        group_id = event.get_group_id()
        
        # 如果是私聊，允许访问（私聊通常应该被允许）
        if not group_id:
            return True
            
        # 检查群组是否在白名单中
        if str(group_id) in self.whitelist_groups:
            return True
        
        return False
    
    async def _send_access_denied_message(self, event: AstrMessageEvent):
        """发送访问被拒绝的提示消息"""
        try:
            await event.send("抱歉，此群聊未在修仙插件的白名单中，无法使用相关功能。")
        except:
            # 如果发送失败，静默处理
            pass

    async def initialize(self):
        await self.db.connect()
        migration_manager = MigrationManager(self.db.conn, self.config_manager)
        await migration_manager.migrate()
        logger.info("修仙插件已加载。")

    async def terminate(self):
        await self.db.close()
        logger.info("修仙插件已卸载。")
        
    @filter.command(CMD_HELP, "显示帮助信息")
    async def handle_help(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.misc_handler.handle_help(event): yield r
        
    @filter.command(CMD_START_XIUXIAN, "开始你的修仙之路")
    async def handle_start_xiuxian(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_start_xiuxian(event): yield r
        
    @filter.command(CMD_PLAYER_INFO, "查看你的角色信息")
    async def handle_player_info(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_player_info(event): yield r
        
    @filter.command(CMD_CHECK_IN, "每日签到领取奖励")
    async def handle_check_in(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_check_in(event): yield r
        
    @filter.command(CMD_START_CULTIVATION, "开始闭关修炼")
    async def handle_start_cultivation(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_start_cultivation(event): yield r
        
    @filter.command(CMD_END_CULTIVATION, "结束闭关修炼")
    async def handle_end_cultivation(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_end_cultivation(event): yield r
        
    @filter.command(CMD_BREAKTHROUGH, "尝试突破当前境界")
    async def handle_breakthrough(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_breakthrough(event): yield r
        
    @filter.command(CMD_REROLL_SPIRIT_ROOT, "花费灵石，重置灵根")
    async def handle_reroll_spirit_root(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_reroll_spirit_root(event): yield r
        
    @filter.command(CMD_SHOP, "查看坊市商品")
    async def handle_shop(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.shop_handler.handle_shop(event): yield r
        
    @filter.command(CMD_BACKPACK, "查看你的背包")
    async def handle_backpack(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.shop_handler.handle_backpack(event): yield r
        
    @filter.command(CMD_BUY, "购买物品")
    async def handle_buy(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.shop_handler.handle_buy(event, item_name, quantity): yield r
        
    @filter.command(CMD_USE_ITEM, "使用背包中的物品")
    async def handle_use(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.shop_handler.handle_use(event, item_name, quantity): yield r
        
    @filter.command(CMD_CREATE_SECT, "创建你的宗门")
    async def handle_create_sect(self, event: AstrMessageEvent, sect_name: str):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_handler.handle_create_sect(event, sect_name): yield r
        
    @filter.command(CMD_JOIN_SECT, "加入一个宗门")
    async def handle_join_sect(self, event: AstrMessageEvent, sect_name: str):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_handler.handle_join_sect(event, sect_name): yield r
        
    @filter.command(CMD_LEAVE_SECT, "退出当前宗门")
    async def handle_leave_sect(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_handler.handle_leave_sect(event): yield r
        
    @filter.command(CMD_MY_SECT, "查看我的宗门信息")
    async def handle_my_sect(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_handler.handle_my_sect(event): yield r
    
    # --- v2.7.0 宗门商店指令 ---
    @filter.command(CMD_SECT_SHOP, "查看宗门商店")
    async def handle_sect_shop(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_shop_handler.handle_sect_shop(event): yield r
    
    @filter.command(CMD_SECT_EXCHANGE, "兑换宗门商品")
    async def handle_sect_exchange(self, event: AstrMessageEvent, item_name: str, quantity: str = "1"):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_shop_handler.handle_sect_exchange(event, item_name, quantity): yield r

    # --- 宗门建筑指令 ---
    @filter.command(CMD_SECT_BUILDINGS, "查看宗门建筑")
    async def handle_sect_buildings(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_building_handler.handle_sect_buildings(event): yield r

    @filter.command(CMD_BUILD, "建造宗门建筑")
    async def handle_build(self, event: AstrMessageEvent, building_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_building_handler.handle_build(event, building_name): yield r

    @filter.command(CMD_UPGRADE_BUILDING, "升级宗门建筑")
    async def handle_upgrade_building(self, event: AstrMessageEvent, building_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_building_handler.handle_upgrade_building(event, building_name): yield r

    @filter.command(CMD_ACTIVATE_BUILDING, "激活宗门建筑Buff")
    async def handle_activate_building(self, event: AstrMessageEvent, building_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_building_handler.handle_activate_building(event, building_name): yield r
        
    @filter.command(CMD_SPAR, "与其他玩家切磋")
    async def handle_spar(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.combat_handler.handle_spar(event): yield r
        
    @filter.command(CMD_BOSS_LIST, "查看当前所有世界Boss")
    async def handle_boss_list(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.combat_handler.handle_boss_list(event): yield r
        
    @filter.command(CMD_FIGHT_BOSS, "讨伐指定ID的世界Boss")
    async def handle_fight_boss(self, event: AstrMessageEvent, boss_id: str):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.combat_handler.handle_fight_boss(event, boss_id): yield r
        
    @filter.command(CMD_BOSS_LOGS, "查看近期Boss击杀战报")
    async def handle_boss_logs(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.combat_handler.handle_boss_logs(event): yield r
        
    @filter.command(CMD_ENTER_REALM, "根据当前境界，探索一个随机秘境")
    async def handle_enter_realm(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.realm_handler.handle_enter_realm(event): yield r
        
    @filter.command(CMD_REALM_ADVANCE, "在秘境中前进")
    async def handle_realm_advance(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.realm_handler.handle_realm_advance(event): yield r
        
    @filter.command(CMD_LEAVE_REALM, "离开当前秘境")
    async def handle_leave_realm(self, event: AstrMessageEvent):
        if not self._check_access(event): 
            await self._send_access_denied_message(event)
            return
        async for r in self.realm_handler.handle_leave_realm(event): yield r
    
    @filter.command(CMD_REALM_CHOICE, "在秘境事件中做出选择")
    async def handle_realm_choice(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.realm_handler.handle_realm_choice(event): yield r

    # --- 装备指令 ---
    @filter.command(CMD_UNEQUIP, "卸下一件装备")
    async def handle_unequip(self, event: AstrMessageEvent, subtype_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.equipment_handler.handle_unequip(event, subtype_name): yield r

    @filter.command(CMD_MY_EQUIPMENT, "查看当前装备")
    async def handle_my_equipment(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.equipment_handler.handle_my_equipment(event): yield r

    # --- 排行榜指令 ---
    @filter.command(CMD_REALM_RANKING, "查看境界排行榜")
    async def handle_realm_ranking(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.ranking_handler.handle_realm_ranking(event): yield r

    @filter.command(CMD_WEALTH_RANKING, "查看财富排行榜")
    async def handle_wealth_ranking(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.ranking_handler.handle_wealth_ranking(event): yield r

    @filter.command(CMD_COMBAT_RANKING, "查看战力排行榜")
    async def handle_combat_ranking(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.ranking_handler.handle_combat_ranking(event): yield r

    @filter.command(CMD_MY_RANKING, "查看我的排名")
    async def handle_my_ranking(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.ranking_handler.handle_my_ranking(event): yield r

    # --- 每日任务指令 ---
    @filter.command(CMD_DAILY_TASKS, "查看每日任务")
    async def handle_daily_tasks(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.daily_task_handler.handle_daily_tasks(event): yield r

    @filter.command(CMD_CLAIM_DAILY_REWARDS, "领取每日任务奖励")
    async def handle_claim_daily_rewards(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.daily_task_handler.handle_claim_daily_rewards(event): yield r

    # --- 奇遇系统指令 ---
    @filter.command(CMD_ADVENTURE, "触发一次奇遇探索")
    async def handle_adventure(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.adventure_handler.handle_adventure(event): yield r

    @filter.command(CMD_ADVENTURE_STATUS, "查看今日奇遇状态")
    async def handle_adventure_status(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.adventure_handler.handle_adventure_status(event): yield r

    # --- 天劫系统指令 ---
    @filter.command(CMD_TRIBULATION_INFO, "查看天劫信息")
    async def handle_tribulation_info(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.tribulation_handler.handle_tribulation_info(event): yield r

    @filter.command(CMD_CHALLENGE_TRIBULATION, "挑战天劫")
    async def handle_challenge_tribulation(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.tribulation_handler.handle_challenge_tribulation(event): yield r

    # --- 悬赏任务指令 ---
    @filter.command(CMD_BOUNTY_LIST, "查看悬赏任务列表")
    async def handle_bounty_list(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.bounty_handler.handle_bounty_list(event): yield r

    @filter.command(CMD_ACCEPT_BOUNTY, "接取并执行悬赏任务")
    async def handle_accept_bounty(self, event: AstrMessageEvent, bounty_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.bounty_handler.handle_accept_bounty(event, bounty_name): yield r

    @filter.command(CMD_BOUNTY_STATUS, "查看悬赏状态")
    async def handle_bounty_status(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.bounty_handler.handle_bounty_status(event): yield r

    # --- v2.3.0 新增指令 ---
    @filter.command(CMD_DUEL, "带灵石赌注的切磋")
    async def handle_duel(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.combat_handler.handle_duel(event): yield r

    @filter.command(CMD_TRANSFER, "转账灵石给其他玩家")
    async def handle_transfer(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.trade_handler.handle_transfer(event): yield r

    @filter.command(CMD_GIFT, "赠送物品给其他玩家")
    async def handle_gift(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.trade_handler.handle_gift(event): yield r

    @filter.command(CMD_PVP_RANKING, "查看PVP排行榜")
    async def handle_pvp_ranking(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.ranking_handler.handle_pvp_ranking(event): yield r

    @filter.command(CMD_SECT_DONATE, "向宗门捐献灵石")
    async def handle_sect_donate(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.sect_handler.handle_sect_donate(event): yield r

    @filter.command(CMD_MY_BUFF, "查看当前激活的buff")
    async def handle_my_buff(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_my_buff(event): yield r

    @filter.command(CMD_MY_SKILLS, "查看已学习的功法")
    async def handle_my_skills(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.player_handler.handle_my_skills(event): yield r

    # --- v2.4.0 炼丹/炼器系统指令 ---
    @filter.command(CMD_ALCHEMY, "炼丹界面或炼制丹药")
    async def handle_alchemy(self, event: AstrMessageEvent, recipe_name: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        if recipe_name:
            async for r in self.crafting_handler.handle_craft_alchemy(event, recipe_name): yield r
        else:
            async for r in self.crafting_handler.handle_alchemy(event): yield r

    @filter.command(CMD_SMITHING, "炼器界面或炼制法器")
    async def handle_smithing(self, event: AstrMessageEvent, recipe_name: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        if recipe_name:
            async for r in self.crafting_handler.handle_craft_smithing(event, recipe_name): yield r
        else:
            async for r in self.crafting_handler.handle_smithing(event): yield r

    @filter.command(CMD_UPGRADE_FURNACE, "升级丹炉")
    async def handle_upgrade_furnace(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.crafting_handler.handle_upgrade_furnace(event): yield r

    @filter.command(CMD_UPGRADE_FORGE, "升级炼器台")
    async def handle_upgrade_forge(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.crafting_handler.handle_upgrade_forge(event): yield r

    @filter.command(CMD_RECIPE_INFO, "查看配方详情")
    async def handle_recipe_info(self, event: AstrMessageEvent, recipe_name: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.crafting_handler.handle_recipe_info(event, recipe_name): yield r

    @filter.command(CMD_RECIPE_LIST, "查看所有配方")
    async def handle_recipe_list(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.crafting_handler.handle_recipe_list(event): yield r

    @filter.command(CMD_MATERIALS, "查看材料图鉴")
    async def handle_materials(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.crafting_handler.handle_materials(event): yield r

    @filter.command(CMD_SELL, "出售物品给商店")
    async def handle_sell(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.shop_handler.handle_sell(event, item_name, quantity): yield r

    # --- v2.5.0 GM管理员指令 ---
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_ADD_GOLD, "GM添加灵石")
    async def handle_gm_add_gold(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        # 获取完整参数：去除命令本身，保留后续所有内容
        msg = event.message_str.strip()
        params = msg.replace(CMD_GM_ADD_GOLD, "", 1).strip()
        async for r in self.gm_handler.handle_gm_add_gold(event, params): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_ADD_EXP, "GM添加修为")
    async def handle_gm_add_exp(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        msg = event.message_str.strip()
        params = msg.replace(CMD_GM_ADD_EXP, "", 1).strip()
        async for r in self.gm_handler.handle_gm_add_exp(event, params): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_SET_LEVEL, "GM设置境界")
    async def handle_gm_set_level(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        msg = event.message_str.strip()
        params = msg.replace(CMD_GM_SET_LEVEL, "", 1).strip()
        async for r in self.gm_handler.handle_gm_set_level(event, params): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_ADD_ITEM, "GM添加物品")
    async def handle_gm_add_item(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        msg = event.message_str.strip()
        params = msg.replace(CMD_GM_ADD_ITEM, "", 1).strip()
        # params可能是 "QQ号 物品名 数量" 或 "@用户 物品名 数量"
        parts = params.split()
        item_name = " ".join(parts[:-1]) if len(parts) > 1 else ""
        quantity = parts[-1] if parts else "1"
        async for r in self.gm_handler.handle_gm_add_item(event, item_name, quantity): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_SET_HP, "GM设置生命值")
    async def handle_gm_set_hp(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        msg = event.message_str.strip()
        params = msg.replace(CMD_GM_SET_HP, "", 1).strip()
        async for r in self.gm_handler.handle_gm_set_hp(event, params): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_RESET_PLAYER, "GM重置玩家")
    async def handle_gm_reset_player(self, event: AstrMessageEvent, qq_param: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_reset_player(event, qq_param): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_VIEW_PLAYER, "GM查看玩家详情")
    async def handle_gm_view_player(self, event: AstrMessageEvent, qq_param: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_view_player(event, qq_param): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_LIST_LEVELS, "GM查看境界列表")
    async def handle_gm_list_levels(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_list_levels(event): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_LIST_ITEMS, "GM查看物品列表")
    async def handle_gm_list_items(self, event: AstrMessageEvent, item_type: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_list_items(event, item_type): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_CLEAR_STATE, "GM清除玩家状态")
    async def handle_gm_clear_state(self, event: AstrMessageEvent, qq_param: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_clear_state(event, qq_param): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_ADD_CODE, "GM添加激活码")
    async def handle_gm_add_code(self, event: AstrMessageEvent, code: str, gold: int = 0, exp: int = 0, max_uses: int = 100, description: str = ""):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_add_code(event, code, gold, exp, max_uses, description): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_DEL_CODE, "GM删除激活码")
    async def handle_gm_del_code(self, event: AstrMessageEvent, code: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_del_code(event, code): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_LIST_CODES, "GM查看激活码列表")
    async def handle_gm_list_codes(self, event: AstrMessageEvent):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_list_codes(event): yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(CMD_GM_ADD_CODE_ITEM, "GM为激活码添加物品")
    async def handle_gm_add_code_item(self, event: AstrMessageEvent, code: str, item_name: str, quantity: int = 1):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.gm_handler.handle_gm_add_code_item(event, code, item_name, quantity): yield r

    # --- v2.5.0 激活码系统 ---
    @filter.command(CMD_REDEEM, "使用激活码领取奖励")
    async def handle_redeem(self, event: AstrMessageEvent, code: str):
        if not self._check_access(event):
            await self._send_access_denied_message(event)
            return
        async for r in self.redeem_handler.handle_redeem(event, code): yield r