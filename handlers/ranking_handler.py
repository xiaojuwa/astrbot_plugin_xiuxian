# handlers/ranking_handler.py
"""排行榜处理器 - 提供各类排行榜查询功能"""

from astrbot.api.event import AstrMessageEvent
from ..data import DataBase
from ..config_manager import ConfigManager
from .utils import player_required
from ..models import Player

__all__ = ["RankingHandler"]


class RankingHandler:
    """排行榜相关指令处理器"""

    def __init__(self, db: DataBase, config_manager: ConfigManager):
        self.db = db
        self.config_manager = config_manager

    def _get_display_name(self, player: Player) -> str:
        """获取玩家显示名称（优先昵称，否则显示ID后4位）"""
        if player.nickname:
            return player.nickname
        return f"修士{player.user_id[-4:]}"

    async def handle_realm_ranking(self, event: AstrMessageEvent):
        """境界排行榜 - 按境界和修为排序"""
        players = await self.db.get_top_players_by_realm(limit=10)
        if not players:
            yield event.plain_result("仙界尚无修士，道友可成为第一人！")
            return

        lines = ["━━ 境界排行榜 ━━"]
        for i, player in enumerate(players, 1):
            level_name = player.get_level(self.config_manager)
            medal = self._get_medal(i)
            name = self._get_display_name(player)
            lines.append(f"{medal} {i}. {name} | {level_name} | 修为:{player.experience}")

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    async def handle_wealth_ranking(self, event: AstrMessageEvent):
        """财富排行榜 - 按灵石数量排序"""
        players = await self.db.get_top_players_by_gold(limit=10)
        if not players:
            yield event.plain_result("仙界尚无修士，道友可成为第一人！")
            return

        lines = ["━━ 财富排行榜 ━━"]
        for i, player in enumerate(players, 1):
            medal = self._get_medal(i)
            name = self._get_display_name(player)
            lines.append(f"{medal} {i}. {name} | {player.gold} 灵石")

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    async def handle_combat_ranking(self, event: AstrMessageEvent):
        """战力排行榜 - 按综合战力排序"""
        players = await self.db.get_top_players_by_combat(limit=10, config_manager=self.config_manager)
        if not players:
            yield event.plain_result("仙界尚无修士，道友可成为第一人！")
            return

        lines = ["━━ 战力排行榜 ━━"]
        for i, (player, combat_power) in enumerate(players, 1):
            level_name = player.get_level(self.config_manager)
            medal = self._get_medal(i)
            name = self._get_display_name(player)
            lines.append(f"{medal} {i}. {name} | {level_name} | 战力:{combat_power}")

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    @player_required
    async def handle_my_ranking(self, player: Player, event: AstrMessageEvent):
        """查看自己的排名"""
        realm_rank = await self.db.get_player_realm_rank(player.user_id)
        wealth_rank = await self.db.get_player_wealth_rank(player.user_id)
        combat_rank = await self.db.get_player_combat_rank(player.user_id, self.config_manager)

        lines = [
            f"━━ 道友 {event.get_sender_name()} 的排名 ━━",
            f"境界排名: 第 {realm_rank} 名",
            f"财富排名: 第 {wealth_rank} 名",
            f"战力排名: 第 {combat_rank} 名",
            "━━━━━━━━━━━━"
        ]
        yield event.plain_result("\n".join(lines))

    async def handle_pvp_ranking(self, event: AstrMessageEvent):
        """PVP排行榜 - 按胜场和胜率排序"""
        players = await self.db.get_top_players_by_pvp(limit=10)
        if not players:
            yield event.plain_result("尚无修士参与过切磋，快去挑战其他道友吧！")
            return

        lines = ["━━ PVP排行榜 ━━"]
        for i, player in enumerate(players, 1):
            medal = self._get_medal(i)
            name = self._get_display_name(player)
            total = player.pvp_wins + player.pvp_losses
            win_rate = f"{player.get_pvp_win_rate():.1f}%" if total > 0 else "0%"
            lines.append(f"{medal} {i}. {name} | {player.pvp_wins}胜{player.pvp_losses}负 | 胜率:{win_rate}")

        lines.append("━━━━━━━━━━━━")
        yield event.plain_result("\n".join(lines))

    def _get_medal(self, rank: int) -> str:
        """获取排名奖牌图标"""
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        return medals.get(rank, "  ")
