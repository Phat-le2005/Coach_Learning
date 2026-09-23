from dataclasses import dataclass

from app.misconceptions.models import MisconceptionCategory


@dataclass(frozen=True, slots=True)
class MisconceptionSeed:
    code: str
    concept_code: str
    problem_type_code: str | None
    name: str
    description: str
    category: MisconceptionCategory


MISCONCEPTIONS: tuple[MisconceptionSeed, ...] = (
    MisconceptionSeed(
        code="DERIVATIVE_SIGN_DIRECTION",
        concept_code="DERIVATIVE",
        problem_type_code="MONOTONICITY_FROM_EXPRESSION",
        name="Derivative sign and monotonic direction",
        description="Treats a negative derivative as increasing or a positive derivative as decreasing.",
        category=MisconceptionCategory.CONCEPTUAL,
    ),
    MisconceptionSeed(
        code="PARAMETER_CONDITION_NOT_GLOBAL",
        concept_code="INEQUALITY_SOLVING",
        problem_type_code="PARAMETER_MONOTONICITY",
        name="Parameter condition checked at one point only",
        description="Checks the derivative inequality at selected points instead of requiring it on the whole domain.",
        category=MisconceptionCategory.PROCEDURAL,
    ),
    MisconceptionSeed(
        code="DERIVATIVE_ZERO_ALWAYS_EXTREMUM",
        concept_code="EXTREMA",
        problem_type_code="FIND_FUNCTION_EXTREMA",
        name="Every stationary point is an extremum",
        description="Assumes that f'(x) = 0 is sufficient for a local extremum without checking a sign change.",
        category=MisconceptionCategory.CONCEPTUAL,
    ),
    MisconceptionSeed(
        code="LOG_SUM_DISTRIBUTION",
        concept_code="LOGARITHM",
        problem_type_code="EXP_LOG_EQUATION",
        name="Logarithm distributed over addition",
        description="Incorrectly applies a logarithm product rule to a sum, such as log(a + b) = log(a) + log(b).",
        category=MisconceptionCategory.CONCEPTUAL,
    ),
    MisconceptionSeed(
        code="INDEFINITE_INTEGRAL_MISSING_CONSTANT",
        concept_code="INTEGRAL",
        problem_type_code="CALCULATE_INTEGRAL",
        name="Missing integration constant",
        description="Omits the arbitrary constant when reporting an indefinite integral.",
        category=MisconceptionCategory.PROCEDURAL,
    ),
    MisconceptionSeed(
        code="PROBABILITY_INDEPENDENCE_ASSUMED",
        concept_code="PROBABILITY",
        problem_type_code="BASIC_PROBABILITY",
        name="Independence assumed without justification",
        description="Multiplies event probabilities as if the events were independent without checking dependence.",
        category=MisconceptionCategory.CONCEPTUAL,
    ),
    MisconceptionSeed(
        code="VECTOR_COORDINATE_SIGN_ERROR",
        concept_code="VECTOR",
        problem_type_code="VECTOR_3D_RELATION",
        name="Vector coordinate subtraction reversed",
        description="Reverses endpoint subtraction or loses a sign when computing vector coordinates.",
        category=MisconceptionCategory.CALCULATION,
    ),
    MisconceptionSeed(
        code="OXYZ_NORMAL_VECTOR_MISUSED",
        concept_code="OXYZ",
        problem_type_code="OXYZ_LINE_PLANE_INTERSECTION",
        name="Plane normal used as a line direction",
        description="Uses the plane normal as the direction vector of an arbitrary intersecting line without justification.",
        category=MisconceptionCategory.PROCEDURAL,
    ),
    MisconceptionSeed(
        code="FUNCTION_GRAPH_AXES_MISREAD",
        concept_code="FUNCTION_ANALYSIS",
        problem_type_code="COMPLETE_FUNCTION_ANALYSIS",
        name="Function graph axes or scale misread",
        description="Reads an x-value as a y-value or ignores the scale when interpreting a function graph.",
        category=MisconceptionCategory.READING,
    ),
    MisconceptionSeed(
        code="DERIVATIVE_ARITHMETIC_SLIP",
        concept_code="DERIVATIVE",
        problem_type_code=None,
        name="Arithmetic slip during differentiation",
        description="Applies the correct derivative method but makes a local arithmetic or sign transcription error.",
        category=MisconceptionCategory.CARELESS,
    ),
)
