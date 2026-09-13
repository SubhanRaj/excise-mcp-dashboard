"""Chat system prompt and the Ollama tool schemas for /api/chat's `tools=`.
MCP_ENGINES.md §Tools (chat/tools.py).
"""

from pydantic import BaseModel

from app.chat.tools import MakeChartArgs, RunSqlQueryArgs, SearchKnowledgeArgs

CHAT_SYSTEM_PROMPT = """You are a conversational analyst for the UP Excise department.

Three tools are available:
- search_knowledge: retrieves UP Excise acts, rules, and policy text. Use it for
  questions about the law. Cite the section and link when you use a result. If
  nothing matches, say so rather than guessing.
- run_sql_query: runs a read-only query against the excise analytics data. Use
  it for questions about numbers.
- make_chart: charts the most recent run_sql_query result in this conversation.
  Use it only after run_sql_query, and only when a chart would help.

Call a tool only when the question needs it — answer a definitional question
directly, with no tool call.
"""


def _tool_schema(name: str, description: str, args_model: type[BaseModel]) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": args_model.model_json_schema(),
        },
    }


CHAT_TOOL_SCHEMAS: list[dict[str, object]] = [
    _tool_schema(
        "search_knowledge", "Retrieve UP Excise acts, rules, and policy text.", SearchKnowledgeArgs
    ),
    _tool_schema(
        "run_sql_query",
        "Run a read-only SQL query against the excise analytics data.",
        RunSqlQueryArgs,
    ),
    _tool_schema("make_chart", "Chart the most recent run_sql_query result.", MakeChartArgs),
]
