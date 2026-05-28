import os
from pathlib import Path

from utils.import_parser import normalize_outlook_import_line

SUPPORTED_EXTENSIONS = {'.txt', '.csv'}
DEFAULT_MAIL_POOL_DIR = '/app/mail'


def get_mail_pool_dir():
    return os.environ.get('MAIL_POOL_DIR', DEFAULT_MAIL_POOL_DIR)


def _iter_pool_files(directory):
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return []

    return sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def sync_mail_pool_directory(db, directory=None):
    """扫描总邮箱库目录，把有效邮箱凭据导入 mail_pool。

    只导入到独立总库表，不写入普通用户 emails 表。
    支持每行一个 Outlook 导出格式：
    - email----password----client_id----refresh_token
    - email----password----refresh_token----client_id
    """
    directory = directory or get_mail_pool_dir()
    result = {
        'directory': directory,
        'total': 0,
        'imported': 0,
        'skipped': 0,
        'failed': 0,
        'failed_details': []
    }

    for file_path in _iter_pool_files(directory):
        try:
            lines = file_path.read_text(encoding='utf-8-sig').splitlines()
        except UnicodeDecodeError:
            lines = file_path.read_text(encoding='gb18030', errors='replace').splitlines()
        except Exception as exc:
            result['failed'] += 1
            result['failed_details'].append({
                'file': file_path.name,
                'line': 0,
                'reason': f'读取文件失败: {exc}'
            })
            continue

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            result['total'] += 1
            try:
                parsed = normalize_outlook_import_line(line)
                imported, reason = db.add_mail_pool_entry(
                    parsed['email'],
                    parsed['password'],
                    parsed['client_id'],
                    parsed['refresh_token'],
                    mail_type='outlook',
                    source_file=file_path.name
                )
                if imported:
                    result['imported'] += 1
                elif reason == 'duplicate':
                    result['skipped'] += 1
                else:
                    result['failed'] += 1
                    result['failed_details'].append({
                        'file': file_path.name,
                        'line': line_no,
                        'content': line,
                        'reason': reason
                    })
            except Exception as exc:
                result['failed'] += 1
                result['failed_details'].append({
                    'file': file_path.name,
                    'line': line_no,
                    'content': line,
                    'reason': str(exc)
                })

    return result
