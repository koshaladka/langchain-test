import os
from pathlib import Path
from typing import Literal

from load_dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

load_dotenv()

model = init_chat_model("openai:gpt-5.4-mini", temperature=0)

DATA_DIR = Path(__file__).parent / "data"
INPUT_FILES = {
    "code_review": DATA_DIR / "code_review.txt",
    "incident": DATA_DIR / "incident.txt",
    "analytics": DATA_DIR / "analytics.txt",
}


class Route(BaseModel):
    category: Literal["code_review", "incident", "analytics"]


class State(TypedDict):
    input_text: str
    category: str
    result: str


classifier = model.with_structured_output(Route)


# Определяет тип входящей задачи и записывает категорию в состояние
def classify(state: State) -> dict:
    route: Route = classifier.invoke(
        "Определи тип входящей задачи. Варианты: code_review, incident, analytics.\n\n"
        f"Входящее:\n{state['input_text']}",
    )
    return {"category": route.category}


# Обрабатывает задачу код-ревью: краткий обзор рисков и замечаний по дифу
def handle_code_review(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты опытный ревьюер кода. Получив описание изменений или диф, составь:\n"
                    "1. Краткое резюме изменений.\n"
                    "2. Критичные замечания (безопасность, баги).\n"
                    "3. Рекомендации по улучшению.\n"
                    "4. Итог: approve / changes_requested / block с обоснованием."
                )
            ),
            HumanMessage(content=state["input_text"]),
        ],
    )
    return {"result": response.content}


# Обрабатывает инцидент: приоритет, шаги триажа и что проверить в первую очередь
def handle_incident(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты инженер on-call. Получив описание инцидента или алерта, составь:\n"
                    "1. Приоритет (critical / high / medium / low) с обоснованием.\n"
                    "2. Пошаговый план триажа.\n"
                    "3. Что проверить в логах, метриках и недавних деплоях.\n"
                    "4. Вероятную причину и следующий шаг."
                )
            ),
            HumanMessage(content=state["input_text"]),
        ],
    )
    return {"result": response.content}


# Обрабатывает аналитический вопрос: какие метрики и срезы нужны для ответа
def handle_analytics(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты аналитик данных. Получив аналитический вопрос, составь:\n"
                    "1. Ключевые метрики для ответа.\n"
                    "2. Рекомендуемые срезы данных (платформа, канал, когорта и т.д.).\n"
                    "3. Гипотезы, которые стоит проверить.\n"
                    "4. Краткий план анализа."
                )
            ),
            HumanMessage(content=state["input_text"]),
        ],
    )
    return {"result": response.content}


# По категории из состояния выбирает имя следующего узла графа
def route_by_category(state: State) -> Literal["code_review", "incident", "analytics"]:
    return state["category"]


# Возвращает колбэки Langfuse, если трассировка включена в .env
def get_callbacks() -> list:
    if os.getenv("LANGFUSE_ENABLED", "false").lower() == "true":
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    return []


# Собирает и компилирует граф диспетчера с классификатором и тремя ветками
def build_graph():
    builder = StateGraph(State)

    builder.add_node("classify", classify)
    builder.add_node("code_review", handle_code_review)
    builder.add_node("incident", handle_incident)
    builder.add_node("analytics", handle_analytics)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_by_category,
        ["code_review", "incident", "analytics"],
    )
    builder.add_edge("code_review", END)
    builder.add_edge("incident", END)
    builder.add_edge("analytics", END)

    return builder.compile()


# Прогоняет один входной файл через граф и печатает результат
def run_input(graph, name: str, path: Path) -> dict:
    input_text = path.read_text(encoding="utf-8")
    print(f"\n{'=' * 60}")
    print(f"Вход: {name} ({path.name})")
    print("=" * 60)
    print(graph.get_graph().draw_mermaid())
    output = graph.invoke(
        {"input_text": input_text, "category": "", "result": ""},
        config={"callbacks": get_callbacks()},
    )
    print(f"\nКатегория: {output['category']}")
    print(f"\nОтвет обработчика:\n{output['result']}")
    return output


# Точка входа: прогоняет все тестовые файлы из data/
def main():
    graph = build_graph()
    results = {}
    for name, path in INPUT_FILES.items():
        results[name] = run_input(graph, name, path)

    if os.getenv("LANGFUSE_ENABLED", "false").lower() == "true":
        from langfuse import get_client

        get_client().flush()

    print(f"\n{'=' * 60}")
    print("Сводка маршрутизации:")
    for name, output in results.items():
        ok = "OK" if output["category"] == name else "MISMATCH"
        print(f"  {name}: {output['category']} [{ok}]")


if __name__ == "__main__":
    main()
