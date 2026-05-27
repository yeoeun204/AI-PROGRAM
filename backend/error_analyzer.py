"""
오답 원인 분석 엔진 (Groq 기반)

[인과 관계 추론 3가지 규칙]
Rule 1 (상위 개념 부재): 부모 노드 평균 성취도 < 0.60
Rule 2 (개념 미숙지): 부모 노드 ≥ 0.60 이지만 현재 노드 실패
Rule 3 (언어적 어려움): 유사도 거의 0 → 핵심 용어 오해

[Multi-Agent 구조]
Agent A: 논리적 오류(개념 오해) 탐색
Agent B: 단순 연산/기입 실수 탐색
Agent C: 최종 분류 + 피드백 생성
"""
import json
import os
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import GraphNode, NodeScore

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

PREREQUISITE_THRESHOLD = 0.60


async def _get_node_avg_score(node_id: int, db: AsyncSession) -> float:
    result = await db.execute(select(NodeScore).where(NodeScore.node_id == node_id))
    score = result.scalar_one_or_none()
    return score.avg_score if score else 1.0


async def _get_parent_chain(node: GraphNode, db: AsyncSession) -> list[GraphNode]:
    chain = []
    current = node
    while current.parent_id:
        result = await db.execute(select(GraphNode).where(GraphNode.id == current.parent_id))
        parent = result.scalar_one_or_none()
        if not parent:
            break
        chain.append(parent)
        current = parent
    return chain


async def apply_causal_rules(
    node: GraphNode,
    current_score: float,
    cos_sim: float,
    db: AsyncSession,
) -> dict:
    """3가지 인과 관계 추론 규칙을 순서대로 적용합니다."""
    parent_chain = await _get_parent_chain(node, db)

    if parent_chain:
        parent_scores = [await _get_node_avg_score(p.id, db) for p in parent_chain]
        avg_parent = sum(parent_scores) / len(parent_scores)

        # Rule 1 — 상위 개념 부재
        if avg_parent < PREREQUISITE_THRESHOLD:
            weak = [{"id": p.id, "concept": p.concept}
                    for p, s in zip(parent_chain, parent_scores)
                    if s < PREREQUISITE_THRESHOLD]
            return {
                "rule": "missing_prerequisite",
                "cause": "상위 개념 부재",
                "description": (
                    f"선행 개념({', '.join(w['concept'] for w in weak)})의 "
                    "성취도가 부족합니다. 기초 개념부터 다시 학습하세요."
                ),
                "review_nodes": weak,
                "priority": "high",
            }

        # Rule 2 — 개념 미숙지
        if avg_parent >= PREREQUISITE_THRESHOLD and current_score < 0.85:
            return {
                "rule": "concept_misunderstanding",
                "cause": "개념 미숙지",
                "description": (
                    f"선행 개념은 이해했지만 '{node.concept}'의 핵심 키워드나 "
                    "공식 적용에 오류가 있습니다. 이 개념의 정의와 적용법을 다시 확인하세요."
                ),
                "review_nodes": [{"id": node.id, "concept": node.concept}],
                "priority": "medium",
            }

    # Rule 3 — 언어적 어려움
    if cos_sim < 0.3:
        return {
            "rule": "language_difficulty",
            "cause": "언어적 어려움",
            "description": (
                f"'{node.concept}'에서 사용되는 핵심 용어의 정의 자체를 오해했을 수 있습니다. "
                "문제에 등장한 도메인 용어를 먼저 정확히 파악하세요."
            ),
            "review_nodes": [{"id": node.id, "concept": node.concept}],
            "priority": "medium",
        }

    return {
        "rule": "root_concept_gap",
        "cause": "기초 개념 공백",
        "description": (
            f"'{node.concept}'은 이 강의의 핵심 개념입니다. "
            "강의 자료를 처음부터 다시 검토하세요."
        ),
        "review_nodes": [{"id": node.id, "concept": node.concept}],
        "priority": "high",
    }


async def multi_agent_analysis(
    question: str,
    user_answer: str,
    model_answer: str,
) -> dict:
    """Multi-Agent 구조로 오답 원인을 심층 분석합니다."""
    prompt = f"""당신은 학생의 오답을 분석하는 교육 AI입니다.
아래 3개의 에이전트로 순서대로 분석하세요.

[문제] {question}
[모범 답안] {model_answer}
[학생 답변] {user_answer}

Agent A (논리 오류): 개념이나 인과관계를 잘못 이해한 부분은?
Agent B (단순 실수): 계산 실수, 용어 혼동, 기입 오류가 있는가?
Agent C (최종 분류): mistake(개념 오해) / slip(단순 실수) / language(용어 오독) 중 하나로 분류하고 피드백 작성.

반드시 아래 JSON 형식만 출력하세요. 마크다운 없이 순수 JSON만:
{{
  "agent_a": "논리 오류 분석 (1~2문장)",
  "agent_b": "단순 실수 분석 (1~2문장)",
  "error_type": "mistake|slip|language",
  "feedback": "학생에게 줄 피드백 (2~3문장)"
}}"""

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except Exception:
        return {
            "agent_a": "분석 불가",
            "agent_b": "분석 불가",
            "error_type": "mistake",
            "feedback": "오답 원인을 자동 분석하지 못했습니다. 모범 답안과 직접 비교해보세요.",
        }
