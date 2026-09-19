from statistics import mean

from app.students.models import SyntheticProfile
from data.synthetic.student_behavior import (
    SeededStudentBehaviorGenerator,
    SyntheticBehaviorTarget,
)


def accuracy(samples) -> float:
    return sum(sample.is_correct for sample in samples) / len(samples)


def test_seeded_behavior_is_deterministic_and_profiles_are_distinct() -> None:
    generator = SeededStudentBehaviorGenerator()
    codes = ["FUNCTION", "DERIVATIVE", "OXYZ"]
    generated = {
        profile: generator.generate(
            seed=2026,
            student_key=profile.value,
            profile=profile,
            concept_codes=codes,
            attempt_count=480,
        )
        for profile in SyntheticProfile
    }
    repeated = generator.generate(
        seed=2026,
        student_key="STRONG",
        profile=SyntheticProfile.STRONG,
        concept_codes=codes,
        attempt_count=480,
    )
    assert generated[SyntheticProfile.STRONG] == repeated
    assert accuracy(generated[SyntheticProfile.STRONG]) > accuracy(
        generated[SyntheticProfile.AVERAGE]
    ) > accuracy(generated[SyntheticProfile.WEAK])
    assert mean(item.response_time_ms for item in generated[SyntheticProfile.STRONG]) < mean(
        item.response_time_ms for item in generated[SyntheticProfile.WEAK]
    )


def test_specific_gap_and_inconsistent_patterns_are_structural() -> None:
    generator = SeededStudentBehaviorGenerator()
    codes = ["FUNCTION", "DERIVATIVE", "OXYZ"]
    gap = generator.generate(
        seed=77,
        student_key="gap",
        profile=SyntheticProfile.SPECIFIC_GAP,
        concept_codes=codes,
        attempt_count=480,
    )
    oxyz = [sample for sample in gap if sample.concept_code == "OXYZ"]
    other = [sample for sample in gap if sample.concept_code != "OXYZ"]
    assert accuracy(other) > 0.70
    assert accuracy(oxyz) < 0.30

    inconsistent = generator.generate(
        seed=77,
        student_key="inconsistent",
        profile=SyntheticProfile.INCONSISTENT,
        concept_codes=codes,
        attempt_count=480,
    )
    even = [sample for sample in inconsistent if sample.session_index % 2 == 0]
    odd = [sample for sample in inconsistent if sample.session_index % 2 == 1]
    assert accuracy(even) > 0.75
    assert accuracy(odd) < 0.40


def test_specific_gap_can_target_a_problem_type() -> None:
    targets = [
        SyntheticBehaviorTarget(
            key="pt:function",
            concept_code="FUNCTION",
            problem_type_code="FUNCTION_ANALYSIS",
        ),
        SyntheticBehaviorTarget(
            key="pt:oxyz",
            concept_code="OXYZ",
            problem_type_code="OXYZ_LINE_PLANE_INTERSECTION",
        ),
    ]
    samples = SeededStudentBehaviorGenerator().generate(
        seed=42,
        student_key="problem-gap",
        profile=SyntheticProfile.SPECIFIC_GAP,
        targets=targets,
        gap_keys={"pt:oxyz"},
        attempt_count=400,
    )
    targeted = [item for item in samples if item.problem_type_code == "OXYZ_LINE_PLANE_INTERSECTION"]
    other = [item for item in samples if item.problem_type_code != "OXYZ_LINE_PLANE_INTERSECTION"]
    assert accuracy(targeted) < 0.30
    assert accuracy(other) > 0.70
