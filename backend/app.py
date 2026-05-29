import os
import sys
import logging
import threading
import argparse
import datetime
import time
import jwt
from functools import wraps
from flask import Flask, send_from_directory, jsonify, request, Response, make_response
from flask_cors import CORS
from database.db import Database
from utils.email import EmailBatchProcessor
from utils.import_parser import normalize_outlook_import_line
from utils.mail_pool_importer import sync_mail_pool_directory, get_mail_pool_dir
from utils.mail_pool_cache import MailPoolCache
from ws_server.handler import WebSocketHandler
import asyncio

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("FireMail.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FireMail')

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

# 初始化Flask应用
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})  # 允许跨域请求和凭据

# 增加捕获所有OPTIONS请求的处理方法，支持预检请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """处理所有OPTIONS请求"""
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# JWT密钥
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'huohuo_email_secret_key')

# 打印所有环境变量，帮助调试
print("\n========= 环境变量 =========")
for key, value in os.environ.items():
    if key in ['JWT_SECRET_KEY', 'HOST', 'FLASK_PORT', 'WS_PORT', 'API_URL', 'WS_URL']:
        print(f"{key}: {value}")
print("===========================\n")

# 初始化数据库
db = Database()

# 确保注册功能默认开启，只通过数据库控制
allow_register = db.is_registration_allowed()
logger.info(f"系统启动: 注册功能状态 = {allow_register}")

# 初始化邮件处理器
email_processor = EmailBatchProcessor(db)

# 总邮箱库版本化缓存：只在版本变化时重新加载总表
mail_pool_cache = MailPoolCache(db)

# 初始化WebSocket处理器
ws_handler = WebSocketHandler()
ws_handler.set_dependencies(db, email_processor)

EMAIL_CHECK_ACTION = 'email_check'
EMAIL_CHECK_DAILY_LIMIT = 50
EMAIL_CHECK_MINUTE_LIMIT = 3
CUSTOMER_VISIBLE_SENDER = 'openai.com'


def get_client_ip():
    """获取客户端 IP，优先信任反向代理传入的首个来源 IP。"""
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        first_ip = forwarded_for.split(',')[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get('X-Real-IP', '').strip()
    if real_ip:
        return real_ip

    return request.remote_addr or 'unknown'


def email_check_rate_limited_response(limit_state):
    if limit_state.get('status') == 'mailbox_rate_limited':
        return jsonify({
            'success': False,
            'status': 'mailbox_rate_limited',
            'message': limit_state.get('message') or '同一个邮箱1分钟最多检查3次，请稍后再试',
            'email_id': limit_state.get('email_id'),
            'limit': limit_state.get('limit', EMAIL_CHECK_MINUTE_LIMIT),
            'remaining': limit_state.get('remaining', 0),
            'retry_after': limit_state.get('retry_after'),
            'reset_at': limit_state.get('reset_at')
        }), 429

    return jsonify({
        'success': False,
        'status': 'rate_limited',
        'message': '每天最多只能检查50个邮箱验证码，请明天再试',
        'limit': limit_state.get('limit', EMAIL_CHECK_DAILY_LIMIT),
        'remaining': limit_state.get('remaining', 0),
        'reset_at': limit_state.get('reset_at')
    }), 429

# 用户认证装饰器
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 从请求头或Cookie获取token
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        elif request.cookies.get('token'):
            token = request.cookies.get('token')

        if not token:
            return jsonify({'error': '未认证，请先登录'}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = db.get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': '无效的用户令牌'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': '令牌已过期，请重新登录'}), 401
        except Exception as e:
            logger.error(f"令牌验证失败: {str(e)}")
            return jsonify({'error': '无效的令牌'}), 401

        # 将当前用户信息添加到kwargs
        kwargs['current_user'] = current_user
        return f(*args, **kwargs)

    return decorated

# 管理员权限装饰器
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or not current_user['is_admin']:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)

    return decorated

