import json
import os
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from models import Quiz, GraphNode

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """당신은 교육 전문가입니다. 주어진 내용으로 주관식 문제 5개를 만드세요.

규칙:
1. 반드시 서술형 문제만 출제합니다.
2. easy 2개, medium 2개, hard 1개를 만드세요.
3. 각 문제는 반드시 어떤 핵심 개념(concept)을 테스트하는지 명시하세요.
4. 반드시 아래 JSON 형식만 출력하세요. 다른 말은 절대 하지 마세요.

[{"concept":"테스트하는 핵심 개념명","question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2","키워드3"],"difficulty":"easy"}]"""


def _match_node(concept: str, nodes: list[GraphNode]) -> GraphNode | None:
    """퀴즈가 테스트하는 개념과 가장 유사한 노드를 찾습니다."""
    concept_lower = concept.lower()

    # 1순위: 정확히 일치
    for node in nodes:
        if node.concept.lower() == concept_lower:
            return node

    # 2순위: 개념명이 포함된 경우
    for node in nodes:
        if concept_lower in node.concept.lower() or node.concept.lower() in concept_lower:
            return node

    # 3순위: 단어 단위로 겹치는 노드
    concept_words = set(concept_lower.split())
    best_node = None
    best_overlap = 0
    for node in nodes:
        node_words = set(node.concept.lower().split())
        overlap = len(concept_words & node_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_node = node

    return best_node


def _extract_json(raw: str) -> list:
    raw = raw.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end+1])
    raise ValueError("JSON 배열을 찾을 수 없습니다.")


async def _try_generate(content: str, count: int) -> list:
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        max_tokens=2500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"아래 내용으로 주관식 문제 {count}개를 JSON으로만 출력하세요:\n\n{content}"},
        ],
    )
    raw = response.choices[0].message.content
    return _extract_json(raw)


async def generate_quizzes(
    lecture_id: int,
    content: str,
    nodes: list[GraphNode],   # ← 노드 목록 받아서 매칭에 사용
    db: AsyncSession,
    count: int = 5,
) -> list[Quiz]:

    quiz_list = None

    for max_chars in [5000, 3000, 2000]:
        try:
            quiz_list = await _try_generate(content[:max_chars], count if max_chars > 2000 else 3)
            break
        except Exception as e:
            print(f"퀴즈 생성 실패 ({max_chars}자): {e}")

    if not quiz_list:
        quiz_list = [
            {
                "concept": nodes[0].concept if nodes else "핵심 개념",
                "question": "이 자료의 핵심 개념을 선택하고 그 중요성을 구체적인 이유를 들어 서술하세요.",
                "model_answer": "강의 자료의 핵심 개념을 파악하고 중요성을 논리적으로 설명할 수 있어야 합니다.",
                "key_points": ["핵심 개념", "중요성", "근거"],
                "difficulty": "medium",
            }
        ]

    quizzes: list[Quiz] = []
    for item in quiz_list:
        try:
            # 퀴즈가 테스트하는 개념과 가장 관련 있는 노드 찾기
            concept_name = item.get("concept", "")
            matched_node = _match_node(concept_name, nodes) if nodes else None

            quiz = Quiz(
                lecture_id=lecture_id,
                node_id=matched_node.id if matched_node else None,  # ← 노드 연결
                question=item["question"],
                model_answer=item["model_answer"],
                key_points=json.dumps(item.get("key_points", []), ensure_ascii=False),
                difficulty=item.get("difficulty", "medium"),
            )
            db.add(quiz)
            quizzes.append(quiz)
        except Exception as e:
            print(f"퀴즈 저장 오류: {e}")
            continue

    await db.commit()
    for q in quizzes:
        await db.refresh(q)
    return quizzes
