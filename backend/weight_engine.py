"""
가중치 엔진 함수
W_final(i) = w1 × [W_KG(i) + Vi] + w2 × [(Ei × Si) × Ti]

정적 가중치: W_static = α × Ic + (1-α) × (dc / Dmax)
동적 가중치: W_dynamic = γ × ec + (1-γ) × sigmoid(tc/Tc - 1)
"""
import math
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import GraphNode, NodeScore

# ── 파라미터 ────────────────────────────────
ALPHA_STATIC = 0.4      # LLM 중요도 vs 트리 깊이 균형 (기본 권장값 0.4)
GAMMA_DYNAMIC = 0.7     # 오답률 vs 시간 지연 균형 (기본 권장값 0.7)
ABILITY_BONUS = 0.15    # 역량 노드 가산점 (Vi)
DEFAULT_REC_TIME = 120  # 권장 풀이 시간(초)

# 시스템 목적 플래그
# 퀴즈 모드: 동적(현재 오답 행동) 중시
# 진단 모드: 정적(지식 구조 깊이) 중시
MODE_WEIGHTS = {
    "quiz":     (0.3, 0.7),   # (w1, w2)
    "assess":   (0.7, 0.3),
}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-50, min(50, x))))


def compute_static_weight(importance: float, depth: int, max_depth: int) -> float:
    """
    W_static = α × Ic + (1 - α) × (dc / Dmax)
    Ic: LLM 판단 중요도, dc: 트리 깊이, Dmax: 최대 깊이
    """
    depth_ratio = (depth / max_depth) if max_depth > 0 else 0.0
    return ALPHA_STATIC * importance + (1 - ALPHA_STATIC) * depth_ratio


def compute_dynamic_weight(error_rate: float, avg_time: float,
                            rec_time: float = DEFAULT_REC_TIME) -> float:
    """
    W_dynamic = γ × ec + (1 - γ) × sigmoid(tc/Tc - 1)
    ec: 오답률, tc: 평균 소요 시간, Tc: 권장 시간
    소요 시간이 권장 시간을 넘을수록 S자 곡선으로 가파르게 증가
    """
    if rec_time <= 0:
        time_load = 0.5
    else:
        time_load = sigmoid(avg_time / rec_time - 1)
    return GAMMA_DYNAMIC * error_rate + (1 - GAMMA_DYNAMIC) * time_load


def compute_final_weight(
    static_w: float,
    error_rate: float,
    avg_time: float,
    is_slip: bool,
    is_ability_node: bool = False,
    rec_time: float = DEFAULT_REC_TIME,
    mode: str = "quiz",
) -> dict:
    """
    W_final(i) = w1 × [W_KG(i) + Vi] + w2 × [(Ei × Si) × Ti]

    Si: Slip이면 0.5 (가중치 감쇄), Mistake이면 1.0 (가중치 유지)
    Vi: 역량/능력 노드이면 0.15 가산점
    Ti: 시간 부하 계수 (시그모이드)
    """
    w1, w2 = MODE_WEIGHTS.get(mode, (0.3, 0.7))
    vi = ABILITY_BONUS if is_ability_node else 0.0
    si = 0.5 if is_slip else 1.0
    ti = sigmoid(avg_time / rec_time - 1) if rec_time > 0 else 0.5

    dynamic_w = compute_dynamic_weight(error_rate, avg_time, rec_time)

    kg_component = static_w + vi
    student_component = error_rate * si * ti

    final = w1 * kg_component + w2 * student_component

    return {
        "static_weight": round(static_w, 4),
        "dynamic_weight": round(dynamic_w, 4),
        "final_weight": round(min(1.0, final), 4),
    }


async def update_node_weight(
    node: GraphNode,
    new_score: float,
    time_spent: int,
    is_slip: bool,
    db: AsyncSession,
    mode: str = "quiz",
) -> NodeScore:
    """퀴즈 시도 후 해당 노드의 성취도와 가중치를 업데이트합니다."""
    result = await db.execute(
        select(NodeScore).where(NodeScore.node_id == node.id)
    )
    node_score = result.scalar_one_or_none()

    if not node_score:
        node_score = NodeScore(node_id=node.id, lecture_id=node.lecture_id)
        db.add(node_score)

    # 통계 갱신
    node_score.attempt_count += 1
    if new_score >= 0.90:
        node_score.correct_count += 1

    # 이동 평균 avg_score
    n = node_score.attempt_count
    node_score.avg_score = round(
        (node_score.avg_score * (n - 1) + new_score) / n, 4
    )

    error_rate = 1.0 - (node_score.correct_count / node_score.attempt_count)

    # 전체 노드에서 max_depth 계산
    all_nodes_r = await db.execute(
        select(GraphNode).where(GraphNode.lecture_id == node.lecture_id)
    )
    max_depth = max((n.level for n in all_nodes_r.scalars().all()), default=0)

    static_w = compute_static_weight(node.importance_score, node.level, max_depth)
    weights = compute_final_weight(
        static_w, error_rate, float(time_spent), is_slip,
        rec_time=DEFAULT_REC_TIME, mode=mode,
    )

    node_score.static_weight = weights["static_weight"]
    node_score.dynamic_weight = weights["dynamic_weight"]
    node_score.final_weight = weights["final_weight"]
    node_score.updated_at = datetime.utcnow()

    await db.commit()
    return node_score
