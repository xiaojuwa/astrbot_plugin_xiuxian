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
        success, msg, updated_player = await self.realm_manager.start_session(player, CMD_REALM_ADVANCE)
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

        await self.db.update_player(player)

        yield event.plain_result(f"你已从【{realm_name}】中脱离，回到了大千世界。")