# app/services/notification_service.py

class NotificationService:
    async def send_schedule_update(self, user_id: int, message: str):
        # Здесь будет логика отправки сообщения через Aiogram
        # Пока просто выводим в консоль
notification_service = NotificationService()