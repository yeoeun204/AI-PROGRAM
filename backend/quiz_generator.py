import json
import os
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from models import Quiz

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """당신은 대학 강의 내용을 바탕으로 학습자의 깊은 이해를 검증하는 주관식 문제를 출제하는 교육 전문가입니다.

핵심 원칙:
1. 반드시 주관식/서술형 문제만 출제합니다. 객관식, OX, 단답형 금지.
2. 단순 암기가 아닌, 개념 간의 관계, 원인-결과, 적용력을 묻는 문제를 만드세요.
3. 학습자가 자신의 논리로 직접 설명해야만 풀 수 있는 문제여야 합니다.
4. easy 2개, medium 2개, hard 1개를 만들어주세요.

반드시 아래 JSON 배열 형식만 출력하세요. 마크다운 없이 순수 JSON만:
[
  {
    "question": "문제 내용",
    "model_answer": "모범 답안 (3~5문장)",
    "key_points": ["핵심 키워드1", "핵심 키워드2", "핵심 키워드3"],
    "difficulty": "easy"
  }
]"""


async def generate_quizzes(
    lecture_id: int,
    content: str,
    db: AsyncSession,
    count: int = 5,
) -> list[Quiz]:
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.4,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"다음 강의 자료를 바탕으로 주관식 문제 {count}개를 생성하세요:\n\n{content[:8000]}"},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    quiz_list = json.loads(raw)

    quizzes: list[Quiz] = []
    for item in quiz_list:
        quiz = Quiz(
            lecture_id=lecture_id,
            question=item["question"],
            model_answer=item["model_answer"],
            key_points=json.dumps(item["key_points"], ensure_ascii=False),
            difficulty=item.get("difficulty", "medium"),
        )
        db.add(quiz)
        quizzes.append(quiz)

    await db.commit()
    for q in quizzes:
        await db.refresh(q)
    return quizzes
