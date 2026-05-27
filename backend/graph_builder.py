import json
import os
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from models import GraphNode

client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """당신은 학문적 텍스트에서 핵심 개념을 추출하고 계층적 지식 구조를 설계하는 전문가입니다.

주어진 강의 자료를 분석하여 개념들의 부모-자식 트리 구조를 JSON 형식으로 반환하세요.

규칙:
1. 루트 노드는 강의의 가장 상위 주제 하나입니다.
2. 각 노드는 반드시 concept(개념명), description(2~3문장의 상세 설명), importance(0.0~1.0 중요도), children(하위 개념 목록)을 가집니다.
3. description은 단순 한 줄이 아니라, 이 개념이 무엇인지, 왜 중요한지, 어떤 맥락에서 등장하는지를 포함하여 충분히 설명하세요.
4. 트리 깊이는 최대 4단계(루트 포함)입니다. 가능한 한 4단계까지 세분화하세요.
5. 각 부모 노드는 최소 2개 이상의 자식 노드를 가져야 합니다.
6. 개념 간 위계와 논리적 인과관계를 명확히 반영하세요.
7. 말단 노드(leaf)는 구체적인 사례, 공식, 또는 세부 기법까지 담아야 합니다.
8. 전체 노드 수는 최소 15개 이상이어야 합니다.

반드시 아래 JSON 형식만 출력하세요. 설명이나 마크다운 없이 순수 JSON만:
{
  "concept": "루트 개념명",
  "description": "이 강의 전체를 아우르는 핵심 주제에 대한 2~3문장 설명",
  "importance": 1.0,
  "children": [
    {
      "concept": "중간 개념명",
      "description": "이 개념이 무엇이고, 왜 중요하며, 상위 개념과 어떻게 연결되는지 2~3문장으로 설명",
      "importance": 0.8,
      "children": [
        {
          "concept": "세부 개념명",
          "description": "구체적인 정의, 공식, 예시 등을 포함한 2~3문장 설명",
          "importance": 0.6,
          "children": [
            {
              "concept": "가장 세부적인 개념/사례",
              "description": "실제 적용 방법이나 구체적 예시를 포함한 2~3문장 설명",
              "importance": 0.4,
              "children": []
            }
          ]
        }
      ]
    }
  ]
}"""


async def build_graph(lecture_id: int, content: str, db: AsyncSession) -> list[GraphNode]:
    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0,
        max_tokens=4000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"다음 강의 자료를 분석해 최대한 세분화된 지식 그래프를 생성하세요:\n\n{content[:10000]}"},
        ],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    tree = json.loads(raw)

    nodes: list[GraphNode] = []

    async def _save_node(data: dict, parent_id: int | None, level: int):
        node = GraphNode(
            lecture_id=lecture_id,
            concept=data["concept"],
            description=data["description"],
            importance_score=float(data.get("importance", 0.5)),
            parent_id=parent_id,
            level=level,
        )
        db.add(node)
        await db.flush()
        nodes.append(node)
        for child_data in data.get("children", []):
            await _save_node(child_data, node.id, level + 1)

    await _save_node(tree, None, 0)
    await db.commit()
    return nodes
