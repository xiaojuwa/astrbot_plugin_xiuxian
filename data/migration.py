# data/migration.py

import aiosqlite
from typing import Dict, Callable, Awaitable
from astrbot.api import logger
from ..config_manager import ConfigManager

LATEST_DB_VERSION = 19 # v2.6.3 修复realm_pending_choice字段缺失

MIGRATION_TASKS: Dict[int, Callable[[aiosqlite.Connection, ConfigManager], Awaitable[None]]] = {}

def migration(version: int):
    """注册数据库迁移任务的装饰器"""

    def decorator(func: Callable[[aiosqlite.Connection, ConfigManager], Awaitable[None]]):
        MIGRATION_TASKS[version] = func
        return func
    return decorator

class MigrationManager:
    """数据库迁移管理器"""
    
    def __init__(self, conn: aiosqlite.Connection, config_manager: ConfigManager):
        self.conn = conn
        self.config_manager = config_manager

    async def migrate(self):
        await self.conn.execute("PRAGMA foreign_keys = ON")
        async with self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_info'") as cursor:
            if await cursor.fetchone() is None:
                logger.info("未检测到数据库版本，将进行全新安装...")
                await self.conn.execute("BEGIN")
                # 使用最新的建表函数
                await _create_all_tables_v11(self.conn)
                await self.conn.execute("INSERT INTO db_info (version) VALUES (?)", (LATEST_DB_VERSION,))
                await self.conn.commit()
                logger.info(f"数据库已初始化到最新版本: v{LATEST_DB_VERSION}")
                return

        async with self.conn.execute("SELECT version FROM db_info") as cursor:
            row = await cursor.fetchone()
            current_version = row[0] if row else 0

        logger.info(f"当前数据库版本: v{current_version}, 最新版本: v{LATEST_DB_VERSION}")
        if current_version < LATEST_DB_VERSION:
            logger.info("检测到数据库需要升级...")
            for version in sorted(MIGRATION_TASKS.keys()):
                if current_version < version:
                    logger.info(f"正在执行数据库升级: v{current_version} -> v{version} ...")
                    is_v5_migration = (version == 5)
                    try:
                        if is_v5_migration:
                            await self.conn.execute("PRAGMA foreign_keys = OFF")

                        await self.conn.execute("BEGIN")
                        await MIGRATION_TASKS[version](self.conn, self.config_manager)
                        await self.conn.execute("UPDATE db_info SET version = ?", (version,))
                        await self.conn.commit()

                        logger.info(f"v{current_version} -> v{version} 升级成功！")
                        current_version = version
                    except Exception as e:
                        await self.conn.rollback()
                        logger.error(f"数据库 v{current_version} -> v{version} 升级失败，已回滚: {e}", exc_info=True)
                        raise
                    finally:
                        if is_v5_migration:
                            await self.conn.execute("PRAGMA foreign_keys = ON")
            logger.info("数据库升级完成！")
        else:
            logger.info("数据库结构已是最新。")