# 认证相关API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        if not data:
            logger.error("登录请求没有JSON数据")
            return jsonify({'error': '无效的请求数据格式'}), 400

        username = data.get('username')
        password = data.get('password')

        logger.info(f"收到登录请求: 用户名={username}")

        if not username or not password:
            logger.warning("登录失败: 用户名或密码为空")
            return jsonify({'error': '用户名和密码不能为空'}), 400

        user = db.authenticate_user(username, password)
        if not user:
            logger.warning(f"登录失败: 用户名或密码错误, 用户名={username}")
            return jsonify({'error': '用户名或密码错误'}), 401

        # 确保user对象包含所有必要属性
        if 'id' not in user or 'username' not in user or 'is_admin' not in user:
            logger.error(f"用户对象缺少必要字段: {user}")
            return jsonify({'error': '内部服务器错误'}), 500

        # 生成JWT令牌
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'is_admin': user['is_admin'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, JWT_SECRET, algorithm="HS256")

        # 创建响应
        response_data = {
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin']
            }
        }

        logger.info(f"登录成功: 用户名={username}, 用户ID={user['id']}")

        # 创建JSON响应并设置CORS头
        response = make_response(jsonify(response_data))
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST')

        # 设置Cookie
        response.set_cookie(
            'token',
            token,
            httponly=True,
            max_age=7*24*60*60,  # 7天
            secure=False,  # 开发环境设为False，生产环境设为True
            samesite='Lax'
        )

        logger.info(f"用户 {username} 登录成功")
        return response
    except Exception as e:
        logger.error(f"登录过程中发生错误: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    response = make_response(jsonify({'message': '已成功登出'}))
    response.delete_cookie('token')
    return response

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    # 检查系统是否允许注册
    allow_register = db.is_registration_allowed()
    logger.info(f"收到注册请求，当前注册功能状态: {allow_register}")

    if not allow_register:
        logger.warning("注册功能已禁用，拒绝注册请求")
        return jsonify({'error': '注册功能已禁用'}), 403

    client_ip = get_client_ip()
    logger.info(f"注册请求来源IP仅记录日志不做封禁: {client_ip}")

    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    verification_email = (
        data.get('verification_email') or data.get('verificationEmail') or ''
    ).strip().lower()

    logger.info(f"注册用户名: {username}, 验证邮箱: {verification_email or '未填写'}")

    if not username or not password:
        logger.warning("注册失败: 用户名或密码为空")
        return jsonify({'error': '用户名和密码不能为空'}), 400

    if not verification_email:
        logger.warning("注册失败: 未填写总邮箱库验证邮箱")
        return jsonify({'error': '注册验证邮箱不能为空'}), 400

    pool_entry = mail_pool_cache.get(verification_email)
    if not pool_entry:
        logger.warning(f"注册失败: 验证邮箱不在总邮箱库中: {verification_email}")
        return jsonify({'error': '验证邮箱不在可注册邮箱库中'}), 403

    pool_status = str(pool_entry.get('status') or '').lower()
    if pool_status == 'disabled':
        logger.warning(f"注册失败: 验证邮箱已停用: {verification_email}")
        return jsonify({'error': '验证邮箱已停用，不能用于注册'}), 403

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        logger.warning("注册失败: 用户名长度不符合要求")
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        logger.warning("注册失败: 密码长度不符合要求")
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    try:
        # 创建用户
        success, is_admin = db.create_user(username, password)
        if not success:
            logger.warning(f"注册失败: 用户名 {username} 已存在")
            return jsonify({'error': '用户名已存在'}), 409

        logger.info(f"注册成功: 用户名 {username}, 是否管理员: {is_admin}")
        return jsonify({
            'message': '注册成功',
            'username': username,
            'is_admin': is_admin,
            'note': '您是第一个注册的用户，已被自动设置为管理员' if is_admin else ''
        })
    except Exception as e:
        logger.error(f"注册过程出错: {str(e)}")
        return jsonify({'error': f'注册失败: {str(e)}'}), 500

@app.route('/api/auth/user', methods=['GET'])
@token_required
def get_current_user(current_user):
    """获取当前用户信息"""
    return jsonify({
        'id': current_user['id'],
        'username': current_user['username'],
        'is_admin': current_user['is_admin']
    })

@app.route('/api/auth/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """更改当前用户密码"""
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'error': '旧密码和新密码不能为空'}), 400

    # 验证旧密码
    user = db.authenticate_user(current_user['username'], old_password)
    if not user:
        return jsonify({'error': '旧密码不正确'}), 401

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(current_user['id'], new_password)
    if not success:
        return jsonify({'error': '密码更新失败'}), 500

    return jsonify({'message': '密码已成功更新'})

# 用户管理API
@app.route('/api/users', methods=['GET'])
@token_required
@admin_required
def get_all_users(current_user):
    """获取所有用户 (仅管理员)"""
    users = db.get_all_users_with_emails()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@token_required
