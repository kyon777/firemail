import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MailPoolCache:
    """总邮箱库版本化内存缓存。

    每次访问只读取数据库里的版本号；版本没有变化时直接使用内存字典，
    避免按用户输入逐条实时查总表。
    """

    def __init__(self, db):
        self.db = db
        self._lock = threading.Lock()
        self._version: Optional[int] = None
        self._entries: Dict[str, dict] = {}

    @staticmethod
    def _normalize_email(email):
        return (email or '').strip().lower()

    def _reload_locked(self, version: int):
        rows = self.db.get_mail_pool_entries_for_cache()
        self._entries = {
            self._normalize_email(row.get('email')): row
            for row in rows
            if self._normalize_email(row.get('email'))
        }
        self._version = version
        logger.info("总邮箱库缓存已刷新: version=%s, count=%s", version, len(self._entries))

    def ensure_fresh(self):
        current_version = self.db.get_mail_pool_version()
        if self._version == current_version:
            return

        with self._lock:
            current_version = self.db.get_mail_pool_version()
            if self._version != current_version:
                self._reload_locked(current_version)

    def get(self, email):
        self.ensure_fresh()
        entry = self._entries.get(self._normalize_email(email))
        return dict(entry) if entry else None

    def get_many(self, emails):
        """一次版本检查后，从内存快照里批量取邮箱记录。"""
        self.ensure_fresh()
        result = {}
        for email in emails or []:
            normalized = self._normalize_email(email)
            if not normalized:
                continue
            entry = self._entries.get(normalized)
            if entry:
                result[normalized] = dict(entry)
        return result

    def invalidate(self):
        with self._lock:
            self._version = None
            self._entries = {}
