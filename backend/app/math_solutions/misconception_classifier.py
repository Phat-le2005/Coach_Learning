from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.misconceptions.models import MisconceptionDefinition, StudentMisconceptionStatus


@dataclass(frozen=True)
class MisconceptionClassification:
    code: str
    name: str
    description: str
    status: str  # SUSPECTED or CONFIRMED
    evidence_quote: str | None
    definition_id: UUID | None


class MisconceptionClassifier:
    """
    Tier-4 Misconception Classifier for Grade 12 Calculus.
    Disentangles 4 distinct pedagogical error classes:
    (a) DERIVATIVE_ARITHMETIC_SLIP: Power rule or algebraic sign slip in y'.
    (b) ROOT_FINDING_ERROR: Inversion or algebraic error when solving y' = 0.
    (c) SIGN_TABLE_QUADRATIC_RULE_INVERTED: Correct roots and derivative, but sign of quadratic trinomial inverted. Status is strictly SUSPECTED.
    (d) DERIVATIVE_SIGN_DIRECTION: Inverting monotonic direction from known derivative sign (y' < 0 => increasing).
    """

    def __init__(self, session: Session | None = None) -> None:
        self.session = session

    def classify_error(
        self,
        error_code: str,
        step_type: str,
        content_latex: str | None,
        explanation_text: str | None,
        artifact_payload: dict[str, Any] | None = None,
        sign_table_was_inverted: bool = False,
    ) -> MisconceptionClassification | None:
        if error_code == "DERIVATIVE_ARITHMETIC_SLIP":
            return self._build_classification(
                code="DERIVATIVE_ARITHMETIC_SLIP",
                name="Lỗi tính toán hoặc dấu đại số của đạo hàm",
                description="Áp dụng sai quy tắc đạo hàm hoặc tính nhầm dấu đại số khi rút gọn biểu thức đạo hàm bậc hai.",
                status=StudentMisconceptionStatus.SUSPECTED.value,
                evidence_quote=content_latex,
            )

        if error_code == "ROOT_FINDING_ERROR":
            return self._build_classification(
                code="ROOT_FINDING_ERROR",
                name="Lỗi giải phương trình tìm nghiệm đạo hàm",
                description="Giải sai phương trình đạo hàm y' = 0 (tính nhầm delta hoặc nhầm dấu nghiệm).",
                status=StudentMisconceptionStatus.SUSPECTED.value,
                evidence_quote=content_latex,
            )

        if error_code == "SIGN_TABLE_QUADRATIC_RULE_INVERTED":
            return self._build_classification(
                code="SIGN_TABLE_QUADRATIC_RULE_INVERTED",
                name="Lỗi đảo ngược quy tắc dấu tam thức bậc hai",
                description="Áp dụng sai quy tắc xét dấu tam thức bậc hai (nhầm 'trong cùng ngoài khác' thay vì 'trong trái ngoài cùng' khi hệ số a > 0).",
                status=StudentMisconceptionStatus.SUSPECTED.value,
                evidence_quote=str(artifact_payload),
            )

        if error_code == "DERIVATIVE_SIGN_DIRECTION" or (
            step_type == "CONCLUSION"
            and not sign_table_was_inverted
            and error_code == "SIGN_TABLE_CONSEQUENCE_ERROR"
        ):
            return self._build_classification(
                code="DERIVATIVE_SIGN_DIRECTION",
                name="Lỗi đảo ngược chiều biến thiên từ dấu đạo hàm",
                description="Đã biết đúng dấu của đạo hàm nhưng suy luận đảo ngược quan hệ đơn điệu (y' < 0 lại kết luận đồng biến hoặc y' > 0 lại kết luận nghịch biến).",
                status=StudentMisconceptionStatus.SUSPECTED.value,
                evidence_quote=(content_latex or "") + " " + (explanation_text or ""),
            )

        return None

    def _build_classification(
        self,
        code: str,
        name: str,
        description: str,
        status: str,
        evidence_quote: str | None,
    ) -> MisconceptionClassification:
        definition_id = None
        if self.session is not None:
            definition = self.session.scalar(
                select(MisconceptionDefinition).where(MisconceptionDefinition.code == code)
            )
            if definition:
                definition_id = definition.id

        return MisconceptionClassification(
            code=code,
            name=name,
            description=description,
            status=status,
            evidence_quote=evidence_quote,
            definition_id=definition_id,
        )
