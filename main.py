from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from typing import List
import traceback
import re


class JoinGroupDataManager:
    """加群管理数据库管理器"""

    def __init__(self, context: Context):
        """
        初始化加群管理数据库管理器

        Args:
            context: AstrBot上下文
        """
        self.context = context
        self.db = self.context.get_db()

        # 确保数据库中有我们需要的表
        self._ensure_table()

    def _ensure_table(self) -> None:
        """确保数据库中有加群管理表"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS joingroup_manager_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL UNIQUE,
            timestamp INTEGER NOT NULL
        );
        """
        try:
            if hasattr(self.db, "_exec_sql"):
                self.db._exec_sql(create_table_sql)
            else:
                if hasattr(self.db, "execute"):
                    self.db.execute(create_table_sql)
                    if hasattr(self.db, "commit"):
                        self.db.commit()

            # 创建索引
            index_sql = """
            CREATE INDEX IF NOT EXISTS idx_joingroup_user ON joingroup_manager_data (user_id);
            """
            if hasattr(self.db, "_exec_sql"):
                self.db._exec_sql(index_sql)
            else:
                if hasattr(self.db, "execute"):
                    self.db.execute(index_sql)
                    if hasattr(self.db, "commit"):
                        self.db.commit()

            logger.info("加群管理数据表创建成功")
        except Exception as e:
            logger.error(f"创建加群管理数据表失败: {e}")

    def _get_db_cursor(self):
        """获取数据库游标"""
        try:
            return self.db.conn.cursor()
        except Exception as e:
            if hasattr(self.db, "_get_conn") and callable(getattr(self.db, "_get_conn")):
                conn = self.db._get_conn(self.db.db_path)
                return conn.cursor()
            else:
                logger.error(f"无法获取数据库连接: {e}")
                raise

    def add_to_blacklist(self, user_id: str) -> bool:
        """
        将用户添加到黑名单

        Args:
            user_id: 用户ID

        Returns:
            是否添加成功
        """
        try:
            insert_sql = """
            INSERT OR REPLACE INTO joingroup_manager_data (user_id, timestamp)
            VALUES (?, strftime('%s', 'now'))
            """
            cursor = self._get_db_cursor()
            cursor.execute(insert_sql, (user_id,))
            cursor.connection.commit()
            cursor.close()
            logger.info(f"用户 {user_id} 已添加到黑名单")
            return True
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False

    def remove_from_blacklist(self, user_id: str) -> bool:
        """
        将用户从黑名单中移除

        Args:
            user_id: 用户ID

        Returns:
            是否移除成功
        """
        try:
            delete_sql = """
            DELETE FROM joingroup_manager_data 
            WHERE user_id = ?
            """
            cursor = self._get_db_cursor()
            cursor.execute(delete_sql, (user_id,))
            cursor.connection.commit()
            cursor.close()
            logger.info(f"用户 {user_id} 已从黑名单中移除")
            return True
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False

    def is_in_blacklist(self, user_id: str) -> bool:
        """
        检查用户是否在黑名单中

        Args:
            user_id: 用户ID

        Returns:
            是否在黑名单中
        """
        try:
            query_sql = """
            SELECT COUNT(*) FROM joingroup_manager_data
            WHERE user_id = ?
            """
            cursor = self._get_db_cursor()
            cursor.execute(query_sql, (user_id,))
            result = cursor.fetchone()
            cursor.close()
            return result[0] > 0
        except Exception as e:
            logger.error(f"检查黑名单失败: {e}")
            return False

    def get_blacklist(self) -> List[str]:
        """
        获取黑名单列表

        Returns:
            黑名单用户ID列表
        """
        try:
            query_sql = """
            SELECT user_id FROM joingroup_manager_data
            ORDER BY timestamp DESC
            """
            cursor = self._get_db_cursor()
            cursor.execute(query_sql)
            results = cursor.fetchall()
            cursor.close()
            return [row[0] for row in results]
        except Exception as e:
            logger.error(f"获取黑名单列表失败: {e}")
            return []


