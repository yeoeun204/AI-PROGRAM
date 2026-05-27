from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Lecture(Base):
    __tablename__ = "lectures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    nodes: Mapped[List["GraphNode"]] = relationship("GraphNode", back_populates="lecture", cascade="all, delete-orphan")
    quizzes: Mapped[List["Quiz"]] = relationship("Quiz", back_populates="lecture", cascade="all, delete-orphan")


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("graph_nodes.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)

    lecture: Mapped["Lecture"] = relationship("Lecture", back_populates="nodes")
    children: Mapped[List["GraphNode"]] = relationship("GraphNode", back_populates="parent", cascade="all, delete-orphan")
    parent: Mapped[Optional["GraphNode"]] = relationship("GraphNode", back_populates="children", remote_side="GraphNode.id")
    node_score: Mapped[Optional["NodeScore"]] = relationship("NodeScore", back_populates="node", uselist=False, cascade="all, delete-orphan")


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("graph_nodes.id"), nullable=True)  # ← 연결된 노드
    question: Mapped[str] = mapped_column(Text, nullable=False)
    model_answer: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    answer_type: Mapped[str] = mapped_column(String(20), default="text")
    recommended_time: Mapped[int] = mapped_column(Integer, default=120)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lecture: Mapped["Lecture"] = relationship("Lecture", back_populates="quizzes")
    attempts: Mapped[List["QuizAttempt"]] = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), nullable=False)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    cosine_similarity: Mapped[float] = mapped_column(Float, default=0.0)
    keyword_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="error")
    error_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_slip: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")


class NodeScore(Base):
    __tablename__ = "node_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), nullable=False, unique=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0.0)
    static_weight: Mapped[float] = mapped_column(Float, default=0.0)
    dynamic_weight: Mapped[float] = mapped_column(Float, default=0.0)
    final_weight: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    node: Mapped["GraphNode"] = relationship("GraphNode", back_populates="node_score")
