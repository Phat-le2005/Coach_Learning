from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.database.session import dispose_engine, get_session_factory
from app.questions.fingerprint import question_content_hash
from app.questions.group_import_service import TrustedQuestionGroupImportService
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import Role, User

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
logger = logging.getLogger(__name__)


def extract_mc_options(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract prompt and (A, B, C, D) options from text."""
    mA = re.search(r'(?:^|\s|\n)A\.\s*', text)
    if not mA:
        return text.strip(), []
    mB = re.search(r'(?:^|\s|\n)B\.\s*', text[mA.end():])
    if not mB:
        return text.strip(), []
    posB = mA.end() + mB.start()
    posB_end = mA.end() + mB.end()
    
    mC = re.search(r'(?:^|\s|\n|\.)C\.\s*', text[posB_end:])
    if not mC:
        return text.strip(), []
    posC = posB_end + mC.start()
    posC_end = posB_end + mC.end()
    
    mD = re.search(r'(?:^|\s|\n)D\.\s*', text[posC_end:])
    if not mD:
        return text.strip(), []
    posD = posC_end + mD.start()
    posD_end = posC_end + mD.end()
    
    prompt = text[:mA.start()].strip()
    optA = text[mA.end():posB].strip()
    optB = text[posB_end:posC].strip()
    optC = text[posC_end:posD].strip()
    optD = text[posD_end:].strip()
    optD = re.sub(r'[\s]+$', '', optD).strip()
    opts = [('A', optA), ('B', optB), ('C', optC), ('D', optD)]
    if all(len(o[1]) > 0 for o in opts) and len(prompt) > 0:
        return prompt, opts
    return text.strip(), []


def extract_tf_items_strict(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract prompt and (a, b, c, d) True/False statements strictly."""
    ma = re.search(r'(?:\n|^|\s)(?:a\)\s+|\(a\)\s+|a\.\s+)', text)
    if not ma:
        return text.strip(), []
    mb = re.search(r'(?:\n|^|\s)(?:b\)\s+|\(b\)\s+|b\.\s+)', text[ma.end():])
    if not mb:
        return text.strip(), []
    pos_b = ma.end() + mb.start()
    pos_b_end = ma.end() + mb.end()
    
    mc = re.search(r'(?:\n|^|\s)(?:c\)\s+|\(c\)\s+|c\.\s+)', text[pos_b_end:])
    if not mc:
        return text.strip(), []
    pos_c = pos_b_end + mc.start()
    pos_c_end = pos_b_end + mc.end()
    
    md = re.search(r'(?:\n|^|\s)(?:d\)\s+|\(d\)\s+|d\.\s+)', text[pos_c_end:])
    if not md:
        return text.strip(), []
    pos_d = pos_c_end + md.start()
    pos_d_end = pos_c_end + md.end()
    
    prompt = text[:ma.start()].strip()
    item_a = text[ma.end():pos_b].strip()
    item_b = text[pos_b_end:pos_c].strip()
    item_c = text[pos_c_end:pos_d].strip()
    item_d = text[pos_d_end:].strip()
    items = [('a', item_a), ('b', item_b), ('c', item_c), ('d', item_d)]
    if all(len(x[1]) >= 2 for x in items) and len(prompt) > 0:
        return prompt, items
    return text.strip(), []


def run_import() -> dict[str, int]:
    settings = get_settings()
    configure_logging(settings.debug and settings.app_env != "production")
    
    session: Session = get_session_factory()()
    stats = Counter()

    try:
        subject = session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
        if not subject:
            raise RuntimeError("Subject MATH_G12 not found in database!")
        
        admin = session.scalar(select(User).where(User.role == Role.ADMIN))
        if not admin:
            admin = session.scalar(select(User))
            if not admin:
                raise RuntimeError("No user found in database to act as created_by actor!")
        
        concepts_map = {c.code: c.id for c in session.scalars(select(Concept).where(Concept.subject_id == subject.id)).all()}
        pts_map = {pt.code: pt.id for pt in session.scalars(select(ProblemType)).all()}
        los_map = {lo.code: lo.id for lo in session.scalars(select(LearningOutcome).where(LearningOutcome.subject_id == subject.id)).all()}
        
        print(f"Loaded taxonomy: {len(concepts_map)} concepts, {len(pts_map)} problem types, {len(los_map)} learning outcomes")
        
        existing_hashes = set(session.scalars(select(Question.content_hash)).all())
        existing_group_contents = set(session.scalars(select(QuestionGroup.content)).all())
        print(f"Existing questions in DB: {len(existing_hashes)}, existing groups: {len(existing_group_contents)}")

        def link_taxonomy(q_obj: Question, raw_concepts: list | None, pt_code: str | None, raw_los: list | None):
            if pt_code and pt_code in pts_map:
                q_obj.problem_type_links.append(
                    QuestionProblemType(
                        problem_type_id=pts_map[pt_code],
                        weight=1.0,
                        is_primary=True,
                    )
                )
            if raw_concepts:
                for c in raw_concepts:
                    code = c.get("concept_code") if isinstance(c, dict) else str(c)
                    if code in concepts_map:
                        w = c.get("weight", 1.0) if isinstance(c, dict) else 1.0
                        q_obj.concept_links.append(
                            QuestionConcept(
                                concept_id=concepts_map[code],
                                weight=min(max(float(w), 0.1), 1.0),
                            )
                        )
            if raw_los:
                for lo in raw_los:
                    code = lo.get("learning_outcome_code") if isinstance(lo, dict) else str(lo)
                    if code in los_map:
                        w = lo.get("weight", 1.0) if isinstance(lo, dict) else 1.0
                        q_obj.learning_outcome_links.append(
                            QuestionLearningOutcome(
                                learning_outcome_id=los_map[code],
                                weight=min(max(float(w), 0.1), 1.0),
                            )
                        )

        # -------------------------------------------------------------
        # 1. IMPORT DERIVATIVE GROUPS & 152 CHILDREN
        # -------------------------------------------------------------
        print("\n--- 1. Importing Derivative Question Groups (Part II True/False) ---")
        deriv_service = TrustedQuestionGroupImportService()
        preview = deriv_service.preview()
        for group in preview.groups:
            if group.content in existing_group_contents:
                stats["deriv_groups_skipped"] += 1
                continue
            
            q_group = QuestionGroup(
                id=group.id,
                subject_id=subject.id,
                content=group.content,
                group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                difficulty=group.difficulty,
                source_type=str(group.source_lineage.get("source_code", "GDPT2018_DERIVATIVE")),
                source_reference=str(group.source_lineage.get("source_evidence_id", group.external_group_key)),
                source_year=2025,
                exam_weight=1.0,
                status=QuestionStatus.APPROVED,
                created_by=admin.id,
            )
            
            group_items = []
            for child in group.children:
                c_hash = question_content_hash(child.content)
                existing_hashes.add(c_hash)
                
                child_q = Question(
                    id=child.id,
                    subject_id=subject.id,
                    content=child.content,
                    content_hash=c_hash,
                    question_type=QuestionType.TRUE_FALSE,
                    difficulty=child.difficulty,
                    correct_answer=child.correct_answer,
                    explanation=None,
                    source_type=str(group.source_lineage.get("source_code", "GDPT2018_DERIVATIVE")),
                    source_reference=str(group.source_lineage.get("source_evidence_id", group.external_group_key)),
                    source_year=2025,
                    exam_weight=0.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                
                for pt_link in child.problem_types:
                    if pt_link.code in pts_map:
                        child_q.problem_type_links.append(
                            QuestionProblemType(
                                problem_type_id=pts_map[pt_link.code],
                                weight=pt_link.weight,
                                is_primary=pt_link.is_primary,
                            )
                        )
                
                for c_link in child.concepts:
                    if c_link.code in concepts_map:
                        child_q.concept_links.append(
                            QuestionConcept(
                                concept_id=concepts_map[c_link.code],
                                weight=c_link.weight,
                            )
                        )
                
                for lo_link in child.learning_outcomes:
                    if lo_link.code in los_map:
                        child_q.learning_outcome_links.append(
                            QuestionLearningOutcome(
                                learning_outcome_id=los_map[lo_link.code],
                                weight=lo_link.weight,
                            )
                        )
                
                session.add(child_q)
                stats["questions_created"] += 1
                
                group_items.append(
                    QuestionGroupItem(
                        id=uuid4(),
                        question_id=child_q.id,
                        label=child.label,
                        order_index=child.order_index,
                    )
                )
            
            q_group.items = group_items
            session.add(q_group)
            existing_group_contents.add(group.content)
            stats["groups_created"] += 1
        
        session.flush()
        print(f"Imported {stats['groups_created']} derivative groups with {stats['questions_created']} child questions.")

        # -------------------------------------------------------------
        # 2. IMPORT INTEGRALS (79 questions)
        # -------------------------------------------------------------
        print("\n--- 2. Importing Integrals Questions ---")
        int_files = [
            "backend/data/questions/math/grade12/integrals_v0_1/academic_review/v0_1/verified_questions.json",
            "backend/data/questions/math/grade12/integrals_v0_1/gap_supplement/v0_1/verified_gap_questions.json",
        ]
        for fpath in int_files:
            if not Path(fpath).exists():
                continue
            with open(fpath, "r", encoding="utf-8") as fp:
                items = json.load(fp)
            for item in items:
                raw_text = item.get("raw_question_text", "").strip()
                if not raw_text:
                    continue
                
                qtype_raw = item.get("question_type", "MULTIPLE_CHOICE")
                
                if qtype_raw == "TRUE_FALSE_GROUP":
                    tf_prompt, tf_statements = extract_tf_items_strict(raw_text)
                    if len(tf_statements) == 4 and tf_prompt not in existing_group_contents:
                        q_group = QuestionGroup(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=tf_prompt,
                            group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                            scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                            difficulty=0.5,
                            source_type="INTEGRALS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        g_items = []
                        for idx, (lbl, stmt) in enumerate(tf_statements):
                            c_hash = question_content_hash(stmt)
                            child_q = Question(
                                id=uuid4(),
                                subject_id=subject.id,
                                content=stmt,
                                content_hash=c_hash,
                                question_type=QuestionType.TRUE_FALSE,
                                difficulty=0.5,
                                correct_answer=None,
                                source_type="INTEGRALS",
                                source_reference=item.get("candidate_id"),
                                source_year=2025,
                                exam_weight=0.0,
                                status=QuestionStatus.APPROVED,
                                created_by=admin.id,
                            )
                            link_taxonomy(child_q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                            session.add(child_q)
                            stats["questions_created"] += 1
                            g_items.append(QuestionGroupItem(id=uuid4(), question_id=child_q.id, label=lbl, order_index=idx))
                        q_group.items = g_items
                        session.add(q_group)
                        existing_group_contents.add(tf_prompt)
                        stats["groups_created"] += 1
                        continue
                
                if qtype_raw == "MULTIPLE_CHOICE":
                    mc_prompt, mc_options = extract_mc_options(raw_text)
                    if len(mc_options) == 4:
                        c_hash = question_content_hash(mc_prompt)
                        if c_hash in existing_hashes:
                            stats["duplicates_skipped"] += 1
                            continue
                        existing_hashes.add(c_hash)
                        
                        q = Question(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=mc_prompt,
                            content_hash=c_hash,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            difficulty=0.5,
                            correct_answer=str(item.get("correct_answer", "A")),
                            source_type="INTEGRALS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        for idx, (lbl, opt_text) in enumerate(mc_options):
                            q.options.append(QuestionOption(id=uuid4(), label=lbl, content=opt_text, order_index=idx))
                        link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                        session.add(q)
                        stats["questions_created"] += 1
                        continue

                # Fallback to Short Answer
                clean_text = re.sub(r'<Key=[^>]+>', '', raw_text).strip()
                if not clean_text:
                    continue
                c_hash = question_content_hash(clean_text)
                if c_hash in existing_hashes:
                    stats["duplicates_skipped"] += 1
                    continue
                existing_hashes.add(c_hash)
                
                ans = item.get("correct_answer")
                if ans:
                    ans_str = str(ans)
                else:
                    m_key = re.search(r'<Key=([^>]+)>', raw_text)
                    ans_str = m_key.group(1).strip() if m_key else None
                
                q = Question(
                    id=uuid4(),
                    subject_id=subject.id,
                    content=clean_text,
                    content_hash=c_hash,
                    question_type=QuestionType.SHORT_ANSWER,
                    difficulty=0.5,
                    correct_answer=ans_str,
                    source_type="INTEGRALS",
                    source_reference=item.get("candidate_id"),
                    source_year=2025,
                    exam_weight=1.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                session.add(q)
                stats["questions_created"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 3. IMPORT CONDITIONAL PROBABILITY (18 questions)
        # -------------------------------------------------------------
        print("\n--- 3. Importing Conditional Probability Questions ---")
        prob_files = [
            "backend/data/questions/math/grade12/conditional_probability_v0_1/academic_review/v0_1/verified_questions.json",
            "backend/data/questions/math/grade12/conditional_probability_v0_1/gap_supplement/v0_1/verified_gap_evidence.json",
        ]
        for fpath in prob_files:
            if not Path(fpath).exists():
                continue
            with open(fpath, "r", encoding="utf-8") as fp:
                items = json.load(fp)
            for item in items:
                raw_text = item.get("raw_question_text", "").strip()
                if not raw_text:
                    continue
                c_hash = question_content_hash(raw_text)
                if c_hash in existing_hashes:
                    stats["duplicates_skipped"] += 1
                    continue
                existing_hashes.add(c_hash)
                
                ans = item.get("correct_answer")
                ans_str = str(ans) if ans is not None else None
                
                q = Question(
                    id=uuid4(),
                    subject_id=subject.id,
                    content=raw_text,
                    content_hash=c_hash,
                    question_type=QuestionType.SHORT_ANSWER,
                    difficulty=0.5,
                    correct_answer=ans_str,
                    source_type="PROBABILITY",
                    source_reference=item.get("candidate_id"),
                    source_year=2025,
                    exam_weight=1.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                session.add(q)
                stats["questions_created"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 4. IMPORT OXYZ QUESTIONS (133 questions)
        # -------------------------------------------------------------
        print("\n--- 4. Importing OXYZ Questions ---")
        oxyz_files = [
            "backend/data/questions/math/grade12/oxyz_v0_1/academic_review/v0_1/verified_questions.json",
            "backend/data/questions/math/grade12/oxyz_v0_1/gap_supplement/v0_1/verified_gap_questions.json",
        ]
        for fpath in oxyz_files:
            if not Path(fpath).exists():
                continue
            with open(fpath, "r", encoding="utf-8") as fp:
                items = json.load(fp)
            for item in items:
                raw_text = item.get("raw_question_text", "").strip()
                if not raw_text:
                    continue
                
                qtype_raw = item.get("question_type")
                if qtype_raw == "TRUE_FALSE_GROUP":
                    tf_prompt, tf_statements = extract_tf_items_strict(raw_text)
                    if len(tf_statements) == 4 and tf_prompt not in existing_group_contents:
                        corr_ans = item.get("correct_answer")
                        q_group = QuestionGroup(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=tf_prompt,
                            group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                            scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                            difficulty=0.5,
                            source_type="OXYZ",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        g_items = []
                        for idx, (lbl, stmt) in enumerate(tf_statements):
                            c_hash = question_content_hash(stmt)
                            child_ans = None
                            if isinstance(corr_ans, list) and idx < len(corr_ans):
                                child_ans = "TRUE" if corr_ans[idx] else "FALSE"
                            child_q = Question(
                                id=uuid4(),
                                subject_id=subject.id,
                                content=stmt,
                                content_hash=c_hash,
                                question_type=QuestionType.TRUE_FALSE,
                                difficulty=0.5,
                                correct_answer=child_ans,
                                source_type="OXYZ",
                                source_reference=item.get("candidate_id"),
                                source_year=2025,
                                exam_weight=0.0,
                                status=QuestionStatus.APPROVED,
                                created_by=admin.id,
                            )
                            link_taxonomy(child_q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                            session.add(child_q)
                            stats["questions_created"] += 1
                            g_items.append(QuestionGroupItem(id=uuid4(), question_id=child_q.id, label=lbl, order_index=idx))
                        q_group.items = g_items
                        session.add(q_group)
                        existing_group_contents.add(tf_prompt)
                        stats["groups_created"] += 1
                        continue
                
                if qtype_raw == "MULTIPLE_CHOICE":
                    mc_prompt, mc_options = extract_mc_options(raw_text)
                    if len(mc_options) == 4:
                        c_hash = question_content_hash(mc_prompt)
                        if c_hash in existing_hashes:
                            stats["duplicates_skipped"] += 1
                            continue
                        existing_hashes.add(c_hash)
                        
                        q = Question(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=mc_prompt,
                            content_hash=c_hash,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            difficulty=0.5,
                            correct_answer=str(item.get("correct_answer", "A")),
                            source_type="OXYZ",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        for idx, (lbl, opt_text) in enumerate(mc_options):
                            q.options.append(QuestionOption(id=uuid4(), label=lbl, content=opt_text, order_index=idx))
                        link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                        session.add(q)
                        stats["questions_created"] += 1
                        continue

                # Short Answer
                c_hash = question_content_hash(raw_text)
                if c_hash in existing_hashes:
                    stats["duplicates_skipped"] += 1
                    continue
                existing_hashes.add(c_hash)
                
                ans = item.get("correct_answer")
                ans_str = str(ans) if ans is not None else None
                q = Question(
                    id=uuid4(),
                    subject_id=subject.id,
                    content=raw_text,
                    content_hash=c_hash,
                    question_type=QuestionType.SHORT_ANSWER,
                    difficulty=0.5,
                    correct_answer=ans_str,
                    source_type="OXYZ",
                    source_reference=item.get("candidate_id"),
                    source_year=2025,
                    exam_weight=1.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                session.add(q)
                stats["questions_created"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 5. IMPORT STATISTICS (41 questions)
        # -------------------------------------------------------------
        print("\n--- 5. Importing Statistics / Grouped Data Dispersion ---")
        stats_path = "backend/data/questions/math/grade12/grouped_data_dispersion_v0_1/staging/materialized_v0_1/candidate_questions.json"
        if Path(stats_path).exists():
            with open(stats_path, "r", encoding="utf-8") as fp:
                items = json.load(fp)
            for item in items:
                raw_text = item.get("raw_question_text", "").strip()
                if not raw_text:
                    continue
                
                raw_text = re.sub(r'^[»\s]+', '', raw_text).strip()
                qtype_raw = item.get("question_type_detected")
                
                if qtype_raw == "TRUE_FALSE_GROUP":
                    tf_prompt, tf_statements = extract_tf_items_strict(raw_text)
                    if len(tf_statements) == 4 and tf_prompt not in existing_group_contents:
                        q_group = QuestionGroup(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=tf_prompt,
                            group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                            scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                            difficulty=0.5,
                            source_type="STATISTICS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        g_items = []
                        for idx, (lbl, stmt) in enumerate(tf_statements):
                            c_hash = question_content_hash(stmt)
                            child_q = Question(
                                id=uuid4(),
                                subject_id=subject.id,
                                content=stmt,
                                content_hash=c_hash,
                                question_type=QuestionType.TRUE_FALSE,
                                difficulty=0.5,
                                correct_answer=None,
                                source_type="STATISTICS",
                                source_reference=item.get("candidate_id"),
                                source_year=2025,
                                exam_weight=0.0,
                                status=QuestionStatus.APPROVED,
                                created_by=admin.id,
                            )
                            link_taxonomy(child_q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                            session.add(child_q)
                            stats["questions_created"] += 1
                            g_items.append(QuestionGroupItem(id=uuid4(), question_id=child_q.id, label=lbl, order_index=idx))
                        q_group.items = g_items
                        session.add(q_group)
                        existing_group_contents.add(tf_prompt)
                        stats["groups_created"] += 1
                        continue
                
                if qtype_raw == "MULTIPLE_CHOICE":
                    mc_prompt, mc_options = extract_mc_options(raw_text)
                    if len(mc_options) == 4:
                        c_hash = question_content_hash(mc_prompt)
                        if c_hash in existing_hashes:
                            stats["duplicates_skipped"] += 1
                            continue
                        existing_hashes.add(c_hash)
                        
                        ans = item.get("answer_detected")
                        q = Question(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=mc_prompt,
                            content_hash=c_hash,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            difficulty=0.5,
                            correct_answer=str(ans) if ans else "A",
                            source_type="STATISTICS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        for idx, (lbl, opt_text) in enumerate(mc_options):
                            q.options.append(QuestionOption(id=uuid4(), label=lbl, content=opt_text, order_index=idx))
                        link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                        session.add(q)
                        stats["questions_created"] += 1
                        continue

                # Short Answer
                c_hash = question_content_hash(raw_text)
                if c_hash in existing_hashes:
                    stats["duplicates_skipped"] += 1
                    continue
                existing_hashes.add(c_hash)
                ans = item.get("answer_detected")
                q = Question(
                    id=uuid4(),
                    subject_id=subject.id,
                    content=raw_text,
                    content_hash=c_hash,
                    question_type=QuestionType.SHORT_ANSWER,
                    difficulty=0.5,
                    correct_answer=str(ans) if ans else None,
                    source_type="STATISTICS",
                    source_reference=item.get("candidate_id"),
                    source_year=2025,
                    exam_weight=1.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                session.add(q)
                stats["questions_created"] += 1

        session.flush()

        # -------------------------------------------------------------
        # 6. IMPORT VECTOR COORDINATES (72 questions)
        # -------------------------------------------------------------
        print("\n--- 6. Importing Vector Coordinates Questions ---")
        vec_path = "backend/data/questions/math/grade12/vector_coordinates_v0_1/staging/materialized_v0_1/candidate_questions.json"
        if Path(vec_path).exists():
            with open(vec_path, "r", encoding="utf-8") as fp:
                items = json.load(fp)
            for item in items:
                raw_text = item.get("raw_question_text", "").strip()
                if not raw_text:
                    continue
                
                raw_text = re.sub(r'^[»\s]+', '', raw_text).strip()
                qtype_raw = item.get("question_type_detected")
                
                if qtype_raw == "TRUE_FALSE_GROUP":
                    tf_prompt, tf_statements = extract_tf_items_strict(raw_text)
                    if len(tf_statements) == 4 and tf_prompt not in existing_group_contents:
                        q_group = QuestionGroup(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=tf_prompt,
                            group_type=QuestionGroupType.TRUE_FALSE_FOUR,
                            scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
                            difficulty=0.5,
                            source_type="VECTORS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        g_items = []
                        for idx, (lbl, stmt) in enumerate(tf_statements):
                            c_hash = question_content_hash(stmt)
                            child_q = Question(
                                id=uuid4(),
                                subject_id=subject.id,
                                content=stmt,
                                content_hash=c_hash,
                                question_type=QuestionType.TRUE_FALSE,
                                difficulty=0.5,
                                correct_answer=None,
                                source_type="VECTORS",
                                source_reference=item.get("candidate_id"),
                                source_year=2025,
                                exam_weight=0.0,
                                status=QuestionStatus.APPROVED,
                                created_by=admin.id,
                            )
                            link_taxonomy(child_q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                            session.add(child_q)
                            stats["questions_created"] += 1
                            g_items.append(QuestionGroupItem(id=uuid4(), question_id=child_q.id, label=lbl, order_index=idx))
                        q_group.items = g_items
                        session.add(q_group)
                        existing_group_contents.add(tf_prompt)
                        stats["groups_created"] += 1
                        continue
                
                if qtype_raw == "MULTIPLE_CHOICE":
                    mc_prompt, mc_options = extract_mc_options(raw_text)
                    if len(mc_options) == 4:
                        c_hash = question_content_hash(mc_prompt)
                        if c_hash in existing_hashes:
                            stats["duplicates_skipped"] += 1
                            continue
                        existing_hashes.add(c_hash)
                        
                        ans = item.get("answer_detected")
                        q = Question(
                            id=uuid4(),
                            subject_id=subject.id,
                            content=mc_prompt,
                            content_hash=c_hash,
                            question_type=QuestionType.MULTIPLE_CHOICE,
                            difficulty=0.5,
                            correct_answer=str(ans) if ans else "A",
                            source_type="VECTORS",
                            source_reference=item.get("candidate_id"),
                            source_year=2025,
                            exam_weight=1.0,
                            status=QuestionStatus.APPROVED,
                            created_by=admin.id,
                        )
                        for idx, (lbl, opt_text) in enumerate(mc_options):
                            q.options.append(QuestionOption(id=uuid4(), label=lbl, content=opt_text, order_index=idx))
                        link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                        session.add(q)
                        stats["questions_created"] += 1
                        continue

                # Short Answer
                c_hash = question_content_hash(raw_text)
                if c_hash in existing_hashes:
                    stats["duplicates_skipped"] += 1
                    continue
                existing_hashes.add(c_hash)
                ans = item.get("answer_detected")
                q = Question(
                    id=uuid4(),
                    subject_id=subject.id,
                    content=raw_text,
                    content_hash=c_hash,
                    question_type=QuestionType.SHORT_ANSWER,
                    difficulty=0.5,
                    correct_answer=str(ans) if ans else None,
                    source_type="VECTORS",
                    source_reference=item.get("candidate_id"),
                    source_year=2025,
                    exam_weight=1.0,
                    status=QuestionStatus.APPROVED,
                    created_by=admin.id,
                )
                link_taxonomy(q, item.get("concepts"), item.get("problem_type_code"), item.get("learning_outcomes"))
                session.add(q)
                stats["questions_created"] += 1

        session.commit()
        print("\n==========================================")
        print("DATABASE IMPORT COMPLETED SUCCESSFULLY!")
        print("==========================================")
        print(f"Total Questions Created: {stats['questions_created']}")
        print(f"Total Question Groups Created: {stats['groups_created']}")
        print(f"Duplicates Skipped: {stats['duplicates_skipped']}")
        return dict(stats)

    except Exception as e:
        session.rollback()
        print(f"IMPORT FAILED: {e}")
        raise
    finally:
        session.close()
        dispose_engine()


if __name__ == "__main__":
    run_import()
