from fastapi import HTTPException, status


class ResourceAlreadyExistsError(HTTPException):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class NotFoundError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class DBInconsistencyError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)
