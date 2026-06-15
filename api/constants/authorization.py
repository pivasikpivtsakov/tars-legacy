from enum import StrEnum, auto


class AuthorizationEnum(StrEnum):
    BOTH = auto()
    INTERNAL = auto()
    EXTERNAL = auto()
