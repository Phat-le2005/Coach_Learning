from datetime import datetime
from math import ceil
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.orm import Session

from app.ai.models import AIRequestLog
from app.ai.pricing import calculate_estimated_cost
from app.ai.schemas import (
    AIRequestLogPagination,
    AIRequestLogRead,
    AIUsageSummaryRead,
    DailyUsageMetric,
    StudentDailyUsageMetric,
    TaskTokenMetric,
    TaskUsageMetric,
)
from app.ai.types import AITaskType


class AIUsageService:
    """Service for AI observability telemetry, audit logging, and usage analytics."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_log(
        self,
        *,
        task: str | AITaskType,
        provider: str,
        model: str,
        latency_ms: float,
        prompt_name: str = "default",
        prompt_version: str = "v1",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        success: bool = True,
        error_type: str | None = None,
        user_id: UUID | None = None,
        estimated_cost: float | None = None,
    ) -> AIRequestLog:
        """Record an AI request execution log.
        
        Calculates estimated cost automatically from model pricing if not provided.
        Privacy guarantee: Raw prompt contents are never persisted.
        """
        task_str = task.value if isinstance(task, AITaskType) else str(task)
        if estimated_cost is None:
            cost = calculate_estimated_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        else:
            cost = estimated_cost

        log = AIRequestLog(
            user_id=user_id,
            task=task_str,
            provider=provider,
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            latency_ms=round(latency_ms, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
            error_type=error_type,
            estimated_cost=cost,
        )
        self.session.add(log)
        self.session.flush()
        return log

    def get_logs(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        task: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        success: bool | None = None,
        user_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AIRequestLogPagination:
        """Query paginated AI request logs with filtering."""
        conditions = []
        if start_date is not None:
            conditions.append(AIRequestLog.created_at >= start_date)
        if end_date is not None:
            conditions.append(AIRequestLog.created_at <= end_date)
        if task is not None:
            conditions.append(AIRequestLog.task == task)
        if provider is not None:
            conditions.append(AIRequestLog.provider == provider)
        if model is not None:
            conditions.append(AIRequestLog.model == model)
        if success is not None:
            conditions.append(AIRequestLog.success == success)
        if user_id is not None:
            conditions.append(AIRequestLog.user_id == user_id)

        where_clause = and_(*conditions) if conditions else True

        total_stmt = select(func.count(AIRequestLog.id)).where(where_clause)
        total = self.session.scalar(total_stmt) or 0

        page_val = max(1, page)
        page_size_val = min(200, max(1, page_size))
        offset = (page_val - 1) * page_size_val

        query = (
            select(AIRequestLog)
            .where(where_clause)
            .order_by(desc(AIRequestLog.created_at))
            .offset(offset)
            .limit(page_size_val)
        )
        rows = self.session.scalars(query).all()
        total_pages = ceil(total / page_size_val) if total > 0 else 0

        items = [AIRequestLogRead.model_validate(row) for row in rows]
        return AIRequestLogPagination(
            items=items,
            total=total,
            page=page_val,
            page_size=page_size_val,
            total_pages=total_pages,
        )

    def get_usage_summary(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        task: str | None = None,
        provider: str | None = None,
    ) -> AIUsageSummaryRead:
        """Calculate aggregated AI usage metrics:
        
        - requests/day
        - requests/task
        - tokens/task
        - average latency
        - failure rate
        - estimated cost
        """
        conditions = []
        if start_date is not None:
            conditions.append(AIRequestLog.created_at >= start_date)
        if end_date is not None:
            conditions.append(AIRequestLog.created_at <= end_date)
        if task is not None:
            conditions.append(AIRequestLog.task == task)
        if provider is not None:
            conditions.append(AIRequestLog.provider == provider)

        where_clause = and_(*conditions) if conditions else True

        # 1. Global totals
        total_stmt = select(
            func.count(AIRequestLog.id).label("total_requests"),
            func.coalesce(func.sum(case((AIRequestLog.success == True, 1), else_=0)), 0).label("successful_requests"),
            func.coalesce(func.sum(case((AIRequestLog.success == False, 1), else_=0)), 0).label("failed_requests"),
            func.coalesce(func.avg(AIRequestLog.latency_ms), 0.0).label("avg_latency"),
            func.coalesce(func.sum(AIRequestLog.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(AIRequestLog.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(AIRequestLog.estimated_cost), 0.0).label("total_cost"),
        ).where(where_clause)

        total_row = self.session.execute(total_stmt).one()
        total_requests = int(total_row.total_requests)
        successful_requests = int(total_row.successful_requests)
        failed_requests = int(total_row.failed_requests)
        avg_latency = round(float(total_row.avg_latency), 2)
        total_input_tokens = int(total_row.total_input_tokens)
        total_output_tokens = int(total_row.total_output_tokens)
        total_tokens = total_input_tokens + total_output_tokens
        total_cost = round(float(total_row.total_cost), 6)
        failure_rate = round(failed_requests / total_requests, 4) if total_requests > 0 else 0.0

        # 2. Requests per day
        date_expr = func.date(AIRequestLog.created_at)
        daily_stmt = (
            select(
                date_expr.label("day"),
                func.count(AIRequestLog.id).label("requests"),
                func.coalesce(func.sum(case((AIRequestLog.success == True, 1), else_=0)), 0).label("successful_requests"),
                func.coalesce(func.sum(case((AIRequestLog.success == False, 1), else_=0)), 0).label("failed_requests"),
                func.coalesce(func.avg(AIRequestLog.latency_ms), 0.0).label("avg_latency"),
                func.coalesce(func.sum(AIRequestLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(AIRequestLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(AIRequestLog.estimated_cost), 0.0).label("cost"),
            )
            .where(where_clause)
            .group_by(date_expr)
            .order_by(date_expr)
        )
        daily_rows = self.session.execute(daily_stmt).all()
        requests_per_day: list[DailyUsageMetric] = []
        for r in daily_rows:
            d_total = int(r.requests)
            d_fail = int(r.failed_requests)
            d_fail_rate = round(d_fail / d_total, 4) if d_total > 0 else 0.0
            requests_per_day.append(
                DailyUsageMetric(
                    date=str(r.day),
                    requests=d_total,
                    successful_requests=int(r.successful_requests),
                    failed_requests=d_fail,
                    failure_rate=d_fail_rate,
                    average_latency_ms=round(float(r.avg_latency), 2),
                    total_tokens=int(r.input_tokens) + int(r.output_tokens),
                    estimated_cost=round(float(r.cost), 6),
                )
            )

        # 3. Requests and tokens per task
        task_stmt = (
            select(
                AIRequestLog.task,
                func.count(AIRequestLog.id).label("requests"),
                func.coalesce(func.sum(case((AIRequestLog.success == True, 1), else_=0)), 0).label("successful_requests"),
                func.coalesce(func.sum(case((AIRequestLog.success == False, 1), else_=0)), 0).label("failed_requests"),
                func.coalesce(func.avg(AIRequestLog.latency_ms), 0.0).label("avg_latency"),
                func.coalesce(func.sum(AIRequestLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(AIRequestLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(AIRequestLog.estimated_cost), 0.0).label("cost"),
            )
            .where(where_clause)
            .group_by(AIRequestLog.task)
            .order_by(desc("requests"))
        )
        task_rows = self.session.execute(task_stmt).all()
        requests_per_task: list[TaskUsageMetric] = []
        tokens_per_task: list[TaskTokenMetric] = []
        for r in task_rows:
            t_total = int(r.requests)
            t_fail = int(r.failed_requests)
            t_fail_rate = round(t_fail / t_total, 4) if t_total > 0 else 0.0
            in_tok = int(r.input_tokens)
            out_tok = int(r.output_tokens)
            tot_tok = in_tok + out_tok
            cost = round(float(r.cost), 6)
            avg_tok = round(tot_tok / t_total, 2) if t_total > 0 else 0.0
            avg_cost = round(cost / t_total, 6) if t_total > 0 else 0.0
            requests_per_task.append(
                TaskUsageMetric(
                    task=r.task,
                    requests=t_total,
                    successful_requests=int(r.successful_requests),
                    failed_requests=t_fail,
                    failure_rate=t_fail_rate,
                    average_latency_ms=round(float(r.avg_latency), 2),
                    total_tokens=tot_tok,
                    average_tokens_per_task=avg_tok,
                    estimated_cost=cost,
                    average_cost_per_task=avg_cost,
                )
            )
            tokens_per_task.append(
                TaskTokenMetric(
                    task=r.task,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=tot_tok,
                    average_tokens_per_task=avg_tok,
                    estimated_cost=cost,
                    average_cost_per_task=avg_cost,
                )
            )

        # 4. Requests per student per day
        student_daily_stmt = (
            select(
                date_expr.label("day"),
                func.count(func.distinct(AIRequestLog.user_id)).label("unique_students"),
                func.count(AIRequestLog.id).label("total_requests"),
            )
            .where(where_clause, AIRequestLog.user_id.is_not(None))
            .group_by(date_expr)
            .order_by(date_expr)
        )
        student_daily_rows = self.session.execute(student_daily_stmt).all()
        student_daily_usage: list[StudentDailyUsageMetric] = []
        student_daily_averages: list[float] = []

        for r in student_daily_rows:
            u_count = int(r.unique_students)
            req_count = int(r.total_requests)
            avg_req = round(req_count / u_count, 2) if u_count > 0 else 0.0
            student_daily_averages.append(avg_req)
            student_daily_usage.append(
                StudentDailyUsageMetric(
                    date=str(r.day),
                    unique_students=u_count,
                    total_requests=req_count,
                    average_requests_per_student=avg_req,
                )
            )

        avg_req_per_student_per_day = (
            round(sum(student_daily_averages) / len(student_daily_averages), 2)
            if student_daily_averages
            else 0.0
        )

        return AIUsageSummaryRead(
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            failure_rate=failure_rate,
            average_latency_ms=avg_latency,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_tokens=total_tokens,
            total_estimated_cost=total_cost,
            average_requests_per_student_per_day=avg_req_per_student_per_day,
            requests_per_day=requests_per_day,
            requests_per_task=requests_per_task,
            tokens_per_task=tokens_per_task,
            student_daily_usage=student_daily_usage,
        )

    def get_metrics_per_task(self) -> dict[str, dict[str, Any]]:
        """Retrieve a dictionary mapping each task type to its core performance metrics:
        
        - average latency/task
        - tokens/task (total & average)
        - estimated cost/task (total & average)
        - requests
        """
        summary = self.get_usage_summary()
        result: dict[str, dict[str, Any]] = {}
        for m in summary.requests_per_task:
            result[m.task] = {
                "requests": m.requests,
                "successful_requests": m.successful_requests,
                "failed_requests": m.failed_requests,
                "average_latency_ms": m.average_latency_ms,
                "total_tokens": m.total_tokens,
                "average_tokens_per_task": m.average_tokens_per_task,
                "estimated_cost": m.estimated_cost,
                "average_cost_per_task": m.average_cost_per_task,
            }
        return result
