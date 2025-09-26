#!/usr/bin/env python3
# 43. scripts/migrate.py
"""
EulerMaker Docker Optimizer 数据迁移脚本

******OSPP-2025-张金荣******

脚本用于管理数据库迁移和数据转换，支持：
- 数据库模式版本控制
- 向前和向后迁移
- 数据备份和恢复
- 配置文件升级
- 批量数据处理
- 迁移状态跟踪
- 错误回滚机制

使用方式：
    python scripts/migrate.py [COMMAND] [OPTIONS]
    python scripts/migrate.py upgrade           # 升级到最新版本
    python scripts/migrate.py downgrade 1.0.0  # 降级到指定版本
    python scripts/migrate.py status            # 查看迁移状态
    python scripts/migrate.py backup            # 备份数据
    python scripts/migrate.py restore backup.db # 恢复数据

版本: 1.0.0
作者: 张金荣
"""

import os
import sys
import json
import sqlite3
import argparse
import logging
import shutil
import hashlib
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    # 尝试导入项目模块
    from config.settings import get_settings
    from utils.logger import get_logger
    from utils.exceptions import APIError
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"警告: 无法导入项目模块: {e}")
    print("某些功能可能不可用")
    IMPORTS_AVAILABLE = False

# ====================================
# 全局配置和常量
# ====================================
SCRIPT_VERSION = "1.0.0"
MIGRATION_TABLE = "schema_migrations"
BACKUP_SUFFIX = ".backup"
TEMP_SUFFIX = ".tmp"

# 迁移状态
class MigrationStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

# ====================================
# 数据模型
# ====================================
@dataclass
class Migration:
    """迁移定义"""
    version: str
    name: str
    description: str
    up_sql: str
    down_sql: str
    checksum: str
    dependencies: List[str]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Migration':
        """从字典创建"""
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)

@dataclass
class MigrationRecord:
    """迁移记录"""
    id: int
    version: str
    name: str
    checksum: str
    status: str
    applied_at: datetime
    rolled_back_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['applied_at'] = self.applied_at.isoformat()
        if self.rolled_back_at:
            data['rolled_back_at'] = self.rolled_back_at.isoformat()
        return data

