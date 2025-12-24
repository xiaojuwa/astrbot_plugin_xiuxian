# data/data_manager.py

import aiosqlite
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import fields

from astrbot.api import logger
from astrbot.api.star import StarTools

from ..config_manager import ConfigManager
from ..models import Player, PlayerEffect, ActiveWorldBoss

class DataBase:
    """数据库管理器，封装所有数据库操作"""
    
    def __init__(self, db_file_name: str):
        data_dir = StarTools.get_data_dir("xiuxian")
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / db_file_name
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            logger.info(f"数据库连接已创建: {self.db_path}")

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("数据库连接已关闭。")

    async def get_active_bosses(self) -> List[ActiveWorldBoss]:
        async with self.conn.execute("SELECT * FROM active_world_bosses") as cursor:
            rows = await cursor.fetchall()
            return [ActiveWorldBoss(**dict(row)) for row in rows]

    async def create_active_boss(self, boss: ActiveWorldBoss):
        await self.conn.execute(
            "INSERT INTO active_world_bosses (boss_id, current_hp, max_hp, spawned_at, level_index) VALUES (?, ?, ?, ?, ?)",
            (boss.boss_id, boss.current_hp, boss.max_hp, boss.spawned_at, boss.level_index)
        )
        await self.conn.commit()

    async def update_active_boss_hp(self, boss_id: str, new_hp: int):
        await self.conn.execute(
            "UPDATE active_world_bosses SET current_hp = ? WHERE boss_id = ?",
            (new_hp, boss_id)
        )
        await self.conn.commit()

    async def delete_active_boss(self, boss_id: str):
        await self.conn.execute("DELETE FROM active_world_bosses WHERE boss_id = ?", (boss_id,))
        await self.conn.commit()

    async def record_boss_damage(self, boss_id: str, user_id: str, user_name: str, damage: int):
        await self.conn.execute("""
            INSERT INTO world_boss_participants (boss_id, user_id, user_name, total_damage) VALUES (?, ?, ?, ?)
            ON CONFLICT(boss_id, user_id) DO UPDATE SET total_damage = total_damage + excluded.total_damage;
        """, (boss_id, user_id, user_name, damage))
        await self.conn.commit()

    async def get_boss_participants(self, boss_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT user_id, user_name, total_damage FROM world_boss_participants WHERE boss_id = ? ORDER BY total_damage DESC"
        async with self.conn.execute(sql, (boss_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_boss_data(self, boss_id: str):
        try:
            await self.conn.execute("BEGIN")
            await self.conn.execute("DELETE FROM active_world_bosses WHERE boss_id = ?", (boss_id,))
            await self.conn.execute("DELETE FROM world_boss_participants WHERE boss_id = ?", (boss_id,))
            await self.conn.commit()
            logger.info(f"Boss {boss_id} 的数据已清理。")
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"清理Boss {boss_id} 数据失败: {e}")

    async def get_top_players(self, limit: int) -> List[Player]:
        async with self.conn.execute(
            "SELECT * FROM players ORDER BY level_index DESC, experience DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

    # ========== 排行榜相关方法 ==========

    async def get_top_players_by_realm(self, limit: int = 10) -> List[Player]:
        """获取境界排行榜（按境界等级和修为排序）"""
        async with self.conn.execute(
            "SELECT * FROM players ORDER BY level_index DESC, experience DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

    async def get_top_players_by_gold(self, limit: int = 10) -> List[Player]:
        """获取财富排行榜（按灵石数量排序）"""
        async with self.conn.execute(
            "SELECT * FROM players ORDER BY gold DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

    async def get_top_players_by_combat(self, limit: int = 10, config_manager: ConfigManager = None) -> List[tuple]:
        """获取战力排行榜（按综合战力排序）"""
        async with self.conn.execute("SELECT * FROM players") as cursor:
            rows = await cursor.fetchall()
            players = [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

        # 计算每个玩家的战力并排序
        player_combat_list = []
        for player in players:
            combat_stats = player.get_combat_stats(config_manager) if config_manager else {
                "attack": player.attack, "defense": player.defense, "max_hp": player.max_hp
            }
            # 战力公式：攻击*2 + 防御*1.5 + 生命*0.1
            combat_power = int(combat_stats["attack"] * 2 + combat_stats["defense"] * 1.5 + combat_stats["max_hp"] * 0.1)
            player_combat_list.append((player, combat_power))

        # 按战力降序排序
        player_combat_list.sort(key=lambda x: x[1], reverse=True)
        return player_combat_list[:limit]

    async def get_player_realm_rank(self, user_id: str) -> int:
        """获取玩家的境界排名"""
        async with self.conn.execute("""
            SELECT COUNT(*) + 1 as rank FROM players p1
            WHERE (p1.level_index > (SELECT level_index FROM players WHERE user_id = ?))
            OR (p1.level_index = (SELECT level_index FROM players WHERE user_id = ?)
                AND p1.experience > (SELECT experience FROM players WHERE user_id = ?))
        """, (user_id, user_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row["rank"] if row else 0

    async def get_player_wealth_rank(self, user_id: str) -> int:
        """获取玩家的财富排名"""
        async with self.conn.execute("""
            SELECT COUNT(*) + 1 as rank FROM players
            WHERE gold > (SELECT gold FROM players WHERE user_id = ?)
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row["rank"] if row else 0

    async def get_player_combat_rank(self, user_id: str, config_manager: ConfigManager = None) -> int:
        """获取玩家的战力排名"""
        player = await self.get_player_by_id(user_id)
        if not player:
            return 0

        combat_stats = player.get_combat_stats(config_manager) if config_manager else {
            "attack": player.attack, "defense": player.defense, "max_hp": player.max_hp
        }
        player_power = int(combat_stats["attack"] * 2 + combat_stats["defense"] * 1.5 + combat_stats["max_hp"] * 0.1)

        # 获取所有玩家并计算战力
        async with self.conn.execute("SELECT * FROM players") as cursor:
            rows = await cursor.fetchall()
            players = [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

        rank = 1
        for p in players:
            p_stats = p.get_combat_stats(config_manager) if config_manager else {
                "attack": p.attack, "defense": p.defense, "max_hp": p.max_hp
            }
            p_power = int(p_stats["attack"] * 2 + p_stats["defense"] * 1.5 + p_stats["max_hp"] * 0.1)
            if p_power > player_power:
                rank += 1

        return rank

    async def get_all_players_count(self) -> int:
        """获取所有玩家数量"""
        async with self.conn.execute("SELECT COUNT(*) as count FROM players") as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_player_by_id(self, user_id: str) -> Optional[Player]:
        async with self.conn.execute("SELECT * FROM players WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._safe_create_player(dict(row))

    def _safe_create_player(self, row_dict: dict) -> Optional[Player]:
        """安全创建Player对象，确保所有字段都有效并添加错误处理"""
        try:
            # 获取Player dataclass的所有有效字段名
            valid_fields = {f.name for f in fields(Player)}
            
            # 只保留Player中定义的字段，过滤掉数据库中可能存在的额外列
            filtered_dict = {k: v for k, v in row_dict.items() if k in valid_fields}
            
            # v2.3.0 新增字段的默认值
            defaults = {
                'learned_skills': '[]',
                'active_buffs': '[]',
                'pvp_wins': 0,
                'pvp_losses': 0,
                'last_pvp_time': 0.0,
                'sect_contribution': 0,
                # 其他可能缺失的旧字段
                'equipped_weapon': None,
                'equipped_armor': None,
                'equipped_accessory': None,
                'realm_id': None,
                'realm_floor': 0,
                'realm_data': None,
                # v2.4.0 炼丹/炼器系统
                'alchemy_level': 1,
                'alchemy_exp': 0,
                'smithing_level': 1,
                'smithing_exp': 0,
                'furnace_level': 1,
                'forge_level': 1,
                'unlocked_recipes': '[]',
            }
            
            # 确保所有必需字段存在且有有效值
            for field, default in defaults.items():
                if field not in filtered_dict or filtered_dict[field] is None:
                    filtered_dict[field] = default
            
            return Player(**filtered_dict)
        except Exception as e:
            from astrbot.api import logger
            logger.error(f"创建Player对象失败: {e}, row_dict keys: {list(row_dict.keys())}")
            return None

    async def create_player(self, player: Player):
        player_fields = [f.name for f in fields(Player)]
        columns = ", ".join(player_fields)
        placeholders = ", ".join([f":{f}" for f in player_fields])
        sql = f"INSERT INTO players ({columns}) VALUES ({placeholders})"
        await self.conn.execute(sql, player.__dict__)
        await self.conn.commit()

    async def update_player(self, player: Player):
        player_fields = [f.name for f in fields(Player) if f.name != 'user_id']
        set_clause = ", ".join([f"{f} = :{f}" for f in player_fields])
        sql = f"UPDATE players SET {set_clause} WHERE user_id = :user_id"
        await self.conn.execute(sql, player.__dict__)
        await self.conn.commit()

    async def update_players_in_transaction(self, players: List[Player]):
        if not players:
            return
        player_fields = [f.name for f in fields(Player) if f.name != 'user_id']
        set_clause = ", ".join([f"{f} = :{f}" for f in player_fields])
        sql = f"UPDATE players SET {set_clause} WHERE user_id = :user_id"
        try:
            await self.conn.execute("BEGIN")
            for player in players:
                await self.conn.execute(sql, player.__dict__)
            await self.conn.commit()
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"批量更新玩家事务失败: {e}")
            raise

    async def create_sect(self, sect_name: str, leader_id: str) -> int:
        async with self.conn.execute("INSERT INTO sects (name, leader_id) VALUES (?, ?)", (sect_name, leader_id)) as cursor:
            await self.conn.commit()
            return cursor.lastrowid

    async def delete_sect(self, sect_id: int):
        await self.conn.execute("DELETE FROM sects WHERE id = ?", (sect_id,))
        await self.conn.commit()

    async def get_sect_by_name(self, sect_name: str) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM sects WHERE name = ?", (sect_name,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_sect_by_id(self, sect_id: int) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT * FROM sects WHERE id = ?", (sect_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_sect_members(self, sect_id: int) -> List[Player]:
        async with self.conn.execute("SELECT * FROM players WHERE sect_id = ?", (sect_id,)) as cursor:
            rows = await cursor.fetchall()
            return [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

    async def update_player_sect(self, user_id: str, sect_id: Optional[int], sect_name: Optional[str]):
        await self.conn.execute("UPDATE players SET sect_id = ?, sect_name = ? WHERE user_id = ?", (sect_id, sect_name, user_id))
        await self.conn.commit()

    async def get_inventory_by_user_id(self, user_id: str, config_manager: ConfigManager) -> List[Dict[str, Any]]:
        async with self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            inventory_list = []
            for row in rows:
                item_id, quantity = row['item_id'], row['quantity']
                item_info = config_manager.item_data.get(str(item_id))
                if item_info:
                     inventory_list.append({
                        "item_id": item_id, "name": item_info.name,
                        "quantity": quantity, "description": item_info.description,
                        "rank": item_info.rank, "type": item_info.type
                    })
                else:
                    inventory_list.append({
                        "item_id": item_id, "name": f"未知物品(ID:{item_id})",
                        "quantity": quantity, "description": "此物品信息已丢失",
                        "rank": "未知", "type": "未知"
                    })
            return inventory_list

    async def get_item_from_inventory(self, user_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        async with self.conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def add_items_to_inventory_in_transaction(self, user_id: str, items: Dict[str, int]):
        try:
            await self.conn.execute("BEGIN")
            for item_id, quantity in items.items():
                await self.conn.execute("""
                    INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
                    ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity;
                """, (user_id, item_id, quantity))
            await self.conn.commit()
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"批量添加物品事务失败: {e}")
            raise

    async def remove_item_from_inventory(self, user_id: str, item_id: str, quantity: int = 1) -> bool:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute("""
                UPDATE inventory SET quantity = quantity - ?
                WHERE user_id = ? AND item_id = ? AND quantity >= ?
            """, (quantity, user_id, item_id, quantity))

            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False

            await self.conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, item_id))
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"移除物品事务失败: {e}")
            return False

    async def transactional_buy_item(self, user_id: str, item_id: str, quantity: int, total_cost: int) -> Tuple[bool, str]:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute(
                "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
                (total_cost, user_id, total_cost)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False, "ERROR_INSUFFICIENT_FUNDS"

            await self.conn.execute("""
                INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity;
            """, (user_id, item_id, quantity))

            await self.conn.commit()
            return True, "SUCCESS"
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"购买物品事务失败: {e}")
            return False, "ERROR_DATABASE"

    async def transactional_apply_item_effect(self, user_id: str, item_id: str, quantity: int, effect: PlayerEffect) -> bool:
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ? AND quantity >= ?",
                (quantity, user_id, item_id, quantity)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False

            await self.conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, item_id))

            await self.conn.execute(
                """
                UPDATE players
                SET experience = experience + ?,
                    gold = gold + ?,
                    hp = MIN(max_hp, hp + ?)
                WHERE user_id = ?
                """,
                (effect.experience, effect.gold, effect.hp, user_id)
            )
            await self.conn.commit()
            return True
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"使用物品事务失败: {e}")
            return False

    # ========== 每日任务相关方法 ==========

    async def get_daily_task_progress(self, user_id: str, task_date: str) -> Dict[str, bool]:
        """获取玩家当日任务完成进度"""
        async with self.conn.execute(
            "SELECT task_id, completed FROM daily_task_progress WHERE user_id = ? AND task_date = ?",
            (user_id, task_date)
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["task_id"]: bool(row["completed"]) for row in rows}

    async def complete_daily_task(self, user_id: str, task_date: str, task_id: str):
        """标记每日任务为已完成"""
        await self.conn.execute("""
            INSERT INTO daily_task_progress (user_id, task_date, task_id, completed)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, task_date, task_id) DO UPDATE SET completed = 1
        """, (user_id, task_date, task_id))
        await self.conn.commit()

    async def get_claimed_daily_tasks(self, user_id: str, task_date: str) -> List[str]:
        """获取已领取奖励的任务列表"""
        async with self.conn.execute(
            "SELECT task_id FROM daily_task_progress WHERE user_id = ? AND task_date = ? AND claimed = 1",
            (user_id, task_date)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row["task_id"] for row in rows]

    async def mark_daily_task_claimed(self, user_id: str, task_date: str, task_id: str):
        """标记任务奖励已领取"""
        await self.conn.execute("""
            UPDATE daily_task_progress SET claimed = 1
            WHERE user_id = ? AND task_date = ? AND task_id = ?
        """, (user_id, task_date, task_id))
        await self.conn.commit()

    async def is_daily_bonus_claimed(self, user_id: str, claim_date: str) -> bool:
        """检查全勤奖励是否已领取"""
        async with self.conn.execute(
            "SELECT 1 FROM daily_bonus_claimed WHERE user_id = ? AND claim_date = ?",
            (user_id, claim_date)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_daily_bonus_claimed(self, user_id: str, claim_date: str):
        """标记全勤奖励已领取"""
        await self.conn.execute(
            "INSERT OR IGNORE INTO daily_bonus_claimed (user_id, claim_date) VALUES (?, ?)",
            (user_id, claim_date)
        )
        await self.conn.commit()

    async def get_task_counter(self, user_id: str, task_date: str, task_id: str) -> int:
        """获取任务进度计数器（用于需要多次完成的任务）"""
        async with self.conn.execute(
            "SELECT progress FROM daily_task_counter WHERE user_id = ? AND task_date = ? AND task_id = ?",
            (user_id, task_date, task_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row["progress"] if row else 0

    async def set_task_counter(self, user_id: str, task_date: str, task_id: str, progress: int):
        """设置任务进度计数器"""
        await self.conn.execute("""
            INSERT INTO daily_task_counter (user_id, task_date, task_id, progress)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, task_date, task_id) DO UPDATE SET progress = ?
        """, (user_id, task_date, task_id, progress, progress))
        await self.conn.commit()

    async def get_check_in_streak(self, user_id: str) -> int:
        """获取连续签到天数"""
        async with self.conn.execute(
            "SELECT streak FROM check_in_streak WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["streak"] if row else 0

    async def update_check_in_streak(self, user_id: str, streak: int, last_date: str):
        """更新连续签到记录"""
        await self.conn.execute("""
            INSERT INTO check_in_streak (user_id, streak, last_check_in_date)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET streak = ?, last_check_in_date = ?
        """, (user_id, streak, last_date, streak, last_date))
        await self.conn.commit()

    async def get_last_check_in_date(self, user_id: str) -> Optional[str]:
        """获取上次签到日期"""
        async with self.conn.execute(
            "SELECT last_check_in_date FROM check_in_streak WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["last_check_in_date"] if row else None

    async def is_streak_reward_claimed(self, user_id: str, streak: int) -> bool:
        """检查连续签到奖励是否已领取"""
        async with self.conn.execute(
            "SELECT 1 FROM streak_reward_claimed WHERE user_id = ? AND streak_milestone = ?",
            (user_id, streak)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_streak_reward_claimed(self, user_id: str, streak: int):
        """标记连续签到奖励已领取"""
        await self.conn.execute(
            "INSERT OR IGNORE INTO streak_reward_claimed (user_id, streak_milestone) VALUES (?, ?)",
            (user_id, streak)
        )
        await self.conn.commit()

    # ========== 奇遇系统相关方法 ==========

    async def get_daily_adventure_count(self, user_id: str, adventure_date: str) -> int:
        """获取玩家当日奇遇次数"""
        async with self.conn.execute(
            "SELECT count FROM daily_adventure_count WHERE user_id = ? AND adventure_date = ?",
            (user_id, adventure_date)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def increment_adventure_count(self, user_id: str, adventure_date: str):
        """增加玩家当日奇遇次数"""
        await self.conn.execute("""
            INSERT INTO daily_adventure_count (user_id, adventure_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, adventure_date) DO UPDATE SET count = count + 1
        """, (user_id, adventure_date))
        await self.conn.commit()

    async def add_adventure_log(self, user_id: str, adventure_date: str, adventure_type: str,
                                 result: str, reward_gold: int, reward_exp: int, created_at: float):
        """添加奇遇记录"""
        await self.conn.execute("""
            INSERT INTO adventure_log (user_id, adventure_date, adventure_type, result, reward_gold, reward_exp, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, adventure_date, adventure_type, result, reward_gold, reward_exp, created_at))
        await self.conn.commit()

    # ========== 悬赏任务相关方法 ==========

    async def get_daily_bounty_count(self, user_id: str, bounty_date: str) -> int:
        """获取玩家当日悬赏任务完成次数"""
        async with self.conn.execute(
            "SELECT count FROM daily_bounty_count WHERE user_id = ? AND bounty_date = ?",
            (user_id, bounty_date)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def increment_bounty_count(self, user_id: str, bounty_date: str):
        """增加玩家当日悬赏任务完成次数"""
        await self.conn.execute("""
            INSERT INTO daily_bounty_count (user_id, bounty_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, bounty_date) DO UPDATE SET count = count + 1
        """, (user_id, bounty_date))
        await self.conn.commit()

    # ========== 交易系统相关方法 ==========

    async def record_trade(self, from_user_id: str, to_user_id: str, trade_type: str,
                          item_id: str = None, quantity: int = None, gold_amount: int = 0):
        """记录交易日志"""
        import time
        await self.conn.execute("""
            INSERT INTO trade_log (from_user_id, to_user_id, trade_type, item_id, quantity, gold_amount, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (from_user_id, to_user_id, trade_type, item_id, quantity, gold_amount, time.time()))
        await self.conn.commit()

    # ========== PVP排行榜相关方法 ==========

    async def get_top_players_by_pvp(self, limit: int = 10) -> List[Player]:
        """获取PVP排行榜（按胜场和胜率排序）"""
        async with self.conn.execute(
            "SELECT * FROM players WHERE pvp_wins + pvp_losses > 0 ORDER BY pvp_wins DESC, pvp_losses ASC LIMIT ?", 
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [p for p in (self._safe_create_player(dict(row)) for row in rows) if p is not None]

    async def get_player_pvp_rank(self, user_id: str) -> int:
        """获取玩家的PVP排名"""
        player = await self.get_player_by_id(user_id)
        if not player or (player.pvp_wins + player.pvp_losses == 0):
            return 0
        
        async with self.conn.execute("""
            SELECT COUNT(*) + 1 as rank FROM players
            WHERE pvp_wins > (SELECT pvp_wins FROM players WHERE user_id = ?)
            OR (pvp_wins = (SELECT pvp_wins FROM players WHERE user_id = ?)
                AND pvp_losses < (SELECT pvp_losses FROM players WHERE user_id = ?))
        """, (user_id, user_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row["rank"] if row else 0

    # ========== 宗门扩展相关方法 ==========

    async def donate_to_sect(self, user_id: str, sect_id: int, amount: int) -> bool:
        """捐献灵石给宗门，增加贡献度和宗门资金"""
        try:
            await self.conn.execute("BEGIN")
            # 扣除玩家灵石
            cursor = await self.conn.execute(
                "UPDATE players SET gold = gold - ?, sect_contribution = sect_contribution + ? WHERE user_id = ? AND gold >= ?",
                (amount, amount, user_id, amount)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False
            
            # 增加宗门资金和经验
            await self.conn.execute(
                "UPDATE sects SET funds = funds + ?, exp = exp + ? WHERE id = ?",
                (amount, amount // 10, sect_id)
            )
            await self.conn.commit()
            return True
        except Exception as e:
            await self.conn.rollback()
            logger.error(f"宗门捐献失败: {e}")
            return False

    async def get_sect_info(self, sect_id: int) -> Optional[Dict[str, Any]]:
        """获取宗门详细信息（包含等级计算）"""
        sect = await self.get_sect_by_id(sect_id)
        if not sect:
            return None
        
        # 计算宗门等级（每10000经验升一级）
        exp = sect.get('exp', 0)
        level = 1 + exp // 10000
        
        members = await self.get_sect_members(sect_id)
        
        return {
            **sect,
            'calculated_level': level,
            'member_count': len(members),
            'members': members
        }

    # ========== 炼丹/炼器系统相关方法 ==========

    async def record_crafting(self, user_id: str, craft_type: str, recipe_id: str, 
                              success: bool, quality: str, output_count: int):
        """记录炼制日志"""
        import time
        await self.conn.execute("""
            INSERT INTO crafting_log (user_id, craft_type, recipe_id, success, quality, output_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, craft_type, recipe_id, 1 if success else 0, quality, output_count, time.time()))
        await self.conn.commit()

    async def get_daily_sell_count(self, user_id: str, sell_date: str) -> int:
        """获取玩家当日回购次数"""
        async with self.conn.execute(
            "SELECT count FROM daily_sell_count WHERE user_id = ? AND sell_date = ?",
            (user_id, sell_date)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def increment_sell_count(self, user_id: str, sell_date: str):
        """增加玩家当日回购次数"""
        await self.conn.execute("""
            INSERT INTO daily_sell_count (user_id, sell_date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, sell_date) DO UPDATE SET count = count + 1
        """, (user_id, sell_date))
        await self.conn.commit()

    async def transactional_sell_item(self, user_id: str, item_id: str, quantity: int, total_price: int) -> Tuple[bool, str]:
        """出售物品事务"""
        try:
            await self.conn.execute("BEGIN")
            cursor = await self.conn.execute(
                "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ? AND quantity >= ?",
                (quantity, user_id, item_id, quantity)
            )
            if cursor.rowcount == 0:
                await self.conn.rollback()
                return False, "ERROR_INSUFFICIENT_ITEMS"

            await self.conn.execute("DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", (user_id, item_id))
            await self.conn.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (total_price, user_id)
            )
            await self.conn.commit()
            return True, "SUCCESS"
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"出售物品事务失败: {e}")
            return False, "ERROR_DATABASE"

    async def transactional_craft_item(self, user_id: str, materials: Dict[str, int], 
                                        output_id: str, output_count: int) -> Tuple[bool, str]:
        """炼制物品事务 - 消耗材料，产出物品"""
        try:
            await self.conn.execute("BEGIN")
            
            # 检查并消耗所有材料
            for item_id, quantity in materials.items():
                cursor = await self.conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ? AND quantity >= ?",
                    (quantity, user_id, item_id, quantity)
                )
                if cursor.rowcount == 0:
                    await self.conn.rollback()
                    return False, f"ERROR_INSUFFICIENT_MATERIAL_{item_id}"
                
                await self.conn.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", 
                    (user_id, item_id)
                )
            
            # 添加产出物品
            await self.conn.execute("""
                INSERT INTO inventory (user_id, item_id, quantity) VALUES (?, ?, ?)
                ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity;
            """, (user_id, output_id, output_count))
            
            await self.conn.commit()
            return True, "SUCCESS"
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"炼制物品事务失败: {e}")
            return False, "ERROR_DATABASE"

    async def transactional_craft_fail(self, user_id: str, materials: Dict[str, int], 
                                        loss_ratio: float = 0.5) -> Tuple[bool, str]:
        """炼制失败事务 - 消耗部分材料"""
        try:
            await self.conn.execute("BEGIN")
            
            for item_id, quantity in materials.items():
                loss_count = max(1, int(quantity * loss_ratio))
                cursor = await self.conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND item_id = ? AND quantity >= ?",
                    (loss_count, user_id, item_id, loss_count)
                )
                if cursor.rowcount == 0:
                    await self.conn.rollback()
                    return False, f"ERROR_INSUFFICIENT_MATERIAL_{item_id}"
                
                await self.conn.execute(
                    "DELETE FROM inventory WHERE user_id = ? AND item_id = ? AND quantity <= 0", 
                    (user_id, item_id)
                )
            
            await self.conn.commit()
            return True, "SUCCESS"
        except aiosqlite.Error as e:
            await self.conn.rollback()
            logger.error(f"炼制失败事务失败: {e}")
            return False, "ERROR_DATABASE"

    async def check_materials(self, user_id: str, materials: Dict[str, int]) -> Tuple[bool, List[str]]:
        """检查玩家是否拥有足够的材料"""
        missing = []
        for item_id, required in materials.items():
            item = await self.get_item_from_inventory(user_id, item_id)
            if not item or item['quantity'] < required:
                missing.append(item_id)
        return len(missing) == 0, missing

    # ========== 激活码系统相关方法 ==========

    async def has_used_redeem_code(self, user_id: str, code: str) -> bool:
        """检查玩家是否已使用过某激活码"""
        async with self.conn.execute(
            "SELECT 1 FROM redeem_code_usage WHERE user_id = ? AND code = ?",
            (user_id, code)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def get_redeem_code_use_count(self, code: str) -> int:
        """获取激活码已使用次数"""
        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM redeem_code_usage WHERE code = ?",
            (code,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def record_redeem_code_use(self, user_id: str, code: str):
        """记录激活码使用"""
        import time
        await self.conn.execute(
            "INSERT INTO redeem_code_usage (user_id, code, used_at) VALUES (?, ?, ?)",
            (user_id, code, time.time())
        )
        await self.conn.commit()