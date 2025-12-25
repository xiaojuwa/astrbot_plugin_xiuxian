# handlers/misc_handler.py
from astrbot.api.event import AstrMessageEvent
from ..data import DataBase

# 基础指令
CMD_START_XIUXIAN = "我要修仙"
CMD_PLAYER_INFO = "我的信息"
CMD_CHECK_IN = "签到"

# 修炼指令
CMD_START_CULTIVATION = "闭关"
CMD_END_CULTIVATION = "出关"
CMD_BREAKTHROUGH = "突破"
CMD_REROLL_SPIRIT_ROOT = "重入仙途"

# 商店指令
CMD_SHOP = "商店"
CMD_BACKPACK = "我的背包"
CMD_BUY = "购买"
CMD_USE_ITEM = "使用"
CMD_MY_EQUIPMENT = "我的装备"
CMD_UNEQUIP = "卸下"

# 宗门指令
CMD_CREATE_SECT = "创建宗门"
CMD_JOIN_SECT = "加入宗门"
CMD_MY_SECT = "我的宗门"
CMD_LEAVE_SECT = "退出宗门"

# 战斗指令
CMD_SPAR = "切磋"
CMD_BOSS_LIST = "查看世界boss"
CMD_FIGHT_BOSS = "讨伐boss"
CMD_ENTER_REALM = "探索秘境"
CMD_REALM_ADVANCE = "前进"
CMD_LEAVE_REALM = "离开秘境"

# 排行榜指令
CMD_REALM_RANKING = "境界排行"
CMD_WEALTH_RANKING = "财富排行"
CMD_COMBAT_RANKING = "战力排行"
CMD_MY_RANKING = "我的排名"

# 每日任务指令
CMD_DAILY_TASKS = "每日任务"
CMD_CLAIM_DAILY_REWARDS = "领取任务奖励"

# 奇遇指令
CMD_ADVENTURE = "奇遇"
CMD_ADVENTURE_STATUS = "奇遇状态"

# 天劫指令
CMD_TRIBULATION_INFO = "天劫信息"
CMD_CHALLENGE_TRIBULATION = "渡劫"

# 悬赏指令
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

__all__ = ["MiscHandler"]


