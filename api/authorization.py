from logging import getLogger

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from api.constants.authorization import AuthorizationEnum
from api.constants.user_roles import UserRoleEnum
from common.environment import API_TOKEN
from common.exceptions import AuthorizationException

logger = getLogger(__name__)

class Authorization:
    def __init__(
        self,
        auth_type: AuthorizationEnum,
        required_user_role: UserRoleEnum | None = None,
        is_blocked_users_allowed: bool | None = None,
    ) -> None:
        self.__auth_type = auth_type
        self.__required_user_role = required_user_role
        self.__is_blocked_users_allowed = is_blocked_users_allowed

    async def __call__(
        self,
        request: Request,
        provided_access_token: str = Depends(
            APIKeyHeader(
                name="X-Access-Token",
                scheme_name="X-Access-Token",
                description=(
                    "X-Access-Token - JWT access token"
                    " for internal or external authorization"
                ),
                auto_error=True,
            )
        ),
    ) -> tuple[int | None, UserRoleEnum | None]:
        host = request.headers.get("X-Real-IP", request.client.host)
        endpoint = request.url.path

        return await self.authenticate(
            host=host,
            endpoint=endpoint,
            provided_access_token=provided_access_token,
        )

    async def authenticate(
        self,
        host: str,
        endpoint: str,
        provided_access_token: str,
    ) -> tuple[int | None, UserRoleEnum | None]:
        logger.debug(
            "Authorization: %s, Host: %s, Endpoint: %s, Access-Token: %s",
            self.__auth_type,
            host,
            endpoint,
            provided_access_token,
        )

        if self.__auth_type == AuthorizationEnum.INTERNAL:
            is_valid = await self.validate_internal_authorization(
                provided_access_token=provided_access_token,
            )
            if is_valid:
                return None, UserRoleEnum.ADMINISTRATOR

        raise AuthorizationException(detail="Authorization failed")

    @staticmethod
    async def validate_internal_authorization(
        provided_access_token: str,
    ) -> bool:
        return provided_access_token == API_TOKEN
