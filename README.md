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
| 1 | Parallelization — код-ревью | готово |
| 2 | Orchestration — аналитика | планируется |
| 3 | Evaluator-optimizer — SQL | планируется |
| 4 | Fault tolerance — данные | планируется |

## Как это работает

```text
входящий файл ──▶ classify ──┬──▶ code_review ──┬──▶ 3 проверки ──▶ aggregate ──▶ END
                             ├──▶ incident     ──────────────────────────────────▶ END
                             └──▶ analytics    ──────────────────────────────────▶ END
```

1. Классификатор определяет категорию (structured output).
2. Роутер выбирает ветку через `add_conditional_edges`.
3. **code_review** — fan-out: 3 параллельные проверки (API, тесты, риск) → fan-in в агрегатор с вердиктом `approve` / `changes_requested` / `block`.
4. **incident** / **analytics** — заглушки с одним LLM-вызовом.

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

# 4. Запустить диспетчер
uv run main.py
```

Скрипт прогонит тестовые файлы, выведет mermaid-схему, отчёты проверок и вердикт. Для code review дополнительно сравнивает risky и clean дифы.

## Переменные окружения (`.env`)

Скопируй `.env.example` → `.env` и заполни ключи.

```env
OPENAI_BASE_URL=https://polza.ai/api/v1
OPENAI_API_KEY=pza_...

LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3011
NO_PROXY=localhost,127.0.0.1
```

## Langfuse tracing

Трассировка через [Langfuse CallbackHandler](https://langfuse.com/docs/integrations/langchain) + `propagate_attributes` (модуль [`langfuse_tracing.py`](langfuse_tracing.py)).

- Имя трейса: `task-dispatcher/<имя_входа>`
- Теги: `task-dispatcher`, имя файла
- `flush()` + `shutdown()` в конце прогона

Локальный Langfuse: `docker compose up -d`, UI на `http://localhost:3011`.

Skill установлен: `.agents/skills/langfuse` (из [langfuse/skills](https://github.com/langfuse/skills)).

## Структура проекта

```
langchain2/
├── main.py              # граф и точка входа
├── langfuse_tracing.py  # Langfuse tracing
├── .agents/skills/langfuse/  # Langfuse AI skill
├── data/                # входные файлы для тестов
│   ├── code_review.txt        # рискованный диф (auth)
│   ├── code_review_clean.txt  # чистый диф (версия + тест)
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
