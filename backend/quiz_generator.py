import json
import os
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from models import Quiz

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """당신은 교육 전문가입니다. 주어진 내용을 바탕으로 주관식 문제 5개를 만드세요.

규칙:
1. 반드시 서술형 문제만 출제합니다.
2. easy 2개, medium 2개, hard 1개를 만드세요.
3. 반드시 아래 JSON 형식만 출력하세요. 다른 말은 절대 하지 마세요.

[{"question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2","키워드3"],"difficulty":"easy"},{"question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2"],"difficulty":"easy"},{"question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2"],"difficulty":"medium"},{"question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2"],"difficulty":"medium"},{"question":"문제","model_answer":"모범답안","key_points":["키워드1","키워드2"],"difficulty":"hard"}]"""


def _extract_json(raw: str) -> list:
    """AI 응답에서 JSON 배열만 추출합니다."""
    raw = raw.strip()
    # 마크다운 펜스 제거
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # [ ] 사이만 추출
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end+1])
    raise ValueError("JSON 배열을 찾을 수 없습니다.")


async def _try_generate(content: str, count: int) -> list:
    """퀴즈 생성을 시도합니다. 실패시 예외를 발생시킵니다."""
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
    db: AsyncSession,
    count: int = 5,
) -> list[Quiz]:

    quiz_list = None

    # 1차 시도: 앞 5000자
    try:
        quiz_list = await _try_generate(content[:5000], count)
    except Exception as e:
        print(f"1차 퀴즈 생성 실패: {e}")

    # 2차 시도: 앞 3000자로 줄여서 재시도
    if not quiz_list:
        try:
            quiz_list = await _try_generate(content[:3000], count)
        except Exception as e:
            print(f"2차 퀴즈 생성 실패: {e}")

    # 3차 시도: 문제 수를 3개로 줄여서 재시도
    if not quiz_list:
        try:
            quiz_list = await _try_generate(content[:2000], 3)
        except Exception as e:
            print(f"3차 퀴즈 생성 실패: {e}")

    # 모두 실패시 기본 퀴즈
    if not quiz_list:
        print("퀴즈 생성 전체 실패 — 기본 퀴즈로 대체")
        quiz_list = [
            {
                "question": "이 자료의 가장 핵심적인 개념을 선택하고, 그 개념이 왜 중요한지 구체적인 이유를 들어 서술하세요.",
                "model_answer": "자료의 핵심 개념을 파악하고 그 중요성을 논리적으로 설명할 수 있어야 합니다.",
                "key_points": ["핵심 개념", "중요성", "근거"],
                "difficulty": "medium",
            },
            {
                "question": "이 자료에서 다루는 주요 개념들 사이의 관계를 설명하세요.",
                "model_answer": "주요 개념들의 상호 관계와 연결 고리를 파악하여 설명할 수 있어야 합니다.",
                "key_points": ["개념 관계", "연결", "구조"],
                "difficulty": "hard",
            },
        ]

    # DB 저장
    quizzes: list[Quiz] = []
    for item in quiz_list:
        try:
            quiz = Quiz(
                lecture_id=lecture_id,
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