@register("joingroup manager", "HakimYu", "加群管理插件", "1.0.1")
class JoinGroupManager(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.group_list = config.get("group_list", [])  # 要监控的群聊列表
        self.monitor_groups = set(
            map(str, config.get("monitor_groups", [])))  # 监控QQ号的群聊列表
        self.exclude_words = set(config.get("exclude_words", []))  # 排除词列表
        self.level = config.get("level")
        self.data_manager = JoinGroupDataManager(context)

        # 用于匹配8位以上数字的正则表达式
        self.qq_pattern = re.compile(r'\d{8,}')
        # 用于匹配删除黑名单命令的正则表达式
        self.remove_blacklist_pattern = re.compile(r'^删除黑名单\s*(\d+)$')

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_add(self, event: AstrMessageEvent):
        """处理所有类型的消息事件"""
        # logger.info(f"Received message_obj: {event.message_obj}")
        # 没有 message_obj 或 raw_message 属性时，直接返回
        if not hasattr(event, "message_obj") or not hasattr(event.message_obj, "raw_message"):
            return

        raw_message = event.message_obj.raw_message
        # 处理 raw_message
        if not raw_message or not isinstance(raw_message, dict):
            return
        if raw_message.get("sub_type") != "add" and raw_message.get("sub_type") != "invite":
            return
        if raw_message.get("group_id") in self.group_list:
            return

        logger.info(
            f"收到加群请求: {raw_message.get('user_id')} 请求加入 {raw_message.get('group_id')} ：{raw_message.get('comment')}")
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
        platform = self.context.get_platform(
            filter.PlatformAdapterType.AIOCQHTTP)
        assert isinstance(platform, AiocqhttpAdapter)

        user_id = raw_message.get("user_id")

        # 检查黑名单
        if self.data_manager.is_in_blacklist(str(user_id)):
            logger.info(f"黑名单用户 {user_id} 拒绝加群")
            await platform.get_client().api.set_group_add_request(
                flag=raw_message.get("flag"),
                sub_type=raw_message.get("sub_type"),
                approve=False,
                reason=""
            )
            return

        # 检查等级
        info = await platform.get_client().api.get_stranger_info(user_id=user_id)
        if int(info.get("level")) < int(self.level):
            logger.info(f"等级不足 {user_id} 拒绝加群")
            await platform.get_client().api.set_group_add_request(
                flag=raw_message.get("flag"),
                sub_type=raw_message.get("sub_type"),
                approve=False,
                reason=f"账号风险等级高，请换一个安全等级高的账号"
            )
            return

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def handle_group_message(self, event: AstrMessageEvent):
        """处理群消息，检测QQ号和命令"""
        try:
            # 获取消息内容
            message = event.message_str if hasattr(
                event, "message_str") else None
            if not message:
                return

            logger.info(f"收到群消息: {event.message_obj.raw_message}")

            # 检查是否是删除黑名单命令
            match = self.remove_blacklist_pattern.match(message)
            if match:
                # 检查发送者是否是管理员
                sender_role = event.message_obj.raw_message.get(
                    "sender").get("role")
                if sender_role not in ["admin", "owner"]:
                    yield event.plain_result("只有管理员才能删除黑名单")

                # 获取要删除的QQ号
                qq = match.group(1)
                if not self.data_manager.is_in_blacklist(qq):
                    yield event.plain_result(f"QQ号 {qq} 不在黑名单中")

                # 删除黑名单
                if self.data_manager.remove_from_blacklist(qq):
                    yield event.plain_result(f"已将QQ号 {qq} 从黑名单中删除")
                else:
                    yield event.plain_result(f"删除失败，请稍后重试")

            # 检查是否是监控的群
            group_id = event.get_group_id()
            if not group_id or str(group_id) not in self.monitor_groups:
                return

            # 检查是否包含排除词
            for word in self.exclude_words:
                if word in message:
                    logger.debug(f"消息包含排除词 '{word}'，跳过处理")
                    return

            # 查找消息中的QQ号（8位以上数字）
            qq_numbers = self.qq_pattern.findall(message)
            for qq in qq_numbers:
                if not self.data_manager.is_in_blacklist(qq):
                    logger.info(f"发现QQ号 {qq}，添加到黑名单")
                    try:
                        self.data_manager.add_to_blacklist(qq)
                        yield event.plain_result(f"已将QQ号 {qq} 添加到黑名单")
                    except Exception as e:
                        logger.error(f"添加黑名单失败: {e}")
                else:
                    yield event.plain_result(f"QQ号 {qq} 已在黑名单中")

        except Exception as e:
            logger.error(f"处理群消息时出错: {e}")
            logger.error(traceback.format_exc())
