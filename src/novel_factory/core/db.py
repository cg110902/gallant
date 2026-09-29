"""
SQLite Connection Factory - 统一的数据库连接装配

生产环境下多个子系统（版本库/图谱/事件库/伏笔台账）会对同一个物理库文件
各自持有连接。默认配置下这会带来两类真实故障：
1. 并发写入时 `database is locked`（默认 busy_timeout 为 0）；
2. 从非创建线程访问时 `SQLite objects created in a thread...` 报错。

因此所有连接一律经由本工厂创建，统一启用 WAL、busy_timeout 与外键约束。
内存库不启用 WAL（无意义且会报错）。
"""

import sqlite3
from typing import Optional


def connect(db_path: Optional[str], busy_timeout_ms: int = 10_000) -> sqlite3.Connection:
    """创建一个按生产要求调优过的 SQLite 连接"""
    path = db_path or ":memory:"
    conn = sqlite3.connect(path, check_same_thread=False, timeout=busy_timeout_ms / 1000.0)
    conn.row_factory = sqlite3.Row
    try:
        if path != ":memory:":
            # WAL 允许读写并发，显著降低长跑生产中的锁冲突
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        conn.execute("PRAGMA foreign_keys=ON")
    except sqlite3.Error:
        # PRAGMA 失败不应阻断启动，退化为默认配置
        pass
    return conn


class ConcurrentProductionError(Exception):
    """同一部作品被多个生产进程同时写入"""
    pass


class ProductionLock:
    """
    生产写锁（建议锁 / advisory lock）。

    两个进程同时对同一个库生产时，各自持有独立的 HEAD 游标，
    交叉提交会让其中一方的章节从祖先链上脱落——实测 40 章只剩 20 章，
    而且【不报任何错】。静默丢稿是最坏的一类故障，必须前置拦死。

    实现为数据库内的一行租约：持有者写入 PID 与心跳时间，
    超过 stale_after_seconds 未续约则视为残留锁，可被安全接管。
    """

    def __init__(
        self,
        conn: "sqlite3.Connection",
        owner: str,
        stale_after_seconds: float = 300.0,
    ):
        import uuid

        self.conn = conn
        self.owner = owner
        self.stale_after = stale_after_seconds
        # 实例令牌而非 PID：同一个进程里起两个编排器同样会互相踩踏
        # （实测线程并发写 40 章只剩 20 章），不能因为 PID 相同就放行。
        self.instance_token = uuid.uuid4().hex
        self._held = False
        self._init_table()

    def _init_table(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS production_lock (
                    lock_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    instance_token TEXT NOT NULL DEFAULT '',
                    acquired_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL
                )
            """)

    def acquire(self, force: bool = False) -> bool:
        import os
        import time

        now = time.time()
        row = self.conn.execute(
            "SELECT owner, pid, instance_token, heartbeat_at "
            "FROM production_lock WHERE lock_id = 'writer'"
        ).fetchone()

        if row and not force:
            age = now - row["heartbeat_at"]
            same_instance = row["instance_token"] == self.instance_token
            if age < self.stale_after and not same_instance:
                raise ConcurrentProductionError(
                    f"该作品正被另一个生产进程写入 "
                    f"(owner={row['owner']}, pid={row['pid']}, "
                    f"{age:.0f} 秒前活跃)。并发写入会导致章节从版本链上静默脱落。\n"
                    f"若确认那个进程已经死掉，用 force=True / --force-lock 接管。"
                )

        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO production_lock
                (lock_id, owner, pid, instance_token, acquired_at, heartbeat_at)
                VALUES ('writer', ?, ?, ?, ?, ?)
            """, (self.owner, os.getpid(), self.instance_token, now, now))
        self._held = True
        return True

    def heartbeat(self) -> None:
        """长跑期间续约，避免被误判为残留锁"""
        if not self._held:
            return
        import time
        with self.conn:
            self.conn.execute(
                "UPDATE production_lock SET heartbeat_at = ? "
                "WHERE lock_id = 'writer' AND instance_token = ?",
                (time.time(), self.instance_token)
            )

    def release(self) -> None:
        if not self._held:
            return
        try:
            with self.conn:
                self.conn.execute(
                    "DELETE FROM production_lock WHERE lock_id = 'writer' "
                    "AND instance_token = ?",
                    (self.instance_token,)
                )
        except Exception:
            pass
        self._held = False

    @property
    def held(self) -> bool:
        return self._held
