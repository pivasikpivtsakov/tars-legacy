from fastapi import HTTPException, status


class AuthorizationException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class ControllerAuthorizationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)
