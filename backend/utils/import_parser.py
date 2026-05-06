import re


EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def _looks_like_client_id(value):
    return bool(value and UUID_PATTERN.match(value))


def _looks_like_refresh_token(value):
    if not value:
        return False

    return (
        value.startswith('M.')
        or len(value) >= 40
        or any(char in value for char in ['!', '*', '$'])
    )


def normalize_outlook_import_line(line):
    parts = [part.strip() for part in line.split('----')]
    if len(parts) != 4:
        raise ValueError('格式错误，需要4个字段')

    email, password, third, fourth = parts
    if not all(parts):
        raise ValueError('有空白字段')

    if not EMAIL_PATTERN.match(email):
        raise ValueError('邮箱格式不正确')

    is_legacy_order = (
        _looks_like_refresh_token(third)
        and _looks_like_client_id(fourth)
        and not _looks_like_client_id(third)
    )

    if is_legacy_order:
        client_id = fourth
        refresh_token = third
        source_format = 'legacy'
    else:
        client_id = third
        refresh_token = fourth
        source_format = 'standard'

    return {
        'email': email,
        'password': password,
        'client_id': client_id,
        'refresh_token': refresh_token,
        'format': source_format
    }