async def _create_all_tables_v9(conn: aiosqlite.Connection):
    await conn.execute("CREATE TABLE IF NOT EXISTS db_info (version INTEGER NOT NULL)")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            leader_id TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 1,
            funds INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY, level_index INTEGER NOT NULL, spiritual_root TEXT NOT NULL,
            experience INTEGER NOT NULL, gold INTEGER NOT NULL, last_check_in REAL NOT NULL,
            state TEXT NOT NULL, state_start_time REAL NOT NULL, sect_id INTEGER, sect_name TEXT,
            hp INTEGER NOT NULL, max_hp INTEGER NOT NULL, attack INTEGER NOT NULL, defense INTEGER NOT NULL,
            realm_id TEXT, realm_floor INTEGER NOT NULL DEFAULT 0, realm_data TEXT,
            equipped_weapon TEXT, equipped_armor TEXT, equipped_accessory TEXT,
            FOREIGN KEY (sect_id) REFERENCES sects (id) ON DELETE SET NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL, FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE,
            UNIQUE(user_id, item_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS active_world_bosses (
            boss_id TEXT PRIMARY KEY,
            current_hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            spawned_at REAL NOT NULL,
            level_index INTEGER NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_participants (
            boss_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            total_damage INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (boss_id, user_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

@migration(2)
async def _upgrade_v1_to_v2(conn: aiosqlite.Connection, config_manager: ConfigManager):
    await conn.execute("PRAGMA foreign_keys = OFF")
    await conn.execute("ALTER TABLE inventory RENAME TO inventory_old")
    await conn.execute("""
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            item_id TEXT NOT NULL, quantity INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE,
            UNIQUE(user_id, item_id)
        )
    """)
    await conn.execute("INSERT INTO inventory (user_id, item_id, quantity) SELECT user_id, item_id, quantity FROM inventory_old")
    await conn.execute("DROP TABLE inventory_old")
    await conn.execute("PRAGMA foreign_keys = ON")

@migration(3)
async def _upgrade_v2_to_v3(conn: aiosqlite.Connection, config_manager: ConfigManager):
    cursor = await conn.execute("PRAGMA table_info(players)")
    columns = [row['name'] for row in await cursor.fetchall()]
    if 'hp' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN hp INTEGER NOT NULL DEFAULT 100")
    if 'max_hp' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN max_hp INTEGER NOT NULL DEFAULT 100")
    if 'attack' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN attack INTEGER NOT NULL DEFAULT 10")
    if 'defense' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN defense INTEGER NOT NULL DEFAULT 5")

@migration(4)
async def _upgrade_v3_to_v4(conn: aiosqlite.Connection, config_manager: ConfigManager):
    cursor = await conn.execute("PRAGMA table_info(players)")
    columns = [row['name'] for row in await cursor.fetchall()]
    if 'realm_id' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN realm_id TEXT")
    if 'realm_floor' not in columns: await conn.execute("ALTER TABLE players ADD COLUMN realm_floor INTEGER NOT NULL DEFAULT 0")

@migration(5)
async def _upgrade_v4_to_v5(conn: aiosqlite.Connection, config_manager: ConfigManager):
    logger.info("开始执行 v4 -> v5 数据库迁移...")
    
    # --- 新增：在执行任何操作前，检查 'players' 表是否存在 ---
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'") as cursor:
        if await cursor.fetchone() is None:
            logger.warning("在 v4->v5 迁移中未找到 'players' 表，将跳过此迁移步骤。")
            # 直接创建最新结构的表以防万一
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id TEXT PRIMARY KEY, level_index INTEGER NOT NULL, spiritual_root TEXT NOT NULL,
                    experience INTEGER NOT NULL, gold INTEGER NOT NULL, last_check_in REAL NOT NULL,
                    state TEXT NOT NULL, state_start_time REAL NOT NULL, sect_id INTEGER,
                    sect_name TEXT, hp INTEGER NOT NULL, max_hp INTEGER NOT NULL,
                    attack INTEGER NOT NULL, defense INTEGER NOT NULL,
                    realm_id TEXT, realm_floor INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (sect_id) REFERENCES sects (id) ON DELETE SET NULL
                )
            """)
            return

    await conn.execute("ALTER TABLE players RENAME TO players_old_v4")
    await conn.execute("""
        CREATE TABLE players (
            user_id TEXT PRIMARY KEY, level_index INTEGER NOT NULL, spiritual_root TEXT NOT NULL,
            experience INTEGER NOT NULL, gold INTEGER NOT NULL, last_check_in REAL NOT NULL,
            state TEXT NOT NULL, state_start_time REAL NOT NULL, sect_id INTEGER,
            sect_name TEXT, hp INTEGER NOT NULL, max_hp INTEGER NOT NULL,
            attack INTEGER NOT NULL, defense INTEGER NOT NULL,
            realm_id TEXT, realm_floor INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sect_id) REFERENCES sects (id) ON DELETE SET NULL
        )
    """)
    level_name_to_index_map = {info['level_name']: i for i, info in enumerate(config_manager.level_data)}
    async with conn.execute("SELECT * FROM players_old_v4") as cursor:
        async for row in cursor:
            old_data = dict(row)
            level_name = old_data.pop('level', None)
            level_index = level_name_to_index_map.get(level_name, 0)
            
            new_data = {
                'user_id': old_data.get('user_id'),
                'level_index': level_index,
                'spiritual_root': old_data.get('spiritual_root', '未知'),
                'experience': old_data.get('experience', 0),
                'gold': old_data.get('gold', 0),
                'last_check_in': old_data.get('last_check_in', 0.0),
                'state': old_data.get('state', '空闲'),
                'state_start_time': old_data.get('state_start_time', 0.0),
                'sect_id': old_data.get('sect_id'),
                'sect_name': old_data.get('sect_name'),
                'hp': old_data.get('hp', 100),
                'max_hp': old_data.get('max_hp', 100),
                'attack': old_data.get('attack', 10),
                'defense': old_data.get('defense', 5),
                'realm_id': old_data.get('realm_id'),
                'realm_floor': old_data.get('realm_floor', 0)
            }

            columns = ", ".join(new_data.keys())
            placeholders = ", ".join([f":{k}" for k in new_data.keys()])
            await conn.execute(f"INSERT INTO players ({columns}) VALUES ({placeholders})", new_data)
    
    await conn.execute("DROP TABLE players_old_v4")
    logger.info("v4 -> v5 数据库迁移完成！")

@migration(6)
async def _upgrade_v5_to_v6(conn: aiosqlite.Connection, config_manager: ConfigManager):
    logger.info("开始执行 v5 -> v6 数据库迁移...")
    cursor = await conn.execute("PRAGMA table_info(players)")
    columns = [row['name'] for row in await cursor.fetchall()]
    if 'realm_data' not in columns:
        await conn.execute("ALTER TABLE players ADD COLUMN realm_data TEXT")
    logger.info("v5 -> v6 数据库迁移完成！")

@migration(7)
async def _upgrade_v6_to_v7(conn: aiosqlite.Connection, config_manager: ConfigManager):
    logger.info("开始执行 v6 -> v7 数据库迁移...")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_boss (
            id INTEGER PRIMARY KEY, boss_template_id TEXT NOT NULL, current_hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL, generated_at REAL NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL UNIQUE, total_damage INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    logger.info("v6 -> v7 数据库迁移完成！")

@migration(8)
async def _upgrade_v7_to_v8(conn: aiosqlite.Connection, config_manager: ConfigManager):
    logger.info("开始执行 v7 -> v8 数据库迁移...")
    await conn.execute("DROP TABLE IF EXISTS world_boss")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS active_world_bosses (
            boss_id TEXT PRIMARY KEY,
            current_hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            spawned_at REAL NOT NULL,
            level_index INTEGER NOT NULL
        )
    """)
    await conn.execute("DROP TABLE IF EXISTS world_boss_participants")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_participants (
            boss_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            total_damage INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (boss_id, user_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    logger.info("v7 -> v8 数据库迁移完成！")

@migration(9)
async def _upgrade_v8_to_v9(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """为 players 表添加装备列"""
    logger.info("开始执行 v8 -> v9 数据库迁移...")
    async with conn.execute("PRAGMA table_info(players)") as cursor:
        columns = [row['name'] for row in await cursor.fetchall()]
        if 'equipped_weapon' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN equipped_weapon TEXT")
        if 'equipped_armor' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN equipped_armor TEXT")
        if 'equipped_accessory' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN equipped_accessory TEXT")
    logger.info("v8 -> v9 数据库迁移完成！")

@migration(10)
async def _upgrade_v9_to_v10(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """添加每日任务和奇遇系统相关表"""
    logger.info("开始执行 v9 -> v10 数据库迁移...")

    # 每日任务进度表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 每日全勤奖励领取记录
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            UNIQUE(user_id, claim_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 奇遇记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS adventure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            adventure_type TEXT NOT NULL,
            result TEXT,
            reward_gold INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 玩家每日奇遇次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_adventure_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, adventure_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 玩家每日悬赏任务次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bounty_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bounty_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, bounty_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 玩家每日悬赏任务次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bounty_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bounty_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, bounty_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v9 -> v10 数据库迁移完成！")

@migration(11)
async def _upgrade_v10_to_v11(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.3.0: 添加功法、buff、PVP、交易、宗门扩展相关字段"""
    logger.info("开始执行 v10 -> v11 数据库迁移...")

    # 为 players 表添加新字段
    async with conn.execute("PRAGMA table_info(players)") as cursor:
        columns = [row['name'] for row in await cursor.fetchall()]
        
        # 功法系统 - 已学习的功法列表 (JSON)
        if 'learned_skills' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN learned_skills TEXT DEFAULT '[]'")
        
        # Buff系统 - 当前激活的buff (JSON)
        if 'active_buffs' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN active_buffs TEXT DEFAULT '[]'")
        
        # PVP统计
        if 'pvp_wins' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN pvp_wins INTEGER NOT NULL DEFAULT 0")
        if 'pvp_losses' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN pvp_losses INTEGER NOT NULL DEFAULT 0")
        if 'last_pvp_time' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN last_pvp_time REAL NOT NULL DEFAULT 0")
        
        # 宗门贡献度
        if 'sect_contribution' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN sect_contribution INTEGER NOT NULL DEFAULT 0")

    # 为 sects 表添加新字段
    async with conn.execute("PRAGMA table_info(sects)") as cursor:
        sect_columns = [row['name'] for row in await cursor.fetchall()]
        
        if 'exp' not in sect_columns:
            await conn.execute("ALTER TABLE sects ADD COLUMN exp INTEGER NOT NULL DEFAULT 0")
        if 'announcement' not in sect_columns:
            await conn.execute("ALTER TABLE sects ADD COLUMN announcement TEXT DEFAULT ''")

    # 创建交易记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id TEXT NOT NULL,
            to_user_id TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            item_id TEXT,
            quantity INTEGER,
            gold_amount INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (from_user_id) REFERENCES players (user_id) ON DELETE CASCADE,
            FOREIGN KEY (to_user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 创建PVP冷却记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_cooldown (
            user_id TEXT PRIMARY KEY,
            last_pvp_time REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # ===== v2.2.0 缺失的表（奇遇/每日任务/悬赏系统） =====
    
    # 奇遇记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS adventure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            adventure_type TEXT NOT NULL,
            result TEXT,
            reward_gold INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    # 玩家每日奇遇次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_adventure_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, adventure_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    # 玩家每日悬赏任务次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bounty_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bounty_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, bounty_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    # 每日任务进度表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    # 每日任务奖励领取记录
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_claimed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            UNIQUE(user_id, claim_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    # 全勤奖励领取记录
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            UNIQUE(user_id, claim_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v10 -> v11 数据库迁移完成！")

@migration(12)
async def _upgrade_v11_to_v12(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.3.1: 修复v11迁移遗漏的v2.2.0表（奇遇/每日任务/悬赏系统）"""
    logger.info("开始执行 v11 -> v12 数据库迁移...")

    # 创建可能缺失的表（IF NOT EXISTS保证幂等性）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS adventure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            adventure_type TEXT NOT NULL,
            result TEXT,
            reward_gold INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_adventure_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, adventure_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bounty_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bounty_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, bounty_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_claimed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            UNIQUE(user_id, claim_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            UNIQUE(user_id, claim_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v11 -> v12 数据库迁移完成！")

@migration(13)
async def _upgrade_v12_to_v13(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.4.0: 添加炼丹/炼器系统相关字段和表"""
    logger.info("开始执行 v12 -> v13 数据库迁移...")

    # 为 players 表添加炼丹/炼器相关字段
    async with conn.execute("PRAGMA table_info(players)") as cursor:
        columns = [row['name'] for row in await cursor.fetchall()]
        
        if 'alchemy_level' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN alchemy_level INTEGER NOT NULL DEFAULT 1")
        if 'alchemy_exp' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN alchemy_exp INTEGER NOT NULL DEFAULT 0")
        if 'smithing_level' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN smithing_level INTEGER NOT NULL DEFAULT 1")
        if 'smithing_exp' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN smithing_exp INTEGER NOT NULL DEFAULT 0")
        if 'furnace_level' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN furnace_level INTEGER NOT NULL DEFAULT 1")
        if 'forge_level' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN forge_level INTEGER NOT NULL DEFAULT 1")
        if 'unlocked_recipes' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN unlocked_recipes TEXT DEFAULT '[]'")

    # 创建炼制日志表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS crafting_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            craft_type TEXT NOT NULL,
            recipe_id TEXT NOT NULL,
            success INTEGER NOT NULL,
            quality TEXT,
            output_count INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 创建每日回购次数表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_sell_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            sell_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, sell_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v12 -> v13 数据库迁移完成！")

async def _create_all_tables_v11(conn: aiosqlite.Connection):
    """创建所有表（v13版本）- 包含功法、buff、PVP、交易、炼丹/炼器系统"""
    await conn.execute("CREATE TABLE IF NOT EXISTS db_info (version INTEGER NOT NULL)")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS sects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            leader_id TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 1,
            funds INTEGER NOT NULL DEFAULT 0, exp INTEGER NOT NULL DEFAULT 0,
            announcement TEXT DEFAULT ''
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY, level_index INTEGER NOT NULL, spiritual_root TEXT NOT NULL,
            experience INTEGER NOT NULL, gold INTEGER NOT NULL, last_check_in REAL NOT NULL,
            state TEXT NOT NULL, state_start_time REAL NOT NULL, sect_id INTEGER, sect_name TEXT,
            hp INTEGER NOT NULL, max_hp INTEGER NOT NULL, attack INTEGER NOT NULL, defense INTEGER NOT NULL,
            realm_id TEXT, realm_floor INTEGER NOT NULL DEFAULT 0, realm_data TEXT,
            equipped_weapon TEXT, equipped_armor TEXT, equipped_accessory TEXT,
            learned_skills TEXT DEFAULT '[]', active_buffs TEXT DEFAULT '[]',
            pvp_wins INTEGER NOT NULL DEFAULT 0, pvp_losses INTEGER NOT NULL DEFAULT 0,
            last_pvp_time REAL NOT NULL DEFAULT 0, sect_contribution INTEGER NOT NULL DEFAULT 0,
            alchemy_level INTEGER NOT NULL DEFAULT 1, alchemy_exp INTEGER NOT NULL DEFAULT 0,
            smithing_level INTEGER NOT NULL DEFAULT 1, smithing_exp INTEGER NOT NULL DEFAULT 0,
            furnace_level INTEGER NOT NULL DEFAULT 1, forge_level INTEGER NOT NULL DEFAULT 1,
            unlocked_recipes TEXT DEFAULT '[]', realm_pending_choice TEXT,
            FOREIGN KEY (sect_id) REFERENCES sects (id) ON DELETE SET NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL, FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE,
            UNIQUE(user_id, item_id)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS active_world_bosses (
            boss_id TEXT PRIMARY KEY,
            current_hp INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            spawned_at REAL NOT NULL,
            level_index INTEGER NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS world_boss_participants (
            boss_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            total_damage INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (boss_id, user_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 每日任务进度表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 每日全勤奖励领取记录
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            claim_date TEXT NOT NULL,
            UNIQUE(user_id, claim_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 奇遇记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS adventure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            adventure_type TEXT NOT NULL,
            result TEXT,
            reward_gold INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 玩家每日奇遇次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_adventure_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            adventure_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, adventure_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 玩家每日悬赏任务次数限制
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bounty_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bounty_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, bounty_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 交易记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id TEXT NOT NULL,
            to_user_id TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            item_id TEXT,
            quantity INTEGER,
            gold_amount INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (from_user_id) REFERENCES players (user_id) ON DELETE CASCADE,
            FOREIGN KEY (to_user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # PVP冷却记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS pvp_cooldown (
            user_id TEXT PRIMARY KEY,
            last_pvp_time REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 炼制日志表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS crafting_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            craft_type TEXT NOT NULL,
            recipe_id TEXT NOT NULL,
            success INTEGER NOT NULL,
            quality TEXT,
            output_count INTEGER,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 每日回购次数表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_sell_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            sell_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, sell_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # 激活码使用记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS redeem_code_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            code TEXT NOT NULL,
            used_at REAL NOT NULL,
            UNIQUE(user_id, code),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)
    # GM激活码表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gm_redeem_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            gold INTEGER DEFAULT 0,
            exp INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 100,
            description TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
    """)
    # GM激活码物品奖励表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gm_redeem_code_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (code) REFERENCES gm_redeem_codes (code) ON DELETE CASCADE
        )
    """)
    # 每日丹药服用计数表（丹药中毒机制）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_pill_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            pill_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, pill_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

@migration(15)
async def _upgrade_v14_to_v15(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.5.0: 每日任务系统重构 - 添加连续签到、任务进度计数器、玩家昵称等"""
    logger.info("开始执行 v14 -> v15 数据库迁移（每日任务系统重构）...")

    # 为 players 表添加 nickname 字段
    try:
        await conn.execute("ALTER TABLE players ADD COLUMN nickname TEXT DEFAULT ''")
    except aiosqlite.OperationalError:
        pass  # 字段已存在

    # 任务进度计数器表（用于需要多次完成的任务）
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_task_counter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            task_date TEXT NOT NULL,
            task_id TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_id),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 连续签到记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS check_in_streak (
            user_id TEXT PRIMARY KEY,
            streak INTEGER NOT NULL DEFAULT 0,
            last_check_in_date TEXT,
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    # 连续签到奖励领取记录
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_reward_claimed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            streak_milestone INTEGER NOT NULL,
            claimed_at REAL DEFAULT (strftime('%s', 'now')),
            UNIQUE(user_id, streak_milestone),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v14 -> v15 数据库迁移完成！每日任务系统已升级。")

@migration(14)
async def _upgrade_v13_to_v14(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.5.0: 添加激活码使用记录表"""
    logger.info("开始执行 v13 -> v14 数据库迁移（激活码系统）...")

    # 创建激活码使用记录表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS redeem_code_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            code TEXT NOT NULL,
            used_at REAL NOT NULL,
            UNIQUE(user_id, code),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v13 -> v14 数据库迁移完成！激活码系统已添加。")

@migration(16)
async def _upgrade_v15_to_v16(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.5.0: 添加GM激活码管理表"""
    logger.info("开始执行 v15 -> v16 数据库迁移（GM激活码管理）...")

    # 创建GM激活码表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gm_redeem_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            gold INTEGER DEFAULT 0,
            exp INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 100,
            description TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
    """)

    # 创建GM激活码物品奖励表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS gm_redeem_code_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (code) REFERENCES gm_redeem_codes (code) ON DELETE CASCADE
        )
    """)

    logger.info("v14 -> v15 数据库迁移完成！GM激活码管理系统已添加。")

@migration(17)
async def _upgrade_v16_to_v17(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """v2.5.3: 添加丹药中毒机制 - 每日丹药服用计数表"""
    logger.info("开始执行 v16 -> v17 数据库迁移（丹药中毒机制）...")

    # 创建每日丹药服用计数表
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_pill_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            pill_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, pill_date),
            FOREIGN KEY (user_id) REFERENCES players (user_id) ON DELETE CASCADE
        )
    """)

    logger.info("v16 -> v17 数据库迁移完成！丹药中毒机制已添加。")

@migration(18)
async def _upgrade_v17_to_v18(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """添加 realm_pending_choice 字段用于秘境选择事件"""
    logger.info("开始执行 v17 -> v18 数据库迁移（秘境系统重新设计）...")

    # 为 players 表添加 realm_pending_choice 字段
    async with conn.execute("PRAGMA table_info(players)") as cursor:
        columns = [row['name'] for row in await cursor.fetchall()]
        
        if 'realm_pending_choice' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN realm_pending_choice TEXT")
            logger.info("已添加 realm_pending_choice 字段")
        else:
            logger.info("realm_pending_choice 字段已存在，跳过")

    logger.info("v17 -> v18 数据库迁移完成！秘境系统已升级。")

@migration(19)
async def _upgrade_v18_to_v19(conn: aiosqlite.Connection, config_manager: ConfigManager):
    """修复v18迁移 - 确保 realm_pending_choice 字段存在"""
    logger.info("开始执行 v18 -> v19 数据库迁移（修复realm_pending_choice字段）...")

    # 防御性检查：即使版本是v18，也要确保字段存在
    async with conn.execute("PRAGMA table_info(players)") as cursor:
        columns = [row['name'] for row in await cursor.fetchall()]
        
        if 'realm_pending_choice' not in columns:
            await conn.execute("ALTER TABLE players ADD COLUMN realm_pending_choice TEXT")
            logger.info("✅ 已添加缺失的 realm_pending_choice 字段")
        else:
            logger.info("realm_pending_choice 字段已存在")

    logger.info("v18 -> v19 数据库迁移完成！")