class MiscHandler:
    """杂项指令处理器"""

    def __init__(self, db: DataBase):
        self.db = db

    async def handle_help(self, event: AstrMessageEvent):
        help_text = (
            "━━ 修仙指令手册 ━━\n"
            "\n"
            "【入门指引】\n"
            f"  {CMD_START_XIUXIAN} - 开启修仙之旅\n"
            f"  {CMD_PLAYER_INFO} - 查看人物信息\n"
            f"  {CMD_CHECK_IN} - 每日签到(0点刷新)\n"
            "\n"
            "【修炼成长】\n"
            f"  {CMD_START_CULTIVATION} - 开始闭关修炼\n"
            f"  {CMD_END_CULTIVATION} - 结束闭关\n"
            f"  {CMD_BREAKTHROUGH} - 尝试突破境界\n"
            f"  {CMD_REROLL_SPIRIT_ROOT} - 重置灵根\n"
            "\n"
            "【灵根概率】(修炼速度)\n"
            "  五行灵根 55.6% (1.0x)\n"
            "  变异灵根 11.1% (1.2x)\n"
            "  天灵根 11.1% (1.5x)\n"
            "  融合灵根 11.1% (1.8x)\n"
            "  混沌灵根 11.1% (2.0x)\n"
            "\n"
            "【坊市物品】\n"
            f"  {CMD_SHOP} - 查看坊市商品\n"
            f"  {CMD_BACKPACK} - 查看背包\n"
            f"  {CMD_BUY} <名> [数] - 购买物品\n"
            f"  {CMD_USE_ITEM} <名> [数] - 使用/装备/学习\n"
            f"  {CMD_MY_EQUIPMENT} - 查看装备\n"
            f"  {CMD_UNEQUIP} <部位> - 卸下装备\n"
            f"  {CMD_MY_SKILLS} - 查看已学功法\n"
            f"  {CMD_MY_BUFF} - 查看当前buff\n"
            "\n"
            "【宗门社交】\n"
            f"  {CMD_CREATE_SECT} <名> - 创建宗门\n"
            f"  {CMD_JOIN_SECT} <名> - 加入宗门\n"
            f"  {CMD_MY_SECT} - 查看宗门\n"
            f"  {CMD_LEAVE_SECT} - 退出宗门\n"
            f"  {CMD_SECT_DONATE} <数额> - 宗门捐献\n"
            "\n"
            "【战斗探险】\n"
            f"  {CMD_SPAR} @某人 - 切磋比试\n"
            f"  {CMD_DUEL} @某人 <灵石> - 奇斗(赌注)\n"
            f"  {CMD_PVP_RANKING} - PVP排行榜\n"
            f"  {CMD_BOSS_LIST} - 查看世界Boss\n"
            f"  {CMD_FIGHT_BOSS} <ID> - 讨伐Boss\n"
            f"  {CMD_ENTER_REALM} [类型] [难度] - 进入秘境\n"
            "    类型: 试炼/宝藏/妖兽/遗迹/幽冥\n"
            "    难度: 普通/困难/地狱(奖励2-3倍)\n"
            f"  {CMD_REALM_ADVANCE} - 秘境前进\n"
            f"  选择 <数字> - 秘境事件选择\n"
            f"  {CMD_LEAVE_REALM} - 离开秘境\n"
            "\n"
            "【排行榜】\n"
            f"  {CMD_REALM_RANKING} - 境界排行\n"
            f"  {CMD_WEALTH_RANKING} - 财富排行\n"
            f"  {CMD_COMBAT_RANKING} - 战力排行\n"
            f"  {CMD_MY_RANKING} - 我的排名\n"
            "\n"
            "【每日任务】\n"
            f"  {CMD_DAILY_TASKS} - 查看每日任务\n"
            f"  {CMD_CLAIM_DAILY_REWARDS} - 领取奖励\n"
            "\n"
            "【奇遇探索】\n"
            f"  {CMD_ADVENTURE} - 触发奇遇(每日3次)\n"
            f"  {CMD_ADVENTURE_STATUS} - 奇遇状态\n"
            "\n"
            "【天劫系统】\n"
            f"  {CMD_TRIBULATION_INFO} - 查看天劫信息\n"
            f"  {CMD_CHALLENGE_TRIBULATION} - 挑战天劫\n"
            "\n"
            "【悬赏任务】\n"
            f"  {CMD_BOUNTY_LIST} - 查看悬赏榜\n"
            f"  {CMD_ACCEPT_BOUNTY} <名> - 接取悬赏\n"
            f"  {CMD_BOUNTY_STATUS} - 悬赏状态\n"
            "\n"
            "【玩家交易】\n"
            f"  {CMD_TRANSFER} @某人 <数额> - 转账灵石\n"
            f"  {CMD_GIFT} @某人 <物品> - 赠送物品\n"
            "\n"
            "【炼丹/炼器】\n"
            f"  {CMD_ALCHEMY} [配方名] - 炼丹界面/炼制\n"
            f"  {CMD_SMITHING} [配方名] - 炼器界面/炼制\n"
            f"  {CMD_UPGRADE_FURNACE} - 升级丹炉\n"
            f"  {CMD_UPGRADE_FORGE} - 升级炼器台\n"
            f"  {CMD_RECIPE_INFO} <配方名> - 查看配方详情\n"
            f"  {CMD_RECIPE_LIST} - 查看所有配方\n"
            f"  {CMD_MATERIALS} - 查看材料图鉴\n"
            f"  {CMD_SELL} <物品> [数量] - 出售物品\n"
            "\n"
            "━━━━━━━━━━━━"
        )
        yield event.plain_result(help_text)