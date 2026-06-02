from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RatingStats:
    speed_seconds: int | None
    complete: int
    incomplete: int
    not_taken: int
