# AI-диспетчер входящих задач команды

Внутренний инструмент на **LangGraph**: получает разнородные входящие и направляет каждое в свою ветку обработки.

Типы задач:
- **code_review** — изменения в коде (диф PR)
- **incident** — инцидент или алерт
- **analytics** — аналитический вопрос

Маршрут задаёт **граф** (условные рёбра), а не tool-calling модели.

## Текущий статус

| Релиз | Паттерн | Статус |
|-------|---------|--------|
| 0 | Routing — классификация и маршрутизация | готово |
| 1 | Parallelization — код-ревью | планируется |
| 2 | Orchestration — аналитика | планируется |
| 3 | Evaluator-optimizer — SQL | планируется |
| 4 | Fault tolerance — данные | планируется |

## Как это работает (Релиз 0)

```text
входящий файл ──▶ classify ──┬──▶ code_review ──▶ END
                             ├──▶ incident     ──▶ END
                             └──▶ analytics    ──▶ END
```

1. Классификатор читает текст и определяет категорию (structured output).
2. Роутер по полю `category` выбирает ветку через `add_conditional_edges`.
3. Обработчик ветки делает один LLM-вызов со своим системным промптом.

## Требования

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)
- Ключ OpenAI API

## Установка и запуск

```bash
# 1. Перейти в папку проекта
cd langchain2

# 2. Заполнить OPENAI_API_KEY в .env

# 3. Установить зависимости
uv sync

# 4. Запустить диспетчер на трёх тестовых файлах
uv run main.py
```

Скрипт прогонит `data/code_review.txt`, `data/incident.txt`, `data/analytics.txt`, выведет mermaid-схему графа, категорию и ответ обработчика. В конце — сводку маршрутизации (`OK` / `MISMATCH`).

## Переменные окружения (`.env`)

```env
OPENAI_BASE_URL=https://polza.ai/api/v1
OPENAI_API_KEY=pza_...

# Langfuse — опционально, пока выключено
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

Когда поднимешь Langfuse — поставь `LANGFUSE_ENABLED=true` и заполни ключи.

## Структура проекта

```
langchain2/
├── main.py              # граф и точка входа
├── data/                # входные файлы для тестов
│   ├── code_review.txt
│   ├── incident.txt
│   └── analytics.txt
├── .env                 # ключи (не коммитить)
├── pyproject.toml
├── .cursor/plan/        # планы по релизам
└── .cursor/done/        # итоги по релизам
```

## Стек

- `langgraph`, `langchain`, `langchain-openai`
- Модель: `gpt-5.4-mini`, `temperature=0`
- `langfuse` — трассировка (заглушка, включается флагом)
