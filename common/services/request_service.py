from enum import StrEnum
from logging import getLogger
from typing import Any

import httpx

logger = getLogger(__name__)


class MethodsEnum(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"


class RequestService:
    """Сервис для отправки запросов."""

    async def request(
        self,
        method: MethodsEnum,
        url: str,
        authorization_token: str,
        params: dict[str, Any] | None = None,
        data: Any = None,
        timeout: float = 25,  # noqa: ASYNC109
    ) -> httpx.Response | None:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {authorization_token}",
        }

        try:
            async with httpx.AsyncClient() as client:
                if method == MethodsEnum.POST:
                    return await client.post(
                        url,
                        headers=headers,
                        json=data,
                        params=params,
                        timeout=timeout,
                    )
                if method == MethodsEnum.PUT:
                    return await client.put(
                        url,
                        headers=headers,
                        json=data,
                        params=params,
                        timeout=timeout,
                    )
                if method == MethodsEnum.GET:
                    return await client.get(url, headers=headers, params=params, timeout=timeout)
                if method == MethodsEnum.PATCH:
                    return await client.patch(
                        url,
                        headers=headers,
                        json=data,
                        params=params,
                        timeout=timeout,
                    )

        except Exception as ex:
            msg = f"Error sending request to {url}: {ex}"
            logger.error(msg)
            return None
