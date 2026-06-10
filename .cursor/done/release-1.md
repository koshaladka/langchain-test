# Релиз 1 — готово

## Что сделано

- Ветка `code_review` заменена на fan-out/fan-in в [`main.py`](../../main.py)
- Три параллельные проверки:
  - `check_api_compat` — обратная совместимость API
  - `check_test_coverage` — покрытие тестами
  - `check_change_risk` — риск (auth, billing, migrations)
- Редьюсер `reviews: Annotated[list, operator.add]` — отчёты не затирают друг друга
- `aggregate_review` — structured verdict: `approve` / `changes_requested` / `block`
- Тестовые дифы:
  - [`data/code_review.txt`](../../data/code_review.txt) — рискованный (auth)
  - [`data/code_review_clean.txt`](../../data/code_review_clean.txt) — чистый (версия + тест)

## Схема графа

```mermaid
flowchart TD
    START --> classify
    classify -->|code_review| code_review
    classify -->|incident| incident
    classify -->|analytics| analytics
    code_review --> check_api_compat
    code_review --> check_test_coverage
    code_review --> check_change_risk
    check_api_compat --> aggregate_review
    check_test_coverage --> aggregate_review
    check_change_risk --> aggregate_review
    aggregate_review --> END
    incident --> END
    analytics --> END
```

## Результаты прогона

| Диф | Вердикт |
|-----|---------|
| risky (auth) | block |
| clean (версия) | approve |

Маршрутизация: code_review, incident, analytics — все OK.

## Запуск

```bash
uv run main.py
```

## Следующий шаг

Релиз 2: orchestration в ветке `analytics`.