@admin_required
def create_user(current_user):
    """创建新用户 (仅管理员)"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    is_admin = data.get('is_admin', False)

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    # 创建用户
    success, _ = db.create_user(username, password, is_admin)
    if not success:
        return jsonify({'error': '用户名已存在'}), 409

    return jsonify({
        'message': '用户创建成功',
        'username': username,
        'is_admin': is_admin
    })

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    """删除用户 (仅管理员)"""
    # 检查是否是当前用户
    if user_id == current_user['id']:
        return jsonify({'error': '不能删除自己的账户'}), 400

    # 删除用户
    success = db.delete_user(user_id)
    if not success:
        return jsonify({'error': '删除用户失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 已删除'})

@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@token_required
@admin_required
def reset_user_password(current_user, user_id):
    """重置用户密码 (仅管理员)"""
    data = request.json
    new_password = data.get('new_password')

    if not new_password:
        return jsonify({'error': '新密码不能为空'}), 400

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(user_id, new_password)
    if not success:
        return jsonify({'error': '密码重置失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 的密码已重置'})

# 修改现有API以加入用户认证和授权
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok', 'message': '花火邮箱助手服务正在运行'})

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取系统配置"""
    try:
        # 确保从数据库获取最新的注册状态
        allow_register = db.is_registration_allowed()
        logger.info(f"获取系统配置: 注册功能状态 = {allow_register}")

        config = {
            'allow_register': allow_register,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 设置CORS头，确保前端可以正常访问
        response = jsonify(config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET')

        logger.info(f"返回系统配置: {config}")
        return response
    except Exception as e:
        logger.error(f"获取系统配置出错: {str(e)}")
        # 返回默认配置，确保注册功能默认开启
        default_config = {
            'allow_register': True,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'error': f"配置获取错误: {str(e)}"
        }
        response = jsonify(default_config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

@app.route('/api/emails', methods=['GET'])
@token_required
def get_all_emails(current_user):
    """获取当前用户的所有邮箱"""
    # 普通用户只能获取自己的邮箱，管理员可以获取所有邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])

    return jsonify([dict(email) for email in emails])

@app.route('/api/emails', methods=['POST'])
@token_required
def add_email(current_user):
    """添加新邮箱"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    mail_type = data.get('mail_type', 'outlook')

    if not email or not password:
        return jsonify({'error': '邮箱地址和密码是必需的'}), 400

    # 根据不同邮箱类型验证参数并添加
    if mail_type == 'outlook':
        client_id = data.get('client_id')
        refresh_token = data.get('refresh_token')

        if not client_id or not refresh_token:
            return jsonify({'error': 'Outlook邮箱需要提供Client ID和Refresh Token'}), 400

        success = db.add_email(
            current_user['id'],
            email,
            password,
            client_id,
            refresh_token,
            mail_type
        )
    elif mail_type in ['imap', 'gmail', 'qq']:
        # Gmail和QQ邮箱使用IMAP协议，服务器和端口是固定的
        if mail_type == 'gmail':
            server = 'imap.gmail.com'
            port = 993
        elif mail_type == 'qq':
            server = 'imap.qq.com'
            port = 993
        else:
            server = data.get('server', 'imap.gmail.com')
            port = data.get('port', 993)

        success = db.add_email(
            current_user['id'],
            email,
            password,
            mail_type=mail_type,
            server=server,
            port=port,
            use_ssl=True
        )
    else:
        return jsonify({'error': f'不支持的邮箱类型: {mail_type}'}), 400

    if success:
        return jsonify({'message': f'邮箱 {email} 添加成功'})
    else:
        return jsonify({'error': f'邮箱 {email} 已存在或添加失败'}), 409

@app.route('/api/emails/<int:email_id>', methods=['DELETE'])
@token_required
def delete_email(current_user, email_id):
    """删除邮箱"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱ID {email_id} 不存在或您没有权限'}), 404

    # 停止正在处理的邮箱
    if email_processor.is_email_being_processed(email_id):
        email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_email(email_id, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'邮箱 ID {email_id} 已删除'})

@app.route('/api/emails/batch_delete', methods=['POST'])
@token_required
def batch_delete_emails(current_user):
    """批量删除邮箱"""
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        return jsonify({'error': '未提供邮箱ID'}), 400

    # 停止正在处理的邮箱
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_emails(email_ids, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'已删除 {len(email_ids)} 个邮箱'})

@app.route('/api/emails/<int:email_id>/check', methods=['POST'])
@token_required
def check_email(current_user, email_id):
    """检查指定邮箱的新邮件"""
    try:
        # 获取邮箱信息
        email_info = db.get_email_by_id(email_id)
        if not email_info:
            return jsonify({'error': '邮箱不存在'}), 404

        # 检查邮箱是否属于当前用户
        if email_info['user_id'] != current_user['id']:
            return jsonify({'error': '无权操作此邮箱'}), 403

        # 在提交任务前原子化检查并标记处理中，避免重复入队
        with email_processor.lock:
            if email_id in email_processor.processing_emails:
                logger.info(f"邮箱 ID {email_id} 正在处理中，拒绝重复请求")
                return jsonify({
                    'success': False,
                    'message': '邮箱正在处理中，请稍后再试',
                    'status': 'processing'
                }), 409
            limit_state = db.consume_user_email_check_limits(
                current_user['id'],
                [email_id],
                daily_limit=EMAIL_CHECK_DAILY_LIMIT,
                minute_limit=EMAIL_CHECK_MINUTE_LIMIT,
            )
            if not limit_state.get('allowed'):
                logger.warning(
                    f"邮箱检查被限流: 用户ID={current_user['id']}, 邮箱ID={email_id}, "
                    f"状态={limit_state.get('status')}, 剩余额度={limit_state.get('remaining')}"
                )
                return email_check_rate_limited_response(limit_state)
            email_processor.processing_emails[email_id] = True

        # 创建进度回调
        def progress_callback(progress, message):
            logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")
            # 通过WebSocket发送进度更新
            try:
                # 使用日志记录进度，不尝试调用异步方法
                logger.info(f"向用户 {current_user['id']} 发送邮箱检查进度: {progress}%, {message}")
                # 这里应使用同步方式发送消息，但WSHandler.broadcast_to_user是异步方法
            except Exception as e:
                logger.error(f"发送进度更新失败: {str(e)}")

        # 提交任务到线程池
        try:
            email_processor.manual_thread_pool.submit(
                email_processor._check_email_task,
                email_info,
                progress_callback
            )
        except Exception:
            with email_processor.lock:
                if email_id in email_processor.processing_emails:
                    del email_processor.processing_emails[email_id]
            raise

        logger.info(f"邮箱检查任务已提交: {email_info['email']}")
        return jsonify({
            'success': True,
            'status': 'started',
            'message': f"已开始检查邮箱 {email_info['email']}"
        }), 202

    except Exception as e:
        logger.error(f"检查邮箱失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'检查邮箱失败: {str(e)}'
        }), 500

