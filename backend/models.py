from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Lecture(Base):
    """업로드된 강의 자료"""
    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    nodes: Mapped[List["GraphNode"]] = relationship(
        "GraphNode", back_populates="lecture", cascade="all, delete-orphan"
    )
    quizzes: Mapped[List["Quiz"]] = relationship(
        "Quiz", back_populates="lecture", cascade="all, delete-orphan"
    )


class GraphNode(Base):
    """지식 그래프의 개념 노드 (부모-자식 트리 구조)"""
    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("graph_nodes.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)  # LLM 판단 중요도 (0~1)

    lecture: Mapped["Lecture"] = relationship("Lecture", back_populates="nodes")
    children: Mapped[List["GraphNode"]] = relationship(
        "GraphNode", back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[Optional["GraphNode"]] = relationship(
        "GraphNode", back_populates="children", remote_side="GraphNode.id"
    )
    node_score: Mapped[Optional["NodeScore"]] = relationship(
        "NodeScore", back_populates="node", uselist=False, cascade="all, delete-orphan"
    )


class Quiz(Base):
    """생성된 주관식 퀴즈"""
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    model_answer: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[str] = mapped_column(Text, nullable=False)       # JSON 배열
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    answer_type: Mapped[str] = mapped_column(String(20), default="text")  # text / quantitative
    recommended_time: Mapped[int] = mapped_column(Integer, default=120)   # 초 단위
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lecture: Mapped["Lecture"] = relationship("Lecture", back_populates="quizzes")
    attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt", back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizAttempt(Base):
    """사용자의 퀴즈 시도 및 평가 결과"""
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)

    # 평가 점수
    cosine_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    keyword_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)

    # 판정
    status: Mapped[str] = mapped_column(String(20), default="error")   # correct / warning / error
    error_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # slip / mistake / language
    is_slip: Mapped[bool] = mapped_column(Boolean, default=False)

    # 시간
    time_spent: Mapped[int] = mapped_column(Integer, default=0)  # 초 단위
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")


class NodeScore(Base):
    """지식 그래프 노드별 학습 성취도 및 가중치"""
    __tablename__ = "node_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), nullable=False, unique=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)

    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)

    # 가중치 엔진 결과
    static_weight: Mapped[float] = mapped_column(Float, default=0.0)
    dynamic_weight: Mapped[float] = mapped_column(Float, default=0.0)
    final_weight: Mapped[float] = mapped_column(Float, default=0.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    node: Mapped["GraphNode"] = relationship("GraphNode", back_populates="node_score")
