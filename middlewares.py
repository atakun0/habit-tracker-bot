import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message

class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, limit_seconds: float = 1.0):
        self.limit_seconds = limit_seconds
        self.user_timeouts = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        current_time = time.time()
        
        if user_id in self.user_timeouts:
            if current_time - self.user_timeouts[user_id] < self.limit_seconds:
                return
        
        self.user_timeouts[user_id] = current_time
        
        return await handler(event, data)