# app/core/omsu_api.py
import httpx
from typing import List, Dict, Any, Optional

# Константы для URL
BASE_URL = "https://eservice.omsu.ru/schedule/backend/"
GROUPS_URL = f"{BASE_URL}dict/groups"
TUTORS_URL = f"{BASE_URL}dict/tutors"
AUDITORIES_URL = f"{BASE_URL}dict/auditories"
SCHEDULE_URL = f"{BASE_URL}schedule/group/"

class OmsuApi:
    """Асинхронный клиент для API ОмГУ."""
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _get_data(self, url: str) -> Optional[List[Dict[str, Any]]]:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            json_response = response.json()
            if json_response.get("success"):
                return json_response.get("data")
            return None
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
            return None

    async def get_groups(self) -> Optional[List[Dict[str, Any]]]:
        return await self._get_data(GROUPS_URL)

    async def get_tutors(self) -> Optional[List[Dict[str, Any]]]:
        return await self._get_data(TUTORS_URL)

    async def get_auditories(self) -> Optional[List[Dict[str, Any]]]:
        return await self._get_data(AUDITORIES_URL)

    async def get_schedule_for_group(self, group_id: int) -> Optional[List[Dict[str, Any]]]:
        return await self._get_data(f"{SCHEDULE_URL}{group_id}")

    async def close(self):
        await self.client.aclose()

api_client = OmsuApi()