@app.route('/api/emails/batch_check', methods=['POST'])
@token_required
def batch_check_emails(current_user):
    """批量检查邮箱邮件"""
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        # 如果没有提供 ID，则获取当前用户拥有的所有邮箱
        if current_user['is_admin']:
            emails = db.get_all_emails()
        else:
            emails = db.get_all_emails(current_user['id'])

        email_ids = [email['id'] for email in emails]
    else:
        # 如果提供了ID，验证用户权限
        if not current_user['is_admin']:
            # 获取该用户拥有的邮箱
            owned_emails = db.get_all_emails(current_user['id'])
            owned_ids = [email['id'] for email in owned_emails]
            # 过滤出用户有权限的邮箱ID
            email_ids = [id for id in email_ids if id in owned_ids]

    if not email_ids:
        logger.warning(f"批量检查邮件：未找到邮箱 (用户ID: {current_user['id']})")
        return jsonify({'error': '没有找到邮箱或您没有权限'}), 404

    # 过滤掉已经在处理的邮箱ID
    processing_ids = []
    valid_ids = []
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            processing_ids.append(email_id)
        else:
            valid_ids.append(email_id)

    if processing_ids:
        logger.info(f"批量检查：跳过正在处理的邮箱IDs: {processing_ids}")

    if not valid_ids:
        logger.warning("批量检查邮件：所有选择的邮箱都在处理中")
        return jsonify({
            'message': '所有选择的邮箱都在处理中',
            'processing_ids': processing_ids
        }), 409

    limit_state = db.consume_user_email_check_limits(
        current_user['id'],
        valid_ids,
        daily_limit=EMAIL_CHECK_DAILY_LIMIT,
        minute_limit=EMAIL_CHECK_MINUTE_LIMIT,
    )
    if not limit_state.get('allowed'):
        logger.warning(
            f"批量邮箱检查被限流: 用户ID={current_user['id']}, 请求数量={len(valid_ids)}, "
            f"状态={limit_state.get('status')}, 剩余额度={limit_state.get('remaining')}"
        )
        return email_check_rate_limited_response(limit_state)

    # 记录有效的邮箱ID
    valid_emails = [db.get_email_by_id(email_id)['email'] for email_id in valid_ids if db.get_email_by_id(email_id)]
    logger.info(f"批量检查开始处理 {len(valid_ids)} 个邮箱: {valid_emails} (用户ID: {current_user['id']})")

    # 自定义进度回调
    def progress_callback(email_id, progress, message):
        logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")

    # 启动邮件检查线程
    email_processor.check_emails(valid_ids, progress_callback)

    return jsonify({
        'message': f'开始检查 {len(valid_ids)} 个邮箱',
        'skipped': len(processing_ids),
        'total': len(email_ids)
    })

