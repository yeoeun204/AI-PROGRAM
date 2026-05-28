import re
import os
from groq import AsyncGroq

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

ALPHA = 0.7
BETA = 0.3
THRESHOLD_CORRECT = 0.70
THRESHOLD_WARNING = 0.50
QUANTITATIVE_THRESHOLD = 0.05

# 파이썬 비교/논리 연산자 목록
PYTHON_OPERATORS = [
    "==", "!=", ">=", "<=", ">", "<",
    "and", "or", "not", "in", "is",
    "+=", "-=", "*=", "/=", "%=",
]


def _is_code_like(text: str) -> bool:
    """답변이 코드/수식 형태인지 판별합니다."""
    code_patterns = [
        r"[=<>!]=",          # ==, !=, <=, >=
        r"\b(and|or|not|if|else|for|while|def|return|import)\b",
        r"[+\-*/]{1,2}=",    # +=, -=, *=, /=
        r"\b\d+\s*[+\-*/]\s*\d+",  # 수식: 1+2, 3*4
        r"\b[a-zA-Z_]\w*\s*[=<>]",  # 변수 비교: x > 0
    ]
    for pattern in code_patterns:
        if re.search(pattern, text):
            return True
    return False


def _extract_operators(text: str) -> list[str]:
    """텍스트에서 파이썬 연산자/키워드를 추출합니다."""
    found = []
    for op in PYTHON_OPERATORS:
        if op.isalpha():
            # 단어 연산자 (and, or, not): 단어 경계 체크
            if re.search(rf"\b{op}\b", text):
                found.append(op)
        else:
            # 기호 연산자 (==, !=, > 등)
            if op in text:
                found.append(op)
    return found


def _token_mismatch_check(user_answer: str, model_answer: str) -> dict:
    """
    파이썬 연산자 토큰 불일치 분석
    불일치 1개 이하 → Slip (단순 실수)
    불일치 2개 이상 → Mistake (개념 오해)
    """
    if not _is_code_like(user_answer) and not _is_code_like(model_answer):
        return {"is_code": False, "mismatch_count": 0, "is_slip": False}

    user_ops = set(_extract_operators(user_answer))
    model_ops = set(_extract_operators(model_answer))

    mismatch = user_ops.symmetric_difference(model_ops)
    mismatch_count = len(mismatch)
    is_slip = mismatch_count <= 1

    return {
        "is_code": True,
        "user_operators": list(user_ops),
        "model_operators": list(model_ops),
        "mismatched_operators": list(mismatch),
        "mismatch_count": mismatch_count,
        "is_slip": is_slip,
    }


def _check_keywords(user_answer: str, key_points: list[str]) -> tuple[int, int]:
    user_lower = user_answer.lower()
    matched = sum(1 for kw in key_points if kw.lower() in user_lower)
    return matched, len(key_points)


async def _llm_similarity(user_answer: str, model_answer: str) -> float:
    prompt = f"""당신은 대학교 교수입니다. 학생 답변이 모범 답안의 핵심 내용을 얼마나 담고 있는지 평가하세요.

채점 기준:
- 0.9~1.0: 핵심 개념을 모두 정확하게 서술함
- 0.7~0.9: 핵심 개념 대부분을 올바르게 서술함
- 0.5~0.7: 핵심 개념 일부를 서술했으나 빠진 부분이 있음
- 0.3~0.5: 방향은 맞지만 내용이 많이 부족함
- 0.0~0.3: 핵심 내용과 관련 없거나 완전히 틀림

중요: 완벽한 문장이 아니어도 핵심 개념만 맞으면 높은 점수를 주세요.
숫자 하나만 출력하세요.

[모범 답안] {model_answer}
[학생 답변] {user_answer}

유사도:"""

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
    if not user_answer.strip():
        return _empty_result(len(key_points))

    # 코드/수식 형태 판별 및 토큰 불일치 분석
    token_result = _token_mismatch_check(user_answer, model_answer)

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

    # Slip 판별
    # 코드 형태: 토큰 불일치 1개 이하면 Slip
    # 일반 텍스트: 의미는 유사한데 키워드 누락이면 Slip
    if token_result["is_code"]:
        is_slip = token_result["is_slip"] and status != "correct"
    else:
        is_slip = (cos_sim >= 0.55 and keyword_score < 0.5 and status != "correct")

    return {
        "cosine_similarity": round(cos_sim, 4),
        "keyword_score": round(keyword_score, 4),
        "final_score": round(final_score, 4),
        "matched_keywords": matched,
        "total_keywords": total,
        "status": status,
        "color": color,
        "is_slip": is_slip,
        "token_analysis": token_result if token_result["is_code"] else None,
    }


def evaluate_quantitative_answer(user_answer: str, model_answer: str) -> dict:
    """
    상대오차 = |정답 - 사용자답| / 정답
    정답이 0이면 절대오차로 전환
    토큰 불일치 1개 이하면 Slip으로 분류
    """
    try:
        user_val = float(user_answer.strip().replace(",", ""))
        correct_val = float(model_answer.strip().replace(",", ""))

        if abs(correct_val) < 1e-8:
            error = abs(user_val)
        else:
            error = abs(correct_val - user_val) / abs(correct_val)

        is_correct = error <= QUANTITATIVE_THRESHOLD
        final_score = max(0.0, min(1.0, 1.0 - error))

        # 토큰 불일치 분석도 함께 실행
        token_result = _token_mismatch_check(user_answer, model_answer)
        is_slip = (0.05 < error <= 0.20) or (token_result["is_code"] and token_result["is_slip"])

        return {
            "relative_error": round(error, 4),
            "final_score": round(final_score, 4),
            "status": "correct" if is_correct else "error",
            "color": "green" if is_correct else "red",
            "is_slip": is_slip,
            "token_analysis": token_result if token_result["is_code"] else None,
        }
    except ValueError:
        return {
            "relative_error": 1.0,
            "final_score": 0.0,
            "status": "error",
            "color": "red",
            "is_slip": False,
            "token_analysis": None,
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
        "token_analysis": None,
    }
