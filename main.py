from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig


@register("joingroup manager", "HakimYu", "加群管理插件", "1.0.0")
class JoinGroupManager(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.group_list = config.get("group_list")
        self.black_list = config.get("black_list")
        self.level = config.get("level")

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

        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import AiocqhttpAdapter
        platform = self.context.get_platform(
            filter.PlatformAdapterType.AIOCQHTTP)
        assert isinstance(platform, AiocqhttpAdapter)
        info = await platform.get_client().api.get_stranger_info(user_id=raw_message.get("user_id"))
        if info.get("user_id") in self.black_list:
            platform.get_client().api.set_group_add_request(flag=raw_message.get("flag"),
                                                            sub_type=raw_message.get(
                                                                "sub_type"),
                                                            approve=False)

        if int(info.get("level")) < int(self.level):
            platform.get_client().api.set_group_add_request(flag=raw_message.get("flag"),
                                                            sub_type=raw_message.get(
                                                                "sub_type"),
                                                            approve=False,
                                                            reason=f"账号风险等级高，请换一个安全等级高的账号")
