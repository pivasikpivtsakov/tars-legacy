from enum import Enum


class CustomEnum(Enum):
    @classmethod
    def _missing_(cls, name):  # noqa: ANN001, ANN206
        if isinstance(name, str):
            return cls.__members__.get(name)
        return super()._missing_(name)


class UserRoleEnum(CustomEnum):
    USER = 0
    MODERATOR = 1
    DEVELOPER = 2
    ADMINISTRATOR = 3
