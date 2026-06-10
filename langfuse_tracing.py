import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from load_dotenv import load_dotenv

load_dotenv()

_handler = None


# Подготавливает переменные окружения Langfuse перед инициализацией SDK
def _configure_langfuse_env() -> None:
    base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
    if base_url:
        os.environ.setdefault("LANGFUSE_BASE_URL", base_url)
        os.environ.setdefault("LANGFUSE_HOST", base_url)
    if base_url and ("localhost" in base_url or "127.0.0.1" in base_url):
        no_proxy = os.environ.get("NO_PROXY", "")
        for host in ("localhost", "127.0.0.1"):
            if host not in no_proxy:
                no_proxy = f"{no_proxy},{host}" if no_proxy else host
        os.environ["NO_PROXY"] = no_proxy


_configure_langfuse_env()


# Проверяет, включена ли отправка трейсов в Langfuse
def is_tracing_enabled() -> bool:
    flag = os.getenv("LANGFUSE_ENABLED")
    if flag is not None:
        return flag.lower() == "true"
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


# Возвращает singleton CallbackHandler для LangChain/LangGraph
def get_callback_handler():
    global _handler
    if not is_tracing_enabled():
        return None
    if _handler is None:
        from langfuse.langchain import CallbackHandler

        _handler = CallbackHandler()
    return _handler


# Собирает config для graph.invoke с метаданными трейса
def build_invoke_config(run_name: str, input_file: str) -> dict:
    session_id = f"dispatch-{run_name}-{uuid.uuid4().hex[:8]}"
    trace_name = f"task-dispatcher/{run_name}"
    metadata = {
        "langfuse_trace_name": trace_name,
        "langfuse_session_id": session_id,
        "langfuse_tags": ["task-dispatcher", run_name],
        "input_file": input_file,
        "app": "langchain2",
    }
    config: dict = {
        "run_name": trace_name,
        "metadata": metadata,
    }
    handler = get_callback_handler()
    if handler:
        config["callbacks"] = [handler]
    return config


# Контекст с propagate_attributes для ранней установки атрибутов трейса
@contextmanager
def trace_context(run_name: str, input_file: str):
    if not is_tracing_enabled():
        yield
        return
    from langfuse import propagate_attributes

    session_id = f"dispatch-{run_name}"
    trace_name = f"task-dispatcher/{run_name}"
    with propagate_attributes(
        trace_name=trace_name,
        session_id=session_id,
        tags=["task-dispatcher", run_name],
        metadata={"input_file": input_file, "app": "langchain2"},
    ):
        yield


# Отправляет буферизованные трейсы и завершает клиент
def flush_traces() -> None:
    if not is_tracing_enabled():
        return
    from langfuse import get_client

    client = get_client()
    client.flush()
    client.shutdown()
