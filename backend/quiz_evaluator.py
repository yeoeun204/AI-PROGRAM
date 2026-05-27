"""
답변 평가 엔진
- 텍스트: LLM 의미 유사도(α=0.7) + 키워드 커버리지(β=0.3)
- 정량: 상대오차 기반
- 임계치: 0.90 정답 / 0.85 경고 / 미만 오류
"""
import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

ALPHA = 0.7
BETA = 0.3
THRESHOLD_CORRECT = 0.90
THRESHOLD_WARNING = 0.85
QUANTITATIVE_THRESHOLD = 0.05


def _check_keywords(user_answer: str, key_points: list[str]) -> tuple[int, int]:
    user_lower = user_answer.lower()
    matched = sum(1 for kw in key_points if kw.lower() in user_lower)
    return matched, len(key_points)


async def _llm_similarity(user_answer: str, model_answer: str) -> float:
    """LLM에게 의미적 유사도를 0.0~1.0 사이로 평가하게 합니다."""
    prompt = f"""아래 모범 답안과 학생 답변의 의미적 유사도를 평가하세요.
코사인 유사도처럼 0.0~1.0 사이 숫자 하나만 출력하세요. 설명 없이 숫자만.

모범 답안: {model_answer}

학생 답변: {user_answer}

유사도 (0.0~1.0):"""

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        score = float(raw.split()[0].replace(",", "."))
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5


async def evaluate_text_answer(
    user_answer: str,
    model_answer: str,
    key_points: list[str],
) -> dict:
    """
    최종 점수 = α × LLM유사도 + β × (만족한 키워드 수 / 전체 키워드 수)
    """
    if not user_answer.strip():
        return _empty_result(len(key_points))

    cos_sim = await _llm_similarity(user_answer, model_answer)

    matched, total = _check_keywords(user_answer, key_points)
    keyword_score = matched / total if total > 0 else 0.0

    final_score = ALPHA * cos_sim + BETA * keyword_score

    if final_score >= THRESHOLD_CORRECT:
        status, color = "correct", "green"
    elif final_score >= THRESHOLD_WARNING:
        status, color = "warning", "yellow"
    else:
        status, color = "error", "red"

    is_slip = (cos_sim >= THRESHOLD_WARNING and keyword_score < 0.6 and status != "correct")

    return {
        "cosine_similarity": round(cos_sim, 4),
        "keyword_score": round(keyword_score, 4),
        "final_score": round(final_score, 4),
        "matched_keywords": matched,
        "total_keywords": total,
        "status": status,
        "color": color,
        "is_slip": is_slip,
    }


def evaluate_quantitative_answer(user_answer: str, model_answer: str) -> dict:
    """상대오차 기반 정량 평가. 정답이 0이면 절대오차로 전환."""
    try:
        user_val = float(user_answer.strip().replace(",", ""))
        correct_val = float(model_answer.strip().replace(",", ""))

        if abs(correct_val) < 1e-8:
            error = abs(user_val)
        else:
            error = abs(correct_val - user_val) / abs(correct_val)

        is_correct = error <= QUANTITATIVE_THRESHOLD
        final_score = max(0.0, min(1.0, 1.0 - error))

        return {
            "relative_error": round(error, 4),
            "final_score": round(final_score, 4),
            "status": "correct" if is_correct else "error",
            "color": "green" if is_correct else "red",
            "is_slip": (0.05 < error <= 0.20),
        }
    except ValueError:
        return {
            "relative_error": 1.0,
            "final_score": 0.0,
            "status": "error",
            "color": "red",
            "is_slip": False,
        }


def _empty_result(total_keywords: int) -> dict:
    return {
        "cosine_similarity": 0.0,
        "keyword_score": 0.0,
        "final_score": 0.0,
        "matched_keywords": 0,
        "total_keywords": total_keywords,
        "status": "error",
        "color": "red",
        "is_slip": False,
    }
