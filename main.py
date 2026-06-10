import operator
from pathlib import Path
from typing import Annotated, Literal

from langchain.chat_models import init_chat_model
from langfuse_tracing import build_invoke_config, flush_traces, trace_context
from langchain.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

model = init_chat_model("openai:gpt-5.4-mini", temperature=0)

DATA_DIR = Path(__file__).parent / "data"
INPUT_FILES = {
    "code_review": DATA_DIR / "code_review.txt",
    "incident": DATA_DIR / "incident.txt",
    "analytics": DATA_DIR / "analytics.txt",
}
CODE_REVIEW_DIFFS = {
    "risky": DATA_DIR / "code_review.txt",
    "clean": DATA_DIR / "code_review_clean.txt",
}


class Route(BaseModel):
    category: Literal["code_review", "incident", "analytics"]


class ReviewVerdict(BaseModel):
    verdict: Literal["approve", "changes_requested", "block"]
    reasoning: str


class State(TypedDict):
    input_text: str
    category: str
    reviews: Annotated[list, operator.add]
    result: str


classifier = model.with_structured_output(Route)
verdict_model = model.with_structured_output(ReviewVerdict)


# Определяет тип входящей задачи и записывает категорию в состояние
def classify(state: State) -> dict:
    route: Route = classifier.invoke(
        "Определи тип входящей задачи. Варианты: code_review, incident, analytics.\n\n"
        f"Входящее:\n{state['input_text']}",
    )
    return {"category": route.category}


# Точка входа в ветку код-ревью — передаёт управление параллельным проверкам
def code_review_entry(state: State) -> dict:
    return {}


# Проверяет обратную совместимость API в дифе
def check_api_compat(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты эксперт по обратной совместимости API. "
                    "Проверь diff на breaking changes: изменение контрактов, "
                    "удаление полей, смену формата ответов, изменение кодов ошибок. "
                    "Будь конкретен. Отвечай на русском."
                )
            ),
            HumanMessage(content=f"Проверь diff:\n\n{state['input_text']}"),
        ],
    )
    return {"reviews": [f"[API совместимость]\n{response.content}"]}


# Проверяет, покрыты ли изменённые функции тестами
def check_test_coverage(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты эксперт по тестированию. Оцени, есть ли в diff изменения тестов "
                    "для затронутого кода. Укажи, какие функции изменены без тестов. "
                    "Отвечай на русском."
                )
            ),
            HumanMessage(content=f"Проверь diff:\n\n{state['input_text']}"),
        ],
    )
    return {"reviews": [f"[Покрытие тестами]\n{response.content}"]}


# Оценивает риск изменения: размер диффа и критичные файлы
def check_change_risk(state: State) -> dict:
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты эксперт по оценке рисков изменений. Оцени размер diff, "
                    "затронуты ли критичные области (auth, billing, migrations, payments). "
                    "Укажи уровень риска. Отвечай на русском."
                )
            ),
            HumanMessage(content=f"Проверь diff:\n\n{state['input_text']}"),
        ],
    )
    return {"reviews": [f"[Риск изменения]\n{response.content}"]}


# Собирает отчёты проверок и выносит итоговый вердикт
def aggregate_review(state: State) -> dict:
    combined = "\n\n".join(state["reviews"])
    verdict: ReviewVerdict = verdict_model.invoke(
        [
            SystemMessage(
                content=(
                    "Ты старший ревьюер. На основе трёх независимых проверок "
                    "(API совместимость, покрытие тестами, риск изменения) "
                    "вынеси вердикт: approve, changes_requested или block. "
                    "Дай краткое обоснование на русском."
                )
            ),
            HumanMessage(content=f"Отчёты проверок:\n\n{combined}"),
        ],
    )
    result = f"Вердикт: {verdict.verdict}\n\n{verdict.reasoning}"
    return {"result": result}


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


# Собирает и компилирует граф диспетчера с классификатором и тремя ветками
def build_graph():
    builder = StateGraph(State)

    builder.add_node("classify", classify)
    builder.add_node("code_review", code_review_entry)
    builder.add_node("check_api_compat", check_api_compat)
    builder.add_node("check_test_coverage", check_test_coverage)
    builder.add_node("check_change_risk", check_change_risk)
    builder.add_node("aggregate_review", aggregate_review)
    builder.add_node("incident", handle_incident)
    builder.add_node("analytics", handle_analytics)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_by_category,
        ["code_review", "incident", "analytics"],
    )

    builder.add_edge("code_review", "check_api_compat")
    builder.add_edge("code_review", "check_test_coverage")
    builder.add_edge("code_review", "check_change_risk")
    builder.add_edge("check_api_compat", "aggregate_review")
    builder.add_edge("check_test_coverage", "aggregate_review")
    builder.add_edge("check_change_risk", "aggregate_review")
    builder.add_edge("aggregate_review", END)

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
    invoke_config = build_invoke_config(name, path.name)
    with trace_context(name, path.name):
        output = graph.invoke(
            {"input_text": input_text, "category": "", "reviews": [], "result": ""},
            config=invoke_config,
        )
    print(f"\nКатегория: {output['category']}")
    if output.get("reviews"):
        print("\n--- Отчёты проверок ---")
        for review in output["reviews"]:
            print(review)
            print("-" * 40)
    print(f"\nОтвет обработчика:\n{output['result']}")
    return output


# Прогоняет оба code review дифа и выводит сравнение вердиктов
def run_code_review_cases(graph) -> dict:
    print(f"\n{'#' * 60}")
    print("Сравнение code review: risky vs clean")
    print("#" * 60)
    results = {}
    for label, path in CODE_REVIEW_DIFFS.items():
        results[label] = run_input(graph, f"code_review_{label}", path)
    return results


# Точка входа: прогоняет все тестовые файлы из data/
def main():
    graph = build_graph()
    results = {}
    for name, path in INPUT_FILES.items():
        results[name] = run_input(graph, name, path)

    review_results = run_code_review_cases(graph)

    flush_traces()

    print(f"\n{'=' * 60}")
    print("Сводка маршрутизации:")
    for name, output in results.items():
        ok = "OK" if output["category"] == name else "MISMATCH"
        print(f"  {name}: {output['category']} [{ok}]")

    print("\nСводка code review вердиктов:")
    for label, output in review_results.items():
        verdict_line = output["result"].split("\n")[0]
        print(f"  {label}: {verdict_line}")


if __name__ == "__main__":
    main()
