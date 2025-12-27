import os
import requests
import logging
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

# Настраиваем логирование для этого модуля
logger = logging.getLogger(__name__)

# Загружаем переменные окружения (на случай если main еще не загрузил)
load_dotenv()

OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

@dataclass
class OpenRouterError(Exception):
    status: int
    msg: str
    def __str__(self) -> str:
        return f"[{self.status}] {self.msg}"

def _friendly(status: int) -> str:
    return {
        400: "Неверный формат запроса.",
        401: "Ключ OpenRouter отклонён (проверь .env).",
        403: "Нет прав доступа к модели.",
        429: "Превышены лимиты бесплатной модели.",
        500: "Внутренняя ошибка OpenRouter.",
        502: "Проблема с соединением OpenRouter.",
        503: "OpenRouter сейчас недоступен.",
    }.get(status, "Сервис недоступен.")

def chat_once(messages: List[Dict], *,
              model: str = "mistralai/devstral-2512:free",
              temperature: float = 0.7,
              max_tokens: int = 500,
              timeout_s: int = 30) -> str:

    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY не найден")
        raise OpenRouterError(401, "Отсутствует API ключ.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/party_bot",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        r = requests.post(OPENROUTER_API, json=payload, headers=headers, timeout=timeout_s)

        if r.status_code // 100 != 2:
            raise OpenRouterError(r.status_code, _friendly(r.status_code))

        data = r.json()
        # Возвращаем только текст ответа
        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        raise OpenRouterError(408, "Таймаут запроса к ИИ.")
    except Exception as e:
        logger.error(f"AI Module Error: {e}")
        raise e