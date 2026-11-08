"""Teacher-selected cognitive levels and the existing 0..1 difficulty scale."""
from enum import StrEnum


class MaterialDifficultyLevel(StrEnum):
    RECOGNITION = "NHAN_BIET"
    COMPREHENSION = "THONG_HIEU"
    APPLICATION = "VAN_DUNG"
    ADVANCED_APPLICATION = "VAN_DUNG_CAO"


DIFFICULTY_SCORES = {
    MaterialDifficultyLevel.RECOGNITION: 0.25,
    MaterialDifficultyLevel.COMPREHENSION: 0.5,
    MaterialDifficultyLevel.APPLICATION: 0.75,
    MaterialDifficultyLevel.ADVANCED_APPLICATION: 1.0,
}
