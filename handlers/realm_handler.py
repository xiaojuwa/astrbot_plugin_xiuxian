# handlers/realm_handler.py
from astrbot.api.event import AstrMessageEvent
from astrbot.api import AstrBotConfig
from ..data import DataBase
from ..core import RealmManager
from ..config_manager import ConfigManager
from ..models import Player
from .utils import player_required

CMD_REALM_ADVANCE = "前进"

__all__ = ["RealmHandler"]

class RealmHandler:
    # 秘境相关指令处理器
    
    def __init__(self, db: DataBase, config: AstrBotConfig, config_manager: ConfigManager):
        self.db = db
        self.config = config
        self.config_manager = config_manager
        self.realm_manager = RealmManager(db, config, config_manager)
        self.daily_task_handler = None  # 延迟注入
    
    def set_daily_task_handler(self, handler):
        """注入每日任务处理器"""
        self.daily_task_handler = handler

    @player_required
    async def handle_enter_realm(self, player: Player, event: AstrMessageEvent):
        """处理进入秘境指令，支持格式：探索秘境 [类型] [难度]"""
        # 解析参数
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        realm_type = "trial"  # 默认试炼之地
        difficulty = "normal"  # 默认普通难度
        
        # 解析参数：探索秘境 [类型] [难度]
        if len(parts) >= 2:
            # 解析类型
            type_mapping = {
                "试炼": "trial",
                "宝藏": "treasure",
                "妖兽": "beast",
                "遗迹": "ruin",
                "幽冥": "ghost"
            }
            if parts[1] in type_mapping:
                realm_type = type_mapping[parts[1]]
        
        if len(parts) >= 3:
            # 解析难度
            diff_mapping = {
                "普通": "normal",
                "困难": "hard",
                "地狱": "hell"
            }
            if parts[2] in diff_mapping:
                difficulty = diff_mapping[parts[2]]
        
        success, msg, updated_player = await self.realm_manager.start_session(
            player, CMD_REALM_ADVANCE, realm_type, difficulty
        )
        
        if success and updated_player:
            await self.db.update_player(updated_player)
            
            # 完成每日任务
            if self.daily_task_handler:
                completed = await self.daily_task_handler.complete_task(player.user_id, "realm_explore")
                if completed:
                    msg += "\n🎯 每日任务「秘境探险」已完成！"
        
        yield event.plain_result(msg)

    @player_required
    async def handle_realm_advance(self, player: Player, event: AstrMessageEvent):
        if not player.realm_id:
            yield event.plain_result("你不在任何秘境中，无法前进。")
            return

        success, msg, updated_player, gained_items = await self.realm_manager.advance_session(player)

        await self.db.update_player(updated_player)

        if gained_items:
            await self.db.add_items_to_inventory_in_transaction(updated_player.user_id, gained_items)
            item_log = []
            for item_id, qty in gained_items.items():
                item = self.config_manager.item_data.get(str(item_id))
                item_name = item.name if item else "未知物品"
                item_log.append(f"【{item_name}】x{qty}")
            if item_log:
                msg += "\n获得物品：" + ", ".join(item_log)

        # 更新每日任务进度（秘境深入需要前进3层）
        if success and self.daily_task_handler:
            completed, task_msg = await self.daily_task_handler.add_task_progress(player.user_id, "realm_advance", 1)
            if task_msg:
                msg += f"\n{task_msg}"

        yield event.plain_result(msg)

    @player_required
    async def handle_leave_realm(self, player: Player, event: AstrMessageEvent):
        if not player.realm_id:
            yield event.plain_result("你不在任何秘境中。")
            return

        realm_instance = player.get_realm_instance()
        realm_name = f"{player.get_level(self.config_manager)}修士的试炼" if realm_instance else "未知的秘境"

        player.realm_id = None
        player.realm_floor = 0
        player.set_realm_instance(None)
        player.realm_pending_choice = None  # 清除待选择事件

        await self.db.update_player(player)

        yield event.plain_result(f"你已从【{realm_name}】中脱离，回到了大千世界。")
    
    @player_required
    async def handle_realm_choice(self, player: Player, event: AstrMessageEvent):
        """处理秘境中的选择，格式：选择 数字"""
        if not player.realm_id:
            yield event.plain_result("你不在任何秘境中。")
            return
        
        if not player.realm_pending_choice:
            yield event.plain_result("当前没有需要做出选择的事件。")
            return
        
        # 解析选择编号
        message_text = event.message_str.strip()
        parts = message_text.split()
        
        if len(parts) < 2:
            yield event.plain_result("请输入：选择 数字（例如：选择 1）")
            return
        
        try:
            choice_num = int(parts[1])
        except ValueError:
            yield event.plain_result("请输入有效的数字。")
            return
        
        # 调用RealmManager处理选择
        success, msg, updated_player, gained_items = await self.realm_manager.handle_player_choice(player, choice_num)
        
        await self.db.update_player(updated_player)
        
        # 处理获得的物品
        if gained_items:
            await self.db.add_items_to_inventory_in_transaction(updated_player.user_id, gained_items)
            item_log = []
            for item_id, qty in gained_items.items():
                item = self.config_manager.item_data.get(str(item_id))
                item_name = item.name if item else "未知物品"
                item_log.append(f"【{item_name}】x{qty}")
            if item_log:
                msg += "\n获得物品：" + ", ".join(item_log)
        
        yield event.plain_result(msg)