# ====================================
# 迁移管理器
# ====================================
class MigrationManager:
    """数据迁移管理器"""

    def __init__(self, db_path: str, migrations_dir: Optional[str] = None):
        """
        初始化迁移管理器

        Args:
            db_path: 数据库文件路径
            migrations_dir: 迁移文件目录
        """
        self.db_path = Path(db_path)
        self.migrations_dir = Path(migrations_dir or PROJECT_ROOT / "migrations")
        self.backup_dir = self.db_path.parent / "backups"

        # 创建必要的目录
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # 设置日志
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(f"migrate_{self.db_path.name}")
        logger.setLevel(logging.INFO)

        # 避免重复添加处理器
        if logger.handlers:
            return logger

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 文件处理器
        log_file = PROJECT_ROOT / "logs" / "migration.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        return logger

    @contextmanager
    def get_connection(self):
        """获取数据库连接上下文管理器"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 启用字典式访问
        try:
            yield conn
        finally:
            conn.close()

    def initialize_schema(self):
        """初始化迁移模式表"""
        self.logger.info("初始化迁移模式表...")

        with self.get_connection() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '{MigrationStatus.PENDING}',
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rolled_back_at TIMESTAMP NULL,
                    error_message TEXT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        self.logger.info("迁移模式表初始化完成")

    def load_migrations(self) -> List[Migration]:
        """加载所有迁移文件"""
        self.logger.info(f"从 {self.migrations_dir} 加载迁移文件...")

        migrations = []

        # 查找所有.sql文件
        for migration_file in sorted(self.migrations_dir.glob("*.sql")):
            try:
                migration = self._parse_migration_file(migration_file)
                migrations.append(migration)
                self.logger.debug(f"加载迁移: {migration.version} - {migration.name}")
            except Exception as e:
                self.logger.error(f"解析迁移文件 {migration_file} 失败: {e}")
                continue

        # 查找所有.py文件（Python迁移脚本）
        for migration_file in sorted(self.migrations_dir.glob("*.py")):
            if migration_file.name.startswith("__"):
                continue

            try:
                migration = self._parse_python_migration(migration_file)
                migrations.append(migration)
                self.logger.debug(f"加载Python迁移: {migration.version} - {migration.name}")
            except Exception as e:
                self.logger.error(f"解析Python迁移文件 {migration_file} 失败: {e}")
                continue

        self.logger.info(f"成功加载 {len(migrations)} 个迁移文件")
        return migrations

    def _parse_migration_file(self, file_path: Path) -> Migration:
        """解析SQL迁移文件"""
        content = file_path.read_text(encoding='utf-8')

        # 解析文件头部元数据
        metadata = {}
        up_sql = ""
        down_sql = ""

        lines = content.split('\n')
        current_section = None

        for line in lines:
            line = line.strip()

            if line.startswith('-- @'):
                # 元数据行
                key, value = line[4:].split(':', 1)
                metadata[key.strip()] = value.strip()
            elif line == '-- +migrate Up':
                current_section = 'up'
            elif line == '-- +migrate Down':
                current_section = 'down'
            elif current_section == 'up' and not line.startswith('--'):
                up_sql += line + '\n'
            elif current_section == 'down' and not line.startswith('--'):
                down_sql += line + '\n'

        # 计算校验和
        checksum = hashlib.md5(content.encode()).hexdigest()

        return Migration(
            version=metadata.get('version', file_path.stem),
            name=metadata.get('name', file_path.stem),
            description=metadata.get('description', ''),
            up_sql=up_sql.strip(),
            down_sql=down_sql.strip(),
            checksum=checksum,
            dependencies=metadata.get('dependencies', '').split(',') if metadata.get('dependencies') else [],
            created_at=datetime.now(timezone.utc)
        )

    def _parse_python_migration(self, file_path: Path) -> Migration:
        """解析Python迁移文件"""
        # 动态导入Python迁移模块
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 获取必需的属性
        version = getattr(module, 'VERSION', file_path.stem)
        name = getattr(module, 'NAME', file_path.stem)
        description = getattr(module, 'DESCRIPTION', '')
        dependencies = getattr(module, 'DEPENDENCIES', [])

        # 获取迁移函数
        up_func = getattr(module, 'up', None)
        down_func = getattr(module, 'down', None)

        if not up_func:
            raise ValueError(f"迁移文件 {file_path} 缺少 up() 函数")

        # 计算校验和
        content = file_path.read_text(encoding='utf-8')
        checksum = hashlib.md5(content.encode()).hexdigest()

        return Migration(
            version=version,
            name=name,
            description=description,
            up_sql='',  # Python迁移不使用SQL
            down_sql='',
            checksum=checksum,
            dependencies=dependencies,
            created_at=datetime.now(timezone.utc)
        )

    def get_applied_migrations(self) -> List[MigrationRecord]:
        """获取已应用的迁移记录"""
        with self.get_connection() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM {MIGRATION_TABLE} 
                WHERE status = '{MigrationStatus.COMPLETED}'
                ORDER BY applied_at
            """)

            records = []
            for row in cursor.fetchall():
                records.append(MigrationRecord(
                    id=row['id'],
                    version=row['version'],
                    name=row['name'],
                    checksum=row['checksum'],
                    status=row['status'],
                    applied_at=datetime.fromisoformat(row['applied_at']),
                    rolled_back_at=datetime.fromisoformat(row['rolled_back_at']) if row['rolled_back_at'] else None,
                    error_message=row['error_message']
                ))

            return records

    def get_pending_migrations(self, target_version: Optional[str] = None) -> List[Migration]:
        """获取待应用的迁移"""
        all_migrations = self.load_migrations()
        applied_versions = {record.version for record in self.get_applied_migrations()}

        pending = [m for m in all_migrations if m.version not in applied_versions]

        if target_version:
            # 过滤到目标版本
            pending = [m for m in pending if self._version_compare(m.version, target_version) <= 0]

        # 按版本排序
        pending.sort(key=lambda m: self._version_to_tuple(m.version))

        return pending

    def apply_migration(self, migration: Migration) -> bool:
        """应用单个迁移"""
        self.logger.info(f"应用迁移: {migration.version} - {migration.name}")

        try:
            # 记录迁移开始
            self._record_migration_start(migration)

            # 创建备份
            backup_path = self._create_backup(f"before_{migration.version}")

            with self.get_connection() as conn:
                if migration.up_sql:
                    # SQL迁移
                    conn.executescript(migration.up_sql)
                else:
                    # Python迁移
                    self._execute_python_migration(migration, 'up', conn)

                conn.commit()

            # 记录迁移完成
            self._record_migration_complete(migration)

            self.logger.info(f"迁移 {migration.version} 应用成功")
            return True

        except Exception as e:
            self.logger.error(f"迁移 {migration.version} 应用失败: {e}")

            # 记录迁移失败
            self._record_migration_error(migration, str(e))

            # 尝试恢复备份
            try:
                self._restore_backup(backup_path)
                self.logger.info("已恢复备份")
            except Exception as restore_error:
                self.logger.error(f"恢复备份失败: {restore_error}")

            return False

    def rollback_migration(self, migration: Migration) -> bool:
        """回滚单个迁移"""
        self.logger.info(f"回滚迁移: {migration.version} - {migration.name}")

        try:
            # 创建备份
            backup_path = self._create_backup(f"before_rollback_{migration.version}")

            with self.get_connection() as conn:
                if migration.down_sql:
                    # SQL回滚
                    conn.executescript(migration.down_sql)
                else:
                    # Python回滚
                    self._execute_python_migration(migration, 'down', conn)

                conn.commit()

            # 更新迁移记录
            self._record_migration_rollback(migration)

            self.logger.info(f"迁移 {migration.version} 回滚成功")
            return True

        except Exception as e:
            self.logger.error(f"迁移 {migration.version} 回滚失败: {e}")

            # 尝试恢复备份
            try:
                self._restore_backup(backup_path)
                self.logger.info("已恢复备份")
            except Exception as restore_error:
                self.logger.error(f"恢复备份失败: {restore_error}")

            return False

    def _execute_python_migration(self, migration: Migration, direction: str, conn: sqlite3.Connection):
        """执行Python迁移"""
        migration_file = self.migrations_dir / f"{migration.version}.py"

        # 动态导入模块
        spec = importlib.util.spec_from_file_location(migration.version, migration_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 执行相应的函数
        if direction == 'up':
            up_func = getattr(module, 'up')
            up_func(conn)
        else:
            down_func = getattr(module, 'down', None)
            if down_func:
                down_func(conn)
            else:
                raise ValueError(f"迁移 {migration.version} 不支持回滚")

    def _record_migration_start(self, migration: Migration):
        """记录迁移开始"""
        with self.get_connection() as conn:
            conn.execute(f"""
                INSERT OR REPLACE INTO {MIGRATION_TABLE}
                (version, name, checksum, status, applied_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                migration.version,
                migration.name,
                migration.checksum,
                MigrationStatus.RUNNING,
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def _record_migration_complete(self, migration: Migration):
        """记录迁移完成"""
        with self.get_connection() as conn:
            conn.execute(f"""
                UPDATE {MIGRATION_TABLE}
                SET status = ?, applied_at = ?
                WHERE version = ?
            """, (
                MigrationStatus.COMPLETED,
                datetime.now(timezone.utc).isoformat(),
                migration.version
            ))
            conn.commit()

    def _record_migration_error(self, migration: Migration, error_message: str):
        """记录迁移错误"""
        with self.get_connection() as conn:
            conn.execute(f"""
                UPDATE {MIGRATION_TABLE}
                SET status = ?, error_message = ?
                WHERE version = ?
            """, (
                MigrationStatus.FAILED,
                error_message,
                migration.version
            ))
            conn.commit()

    def _record_migration_rollback(self, migration: Migration):
        """记录迁移回滚"""
        with self.get_connection() as conn:
            conn.execute(f"""
                UPDATE {MIGRATION_TABLE}
                SET status = ?, rolled_back_at = ?
                WHERE version = ?
            """, (
                MigrationStatus.ROLLED_BACK,
                datetime.now(timezone.utc).isoformat(),
                migration.version
            ))
            conn.commit()

    def _create_backup(self, suffix: str) -> Path:
        """创建数据库备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.db_path.stem}_{suffix}_{timestamp}{BACKUP_SUFFIX}"
        backup_path = self.backup_dir / backup_name

        self.logger.info(f"创建备份: {backup_path}")
        shutil.copy2(self.db_path, backup_path)

        return backup_path

    def _restore_backup(self, backup_path: Path):
        """恢复数据库备份"""
        self.logger.info(f"恢复备份: {backup_path}")
        shutil.copy2(backup_path, self.db_path)

    def _version_compare(self, version1: str, version2: str) -> int:
        """比较版本号"""
        v1_tuple = self._version_to_tuple(version1)
        v2_tuple = self._version_to_tuple(version2)

        if v1_tuple < v2_tuple:
            return -1
        elif v1_tuple > v2_tuple:
            return 1
        else:
            return 0

    def _version_to_tuple(self, version: str) -> tuple:
        """将版本号转换为元组以便比较"""
        try:
            # 尝试解析语义化版本号
            parts = version.split('.')
            return tuple(int(part) for part in parts)
        except ValueError:
            # 如果不是数字版本号，则按字符串排序
            return (version,)

# ====================================
# 迁移命令
# ====================================
class MigrationCommands:
    """迁移命令集"""

    def __init__(self, db_path: str, migrations_dir: Optional[str] = None):
        self.manager = MigrationManager(db_path, migrations_dir)
        self.manager.initialize_schema()

    def status(self) -> Dict[str, Any]:
        """获取迁移状态"""
        print("数据库迁移状态")
        print("=" * 50)

        applied_migrations = self.manager.get_applied_migrations()
        pending_migrations = self.manager.get_pending_migrations()
        all_migrations = self.manager.load_migrations()

        status_info = {
            "database_path": str(self.manager.db_path),
            "migrations_dir": str(self.manager.migrations_dir),
            "total_migrations": len(all_migrations),
            "applied_count": len(applied_migrations),
            "pending_count": len(pending_migrations),
            "applied_migrations": [record.to_dict() for record in applied_migrations],
            "pending_migrations": [migration.to_dict() for migration in pending_migrations]
        }

        print(f"数据库文件: {status_info['database_path']}")
        print(f"迁移目录: {status_info['migrations_dir']}")
        print(f"总迁移数: {status_info['total_migrations']}")
        print(f"已应用: {status_info['applied_count']}")
        print(f"待应用: {status_info['pending_count']}")
        print()

        if applied_migrations:
            print("已应用的迁移:")
            for record in applied_migrations:
                print(f"  ✓ {record.version} - {record.name} ({record.applied_at.strftime('%Y-%m-%d %H:%M:%S')})")
            print()

        if pending_migrations:
            print("待应用的迁移:")
            for migration in pending_migrations:
                print(f"  ○ {migration.version} - {migration.name}")
            print()
        else:
            print("所有迁移已应用完成!")

        return status_info

    def upgrade(self, target_version: Optional[str] = None) -> bool:
        """升级数据库到指定版本或最新版本"""
        pending_migrations = self.manager.get_pending_migrations(target_version)

        if not pending_migrations:
            print("没有待应用的迁移")
            return True

        print(f"准备应用 {len(pending_migrations)} 个迁移:")
        for migration in pending_migrations:
            print(f"  • {migration.version} - {migration.name}")

        if not self._confirm("是否继续?"):
            print("迁移已取消")
            return False

        success_count = 0
        for migration in pending_migrations:
            if self.manager.apply_migration(migration):
                success_count += 1
            else:
                print(f"迁移失败，已应用 {success_count}/{len(pending_migrations)} 个迁移")
                return False

        print(f"成功应用 {success_count} 个迁移")
        return True

    def downgrade(self, target_version: str) -> bool:
        """降级数据库到指定版本"""
        applied_migrations = self.manager.get_applied_migrations()

        # 找到需要回滚的迁移
        migrations_to_rollback = []
        for record in reversed(applied_migrations):
            if self.manager._version_compare(record.version, target_version) > 0:
                migrations_to_rollback.append(record)
            else:
                break

        if not migrations_to_rollback:
            print(f"当前版本已经低于或等于目标版本 {target_version}")
            return True

        print(f"准备回滚 {len(migrations_to_rollback)} 个迁移:")
        for record in migrations_to_rollback:
            print(f"  • {record.version} - {record.name}")

        if not self._confirm("是否继续?"):
            print("回滚已取消")
            return False

        # 加载迁移定义以获取回滚脚本
        all_migrations = {m.version: m for m in self.manager.load_migrations()}

        success_count = 0
        for record in migrations_to_rollback:
            migration = all_migrations.get(record.version)
            if not migration:
                print(f"无法找到迁移 {record.version} 的定义")
                return False

            if self.manager.rollback_migration(migration):
                success_count += 1
            else:
                print(f"回滚失败，已回滚 {success_count}/{len(migrations_to_rollback)} 个迁移")
                return False

        print(f"成功回滚 {success_count} 个迁移")
        return True

    def create(self, name: str, migration_type: str = "sql") -> bool:
        """创建新的迁移文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = f"v{timestamp}"

        if migration_type.lower() == "sql":
            filename = f"{version}_{name}.sql"
            template = f"""-- @version: {version}
-- @name: {name}
-- @description: {name}的迁移
-- @dependencies: 

-- +migrate Up
-- 在这里编写升级SQL语句


-- +migrate Down
-- 在这里编写降级SQL语句

"""
        elif migration_type.lower() == "python":
            filename = f"{version}_{name}.py"
            template = f'''"""
{name}的迁移

版本: {version}
创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

VERSION = "{version}"
NAME = "{name}"
DESCRIPTION = "{name}的迁移"
DEPENDENCIES = []


def up(conn):
    """
    升级数据库
    
    Args:
        conn: SQLite数据库连接
    """
    # 在这里编写升级代码
    pass


def down(conn):
    """
    降级数据库
    
    Args:
        conn: SQLite数据库连接
    """
    # 在这里编写降级代码
    pass
'''
        else:
            print(f"不支持的迁移类型: {migration_type}")
            return False

        migration_file = self.manager.migrations_dir / filename

        if migration_file.exists():
            print(f"迁移文件已存在: {migration_file}")
            return False

        migration_file.write_text(template, encoding='utf-8')
        print(f"创建迁移文件: {migration_file}")

        return True

    def backup(self, backup_name: Optional[str] = None) -> bool:
        """创建数据库备份"""
        try:
            suffix = backup_name or "manual"
            backup_path = self.manager._create_backup(suffix)
            print(f"备份创建成功: {backup_path}")
            return True
        except Exception as e:
            print(f"备份创建失败: {e}")
            return False

    def restore(self, backup_path: str) -> bool:
        """从备份恢复数据库"""
        backup_file = Path(backup_path)

        if not backup_file.exists():
            print(f"备份文件不存在: {backup_path}")
            return False

        if not self._confirm(f"这将覆盖当前数据库 {self.manager.db_path}，是否继续?"):
            print("恢复已取消")
            return False

        try:
            self.manager._restore_backup(backup_file)
            print(f"数据库恢复成功: {backup_path} -> {self.manager.db_path}")
            return True
        except Exception as e:
            print(f"数据库恢复失败: {e}")
            return False

    def validate(self) -> bool:
        """验证迁移完整性"""
        print("验证迁移完整性...")

        try:
            all_migrations = self.manager.load_migrations()
            applied_records = self.manager.get_applied_migrations()

            # 检查已应用迁移的校验和
            applied_dict = {record.version: record for record in applied_records}

            issues = []

            for migration in all_migrations:
                if migration.version in applied_dict:
                    record = applied_dict[migration.version]
                    if migration.checksum != record.checksum:
                        issues.append(f"迁移 {migration.version} 校验和不匹配")

            # 检查依赖关系
            for migration in all_migrations:
                for dep in migration.dependencies:
                    if dep not in applied_dict:
                        if dep not in [m.version for m in all_migrations]:
                            issues.append(f"迁移 {migration.version} 依赖的 {dep} 不存在")

            if issues:
                print("发现以下问题:")
                for issue in issues:
                    print(f"  ⚠ {issue}")
                return False
            else:
                print("迁移完整性验证通过")
                return True

        except Exception as e:
            print(f"验证失败: {e}")
            return False

    def _confirm(self, message: str) -> bool:
        """确认提示"""
        try:
            response = input(f"{message} [y/N]: ").strip().lower()
            return response in ('y', 'yes')
        except KeyboardInterrupt:
            print("\n操作已取消")
            return False

# ====================================
# 命令行接口
# ====================================
def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        description="EulerMaker Docker Optimizer 数据迁移工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s status                          # 查看迁移状态
  %(prog)s upgrade                         # 升级到最新版本
  %(prog)s upgrade v20250901_100000        # 升级到指定版本
  %(prog)s downgrade v20250901_100000      # 降级到指定版本
  %(prog)s create add_user_table           # 创建新的SQL迁移
  %(prog)s create add_indexes --type python # 创建新的Python迁移
  %(prog)s backup production               # 创建备份
  %(prog)s restore backup.db               # 恢复备份
  %(prog)s validate                        # 验证迁移完整性
        """
    )

    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "optimizer.db"),
        help="数据库文件路径"
    )

    parser.add_argument(
        "--migrations-dir",
        default=str(PROJECT_ROOT / "migrations"),
        help="迁移文件目录"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出"
    )

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # status命令
    subparsers.add_parser("status", help="查看迁移状态")

    # upgrade命令
    upgrade_parser = subparsers.add_parser("upgrade", help="升级数据库")
    upgrade_parser.add_argument(
        "target_version",
        nargs="?",
        help="目标版本（可选）"
    )

    # downgrade命令
    downgrade_parser = subparsers.add_parser("downgrade", help="降级数据库")
    downgrade_parser.add_argument(
        "target_version",
        help="目标版本"
    )

    # create命令
    create_parser = subparsers.add_parser("create", help="创建新迁移")
    create_parser.add_argument("name", help="迁移名称")
    create_parser.add_argument(
        "--type",
        choices=["sql", "python"],
        default="sql",
        help="迁移类型"
    )

    # backup命令
    backup_parser = subparsers.add_parser("backup", help="创建数据库备份")
    backup_parser.add_argument(
        "name",
        nargs="?",
        help="备份名称（可选）"
    )

    # restore命令
    restore_parser = subparsers.add_parser("restore", help="恢复数据库")
    restore_parser.add_argument("backup_file", help="备份文件路径")

    # validate命令
    subparsers.add_parser("validate", help="验证迁移完整性")

    return parser

def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 创建命令执行器
    try:
        commands = MigrationCommands(args.db, args.migrations_dir)
    except Exception as e:
        print(f"初始化失败: {e}")
        sys.exit(1)

    # 执行命令
    success = True

    try:
        if args.command == "status":
            commands.status()
        elif args.command == "upgrade":
            success = commands.upgrade(args.target_version)
        elif args.command == "downgrade":
            success = commands.downgrade(args.target_version)
        elif args.command == "create":
            success = commands.create(args.name, args.type)
        elif args.command == "backup":
            success = commands.backup(args.name)
        elif args.command == "restore":
            success = commands.restore(args.backup_file)
        elif args.command == "validate":
            success = commands.validate()
        else:
            print(f"未知命令: {args.command}")
            success = False

    except KeyboardInterrupt:
        print("\n操作已取消")
        success = False
    except Exception as e:
        print(f"执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        success = False

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    # 添加必要的导入
    import importlib.util

    main()