@app.route('/api/emails/<int:email_id>/mail_records', methods=['GET'])
@token_required
def get_mail_records(current_user, email_id):
    """获取指定邮箱的邮件记录"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

    if current_user['is_admin']:
        mail_records = db.get_mail_records(email_id)
    else:
        mail_records = db.get_mail_records(email_id, sender_filter=CUSTOMER_VISIBLE_SENDER)
    return jsonify([dict(record) for record in mail_records])

@app.route('/api/mail_records/<int:mail_id>/attachments', methods=['GET'])
@token_required
def get_mail_attachments(current_user, mail_id):
    """获取指定邮件的附件列表"""
    try:
        # 先获取邮件信息，验证权限
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        # 验证用户是否有权限访问该邮件
        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权访问此邮件'}), 403

        # 获取附件列表
        attachments = db.get_attachments(mail_id)
        return jsonify([dict(attachment) for attachment in attachments])
    except Exception as e:
        logger.error(f"获取附件列表失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/attachments/<int:attachment_id>/download', methods=['GET'])
@token_required
def download_attachment(current_user, attachment_id):
    """下载附件"""
    try:
        # 获取附件信息
        attachment = db.get_attachment(attachment_id)
        if not attachment:
            return jsonify({'error': '附件不存在'}), 404

        # 验证用户是否有权限下载该附件
        mail_id = attachment['mail_id']
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权下载此附件'}), 403

        # 准备下载响应
        filename = attachment['filename']
        content_type = attachment['content_type']
        content = attachment['content']

        response = make_response(content)
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response
    except Exception as e:
        logger.error(f"下载附件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>/upload_email_file', methods=['POST'])
@token_required
def upload_email_file(current_user, email_id):
    """上传邮件文件并解析"""
    try:
        # 验证用户是否有权限操作该邮箱
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400

        # 检查文件扩展名
        allowed_extensions = ['.eml', '.txt', '.msg', '.mbox', '.emlx']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'不支持的文件格式，仅支持 {", ".join(allowed_extensions)}'}), 400

        # 保存文件到临时目录
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, f"{int(time.time())}_{file.filename}")
        file.save(temp_file_path)

        try:
            # 导入邮件处理模块
            from utils.email import EmailFileParser

            # 解析邮件文件
            mail_record = EmailFileParser.parse_email_file(temp_file_path)

            if not mail_record:
                return jsonify({'error': '解析邮件文件失败'}), 400

            # 保存邮件记录到数据库
            success, mail_id = db.add_mail_record(
                email_id=email_id,
                subject=mail_record.get('subject', '(无主题)'),
                sender=mail_record.get('sender', '(未知发件人)'),
                content=mail_record.get('content', '(无内容)'),
                received_time=mail_record.get('received_time', datetime.now()),
                folder='IMPORTED',
                has_attachments=1 if mail_record.get('has_attachments', False) else 0
            )

            if success and mail_id and mail_record.get('has_attachments', False):
                # 保存附件
                attachments = mail_record.get('full_attachments', [])
                for attachment in attachments:
                    db.add_attachment(
                        mail_id=mail_id,
                        filename=attachment.get('filename', '未命名'),
                        content_type=attachment.get('content_type', 'application/octet-stream'),
                        size=attachment.get('size', 0),
                        content=attachment.get('content', b'')
                    )

            # 删除临时文件
            os.remove(temp_file_path)

            return jsonify({
                'success': True,
                'message': '邮件文件解析成功',
                'mail_id': mail_id
            })

        finally:
            # 确保临时文件被删除
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    except Exception as e:
        logger.error(f"上传邮件文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/import', methods=['POST'])
@token_required
def import_emails(current_user):
    """批量导入邮箱"""
    data = request.json.get('data')
    mail_type = request.json.get('mail_type', 'outlook')

    if not data:
        return jsonify({'error': '未提供导入数据'}), 400

    lines = data.strip().split('\n')
    total = len([line for line in lines if line.strip()])
    success_count = 0
    failed_details = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            if mail_type == 'outlook':
                parsed = normalize_outlook_import_line(line)
                email = parsed['email']
                password = parsed['password']
                client_id = parsed['client_id']
                refresh_token = parsed['refresh_token']
            else:
                parts = [part.strip() for part in line.split('----')]
                if len(parts) != 4:
                    raise ValueError('导入格式错误，应包含 4 个字段')

                email, password, client_id, refresh_token = parts
                if not all([email, password, client_id, refresh_token]):
                    raise ValueError('导入数据不能为空')

            success = db.add_email(current_user['id'], email, password, client_id, refresh_token, mail_type)
            if success:
                success_count += 1
            else:
                failure_reason = '邮箱已存在' if db.email_exists(current_user['id'], email) else '邮箱添加失败'
                failed_details.append({
                    'line': i + 1,
                    'content': line,
                    'reason': failure_reason
                })
        except Exception as e:
            logger.error(f"导入邮箱失败: {str(e)}")
            failed_details.append({
                'line': i + 1,
                'content': line,
                'reason': str(e)
            })

    return jsonify({
        'total': total,
        'success': success_count,
        'failed': len(failed_details),
        'failed_details': failed_details
    })

# 管理员配置 API

@app.route('/api/mail-pool/bind', methods=['POST'])
@token_required
def bind_mail_pool_email(current_user):
    """普通用户按邮箱地址绑定总邮箱库里的邮箱。"""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({'error': '邮箱地址不能为空'}), 400

    pool_entry = mail_pool_cache.get(email)
    if pool_entry:
        result = db.bind_mail_pool_email(current_user['id'], email, entry=pool_entry)
    else:
        result = {'status': 'not_found'}
    status = result.get('status')

    if status in ['bound', 'already_bound']:
        message = '邮箱绑定成功' if status == 'bound' else '邮箱已绑定，无需重复绑定'
        return jsonify({
            'message': message,
            'status': status,
            'email': result.get('email', email),
            'email_id': result.get('email_id')
        }), 200

    if status == 'not_found':
        return jsonify({'error': '该邮箱不在可绑定邮箱库中', 'status': status}), 404

    if status == 'assigned_to_other':
        return jsonify({'error': '该邮箱已被其他用户绑定', 'status': status}), 409

    if status == 'disabled':
        return jsonify({'error': '该邮箱已被禁用，无法绑定', 'status': status}), 409

    if status == 'invalid_email':
        return jsonify({'error': '邮箱地址不能为空', 'status': status}), 400

    if status == 'unsupported_type':
        return jsonify({'error': '该邮箱类型暂不支持绑定', 'status': status}), 400

    logger.error(f"绑定总邮箱库邮箱失败: {result}")
    return jsonify({'error': '绑定邮箱失败', 'status': status}), 500



@app.route('/api/mail-pool/batch-bind', methods=['POST'])
@token_required
def batch_bind_mail_pool_emails(current_user):
    """普通用户批量提交邮箱地址，命中总库后直接绑定到自己的邮箱列表。"""
    data = request.get_json(silent=True) or {}
    raw_emails = data.get('emails', '')

    if isinstance(raw_emails, list):
        emails = [str(item).strip().lower() for item in raw_emails if str(item).strip()]
    else:
        emails = [line.strip().lower() for line in str(raw_emails).splitlines() if line.strip()]

    if not emails:
        return jsonify({'error': '邮箱列表不能为空', 'status': 'invalid_email'}), 400

    if len(emails) > 1000:
        return jsonify({'error': '单次最多绑定 1000 个邮箱', 'status': 'too_many'}), 400

    pool_entries = mail_pool_cache.get_many(emails)

    result = db.bind_mail_pool_emails(
        current_user['id'],
        emails,
        resolver=lambda email: pool_entries.get(email),
    )
    logger.info(
        f"用户 {current_user['username']} 批量绑定总库邮箱: total={result.get('total')}, summary={result.get('summary')}"
    )
    return jsonify(result), 200


@app.route('/api/admin/mail-pool/sync', methods=['POST'])
@token_required
@admin_required
def sync_admin_mail_pool(current_user):
    """管理员手动同步宿主机挂载的总邮箱库目录。"""
    result = sync_mail_pool_directory(db, get_mail_pool_dir())
    logger.info(f"管理员 {current_user['username']} 同步总邮箱库: {result}")
    return jsonify(result)


@app.route('/api/admin/mail-pool/stats', methods=['GET'])
@token_required
@admin_required
def get_admin_mail_pool_stats(current_user):
    """管理员查看总邮箱库统计，不给普通用户开放。"""
    return jsonify(db.get_mail_pool_stats())


@app.route('/api/admin/config/registration', methods=['POST'])
@token_required
@admin_required
def toggle_registration(current_user):
    """管理员开启/关闭注册功能"""
    data = request.json
    allow = data.get('allow', False)

    if db.toggle_registration(allow):
        action = "开启" if allow else "关闭"
        logger.info(f"管理员 {current_user['username']} 已{action}注册功能")
        return jsonify({'message': f'已成功{action}注册功能', 'allow_register': allow})
    else:
        return jsonify({'error': '更新注册配置失败'}), 500

# 前端静态文件服务
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """提供前端静态文件"""
    # 确定前端构建目录的路径
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')

    # 如果路径为空或者是根路径，则返回 index.html
    if not path or path == '/':
        return send_from_directory(frontend_dir, 'index.html')

    # 检查请求的文件是否存在
    file_path = os.path.join(frontend_dir, path)
    if os.path.isfile(file_path):
        return send_from_directory(frontend_dir, path)
    else:
        # 如果文件不存在，返回 index.html 让前端路由处理
        return send_from_directory(frontend_dir, 'index.html')

@app.route('/api/emails/<int:email_id>/password', methods=['GET'])
@token_required
def get_email_password(current_user, email_id):
    """获取指定邮箱的密码"""
    try:
        email = db.get_email_by_id(email_id)
        if not email:
            return jsonify({'error': '邮箱不存在'}), 404

        # 验证是否为当前用户的邮箱或管理员
        if email['user_id'] != current_user['id'] and not current_user['is_admin']:
            return jsonify({'error': '无权访问此邮箱'}), 403

        return jsonify({'password': email['password']})
    except Exception as e:
        logger.error(f"获取邮箱密码失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/search', methods=['POST'])
@token_required
def search_emails(current_user):
    """搜索邮件内容"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': '无效的请求数据格式'}), 400

        query = data.get('query', '').strip()
        search_in = data.get('search_in', [])  # 可以包含 'subject', 'sender', 'recipient', 'content'

        if not query:
            return jsonify({'error': '搜索关键词不能为空'}), 400

        if not search_in:
            search_in = ['subject', 'sender', 'recipient', 'content']  # 默认搜索所有字段

        logger.info(f"用户 {current_user['username']} 执行搜索: {query}, 搜索范围: {search_in}")

        # 获取用户的所有邮箱
        user_emails = db.get_emails_by_user_id(current_user['id'])
        user_email_ids = [email['id'] for email in user_emails]

        # 根据搜索条件查询邮件
        results = db.search_mail_records(
            user_email_ids,
            query,
            search_in_subject='subject' in search_in,
            search_in_sender='sender' in search_in,
            search_in_recipient='recipient' in search_in,
            search_in_content='content' in search_in
        )

        # 增加邮箱信息到结果中
        emails_map = {email['id']: email for email in user_emails}
        for record in results:
            email_id = record.get('email_id')
            if email_id in emails_map:
                record['email_address'] = emails_map[email_id]['email']

        return jsonify({'results': results})
    except Exception as e:
        logger.error(f"搜索邮件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>', methods=['PUT'])
@token_required
def update_email(current_user, email_id):
    """更新邮箱信息"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400

        # 获取当前邮箱信息，用于保留不允许修改的字段
        current_email = db.get_email_by_id(email_id, current_user['id'])
        if not current_email:
            return jsonify({'error': '邮箱不存在或您没有权限修改'}), 404

        # 验证邮箱信息
        required_fields = ['email', 'password']
        for field in required_fields:
            if field not in data and field != 'password':  # 密码可以不修改
                return jsonify({'error': f'缺少必要字段: {field}'}), 400

        # 准备更新数据，保持邮箱类型不变
        update_data = {
            'email': data.get('email'),
            'mail_type': current_email['mail_type']  # 使用已有数据，不允许修改
        }

        # 仅当提供了非空密码时才更新密码
        if data.get('password') and data.get('password') != '******':
            update_data['password'] = data.get('password')

        # 根据不同邮箱类型更新特定字段
        if current_email['mail_type'] == 'outlook':
            if data.get('client_id'):
                update_data['client_id'] = data.get('client_id')
            if data.get('refresh_token'):
                update_data['refresh_token'] = data.get('refresh_token')
        elif current_email['mail_type'] in ['imap', 'gmail', 'qq']:
            if data.get('server'):
                update_data['server'] = data.get('server')
            if data.get('port') is not None:
                update_data['port'] = data.get('port')
            if data.get('use_ssl') is not None:
                update_data['use_ssl'] = data.get('use_ssl')

        # 更新邮箱信息
        success = db.update_email(
            email_id,
            user_id=current_user['id'],
            **update_data
        )

        if not success:
            return jsonify({'error': '更新邮箱信息失败'}), 500

        logger.info(f"用户 {current_user['username']} 更新了邮箱 ID: {email_id}")

        return jsonify({
            'message': '邮箱信息更新成功',
            'data': {
                'email_id': email_id,
                'email': update_data['email'],
                'mail_type': update_data['mail_type']
            }
        }), 200

    except Exception as e:
        logger.error(f"更新邮箱信息失败: {str(e)}")
        return jsonify({'error': '更新邮箱信息失败'}), 500

@app.route('/api/email/start_real_time_check', methods=['POST'])
@token_required
def start_real_time_check(current_user):
    """拒绝启动实时自动收码；系统仅支持用户手动点击检查邮件。"""
    logger.info(f"用户 {current_user['username']} 尝试启动实时自动收码，已拒绝")
    return jsonify({
        'success': False,
        'message': '实时自动收码已关闭，请在前端点击检查邮件手动收码'
    }), 410

@app.route('/api/email/stop_real_time_check', methods=['POST'])
@token_required
def stop_real_time_check(current_user):
    """兼容旧前端：允许停止实时检查，但不会启动任何自动收码。"""
    try:
        success = email_processor.stop_real_time_check()
        if success:
            return jsonify({
                'success': True,
                'message': '实时邮件检查已停止'
            })
        else:
            return jsonify({
                'success': False,
                'message': '实时邮件检查未在运行'
            })
    except Exception as e:
        logger.error(f"停止实时邮件检查失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'停止实时邮件检查失败: {str(e)}'
        })

@app.route('/api/email/add_to_real_time_queue', methods=['POST'])
@token_required
def add_to_real_time_queue(current_user):
    """拒绝加入实时检查队列，避免大量邮箱自动触发 429 限流。"""
    logger.info(f"用户 {current_user['username']} 尝试加入实时检查队列，已拒绝")
    return jsonify({
        'success': False,
        'message': '实时自动收码已关闭，请在前端点击检查邮件手动收码'
    }), 410

@app.route('/api/emails/<int:email_id>/realtime', methods=['POST'])
@token_required
def toggle_email_realtime_check(current_user, email_id):
    """兼容旧实时检查开关：禁止开启，只允许关闭历史开关。"""
    try:
        data = request.json or {}
        enable = data.get('enable', False)

        # 获取当前邮箱信息
        email_info = db.get_email_by_id(email_id, current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或您没有权限'}), 404

        if enable:
            logger.info(f"用户 {current_user['username']} 尝试开启邮箱 {email_info['email']} 的实时自动收码，已拒绝")
            return jsonify({
                'success': False,
                'message': '实时自动收码已关闭，请使用前端检查邮件按钮手动收码'
            }), 410

        # 兼容旧数据：允许用户把历史实时检查开关关闭。
        success = db.set_email_realtime_check(email_id, False)
        if not success:
            return jsonify({'error': '更新实时检查状态失败'}), 500

        logger.info(f"用户 {current_user['username']} 关闭了邮箱 {email_info['email']} 的实时检查")

        return jsonify({
            'success': True,
            'message': '已关闭邮箱的实时检查',
            'data': {
                'email_id': email_id,
                'email': email_info['email'],
                'enable_realtime_check': False
            }
        })
    except Exception as e:
        logger.error(f"切换邮箱实时检查状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'切换邮箱实时检查状态失败: {str(e)}'
        }), 500

def start_mail_pool_auto_sync():
    """启动总邮箱库后台同步：启动立即扫一次，之后按间隔扫描新增文件。"""
    try:
        interval = int(os.environ.get('MAIL_POOL_SCAN_INTERVAL', '300'))
    except ValueError:
        interval = 300

    if interval <= 0:
        logger.info('总邮箱库自动同步已关闭')
        return None

    try:
        result = sync_mail_pool_directory(db, get_mail_pool_dir())
        logger.info(f"\u603b\u90ae\u7bb1\u5e93\u542f\u52a8\u540c\u6b65\u5b8c\u6210: {result}")
    except Exception as e:
        logger.error(f"\u603b\u90ae\u7bb1\u5e93\u542f\u52a8\u540c\u6b65\u5931\u8d25: {str(e)}")

    def worker():
        while True:
            time.sleep(interval)
            try:
                result = sync_mail_pool_directory(db, get_mail_pool_dir())
                logger.info(f"\u603b\u90ae\u7bb1\u5e93\u81ea\u52a8\u540c\u6b65\u5b8c\u6210: {result}")
            except Exception as e:
                logger.error(f"\u603b\u90ae\u7bb1\u5e93\u81ea\u52a8\u540c\u6b65\u5931\u8d25: {str(e)}")

    sync_thread = threading.Thread(target=worker, name='mail-pool-sync')
    sync_thread.daemon = True
    sync_thread.start()
    logger.info(f"总邮箱库自动同步已启动，目录: {get_mail_pool_dir()}, 间隔: {interval}秒")
    return sync_thread


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='花火邮箱助手')
    parser.add_argument('--host', default='0.0.0.0', help='主机地址')
    parser.add_argument('--port', type=int, default=5000, help='HTTP端口')
    parser.add_argument('--ws-port', type=int, default=8765, help='WebSocket端口')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def start_websocket_server():
    """启动WebSocket服务器"""
    try:
        logger.info("启动WebSocket服务器")
        ws_handler.run()
    except Exception as e:
        logger.error(f"WebSocket服务器异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    try:
        args = parse_args()

        # 设置WebSocket端口
        ws_handler.port = args.ws_port

        # 启动WebSocket服务器
        ws_thread = threading.Thread(target=start_websocket_server)
        ws_thread.daemon = True
        ws_thread.start()

        # 启动总邮箱库自动同步
        start_mail_pool_auto_sync()

        # 不启动实时自动收码，避免邮箱数量过多时触发 429 限流
        logger.info("实时自动收码未启动，仅支持前端手动点击检查邮件")

        # 启动Flask应用
        logger.info(f"花火邮箱助手启动于 http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("程序被用户中断，正在关闭...")
    except Exception as e:
        logger.error(f"程序启动异常: {e}")
    finally:
        # 清理资源
        if db:
            db.close()
        logger.info("程序已关闭")
