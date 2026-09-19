from dataclasses import dataclass
from random import Random
from typing import Sequence

from app.students.models import SyntheticProfile


@dataclass(frozen=True, slots=True)
class SyntheticAttemptSample:
    attempt_index: int
    session_index: int
    minute_offset: int
    target_key: str
    concept_code: str
    problem_type_code: str | None
    is_correct: bool
    response_time_ms: int


@dataclass(frozen=True, slots=True)
class SyntheticBehaviorTarget:
    key: str
    concept_code: str
    problem_type_code: str | None = None
    topic_code: str | None = None
    chapter_code: str | None = None
    subject_code: str | None = None
    is_primary_concept: bool = False


class SeededStudentBehaviorGenerator:
    """Pure deterministic simulator; no database, network, or AI dependency."""

    def generate(
        self,
        *,
        seed: int,
        student_key: str,
        profile: SyntheticProfile,
        concept_codes: Sequence[str] | None = None,
        targets: Sequence[SyntheticBehaviorTarget] | None = None,
        gap_keys: set[str] | None = None,
        attempt_count: int = 48,
        attempts_per_session: int = 6,
    ) -> list[SyntheticAttemptSample]:
        behavior_targets = list(targets or [])
        if not behavior_targets and concept_codes:
            behavior_targets = [
                SyntheticBehaviorTarget(key=code, concept_code=code)
                for code in concept_codes
            ]
        if not behavior_targets:
            raise ValueError("concept_codes or targets cannot be empty")
        if attempt_count < 1 or attempts_per_session < 1:
            raise ValueError("attempt counts must be positive")
        rng = Random(f"{seed}:{student_key}:{profile.value}")
        samples: list[SyntheticAttemptSample] = []
        shuffled_targets: list[SyntheticBehaviorTarget] = []
        while len(shuffled_targets) < attempt_count:
            block = list(behavior_targets)
            rng.shuffle(block)
            shuffled_targets.extend(block)

        selected_gap_keys = gap_keys or {
            target.key
            for target in behavior_targets
            if target.concept_code == "OXYZ"
            or (target.problem_type_code is not None and "OXYZ" in target.problem_type_code)
        }
        if profile == SyntheticProfile.SPECIFIC_GAP and not selected_gap_keys:
            selected_gap_keys = {behavior_targets[-1].key}

        for attempt_index, target in enumerate(shuffled_targets[:attempt_count]):
            session_index = attempt_index // attempts_per_session
            probability, mean_seconds, deviation = self._parameters(
                profile, target.key in selected_gap_keys, session_index
            )
            is_correct = rng.random() < probability
            seconds = max(5.0, rng.gauss(mean_seconds, deviation))
            if not is_correct:
                seconds *= 1.15
            samples.append(
                SyntheticAttemptSample(
                    attempt_index=attempt_index,
                    session_index=session_index,
                    minute_offset=(attempt_index % attempts_per_session) * 7,
                    target_key=target.key,
                    concept_code=target.concept_code,
                    problem_type_code=target.problem_type_code,
                    is_correct=is_correct,
                    response_time_ms=int(seconds * 1000),
                )
            )
        return samples

    @staticmethod
    def _parameters(
        profile: SyntheticProfile, is_specific_gap: bool, session_index: int
    ) -> tuple[float, float, float]:
        if profile == SyntheticProfile.STRONG:
            return 0.90, 38.0, 10.0
        if profile == SyntheticProfile.AVERAGE:
            return 0.65, 72.0, 20.0
        if profile == SyntheticProfile.WEAK:
            return 0.35, 118.0, 32.0
        if profile == SyntheticProfile.SPECIFIC_GAP:
            if is_specific_gap:
                return 0.15, 135.0, 34.0
            return 0.82, 52.0, 15.0
        # Alternate strong and weak sessions so inconsistency is structural,
        # rather than an accidental result of a small random sample.
        if session_index % 2 == 0:
            return 0.88, 45.0, 14.0
        return 0.25, 125.0, 40.0
