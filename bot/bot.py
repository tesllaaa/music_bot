import os
import re
import telebot
import logging
from telebot import types
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

from logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

from db import (
    init_db, add_track, get_current_track, pop_track,
    add_vote, count_votes, clear_votes, get_queue_list, get_top_stats,
    clear_queue_list
)

from ai import chat_once

load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("В .env файле нет TOKEN")

bot = telebot.TeleBot(TOKEN)
init_db()

SKIP_VOTES_REQUIRED = 3


def make_main_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎵 Сейчас", "📜 Очередь")
    kb.row("⏭ Скип", "🔥 Топ")
    kb.row("🤖 AI Вайб", "/help", "/hide")
    return kb


def make_confirm_kb(action_code: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("Да", callback_data=f"confirm:{action_code}:yes"),
        types.InlineKeyboardButton("Нет", callback_data=f"confirm:{action_code}:no")
    )
    return kb


def extract_vk_url(text: str) -> str | None:
    match = re.search(r'https?://vk\.(com|ru)/\S+', text)
    return match.group(0) if match else None


def get_vk_track_title(url: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        r.encoding = r.apparent_encoding

        soup = BeautifulSoup(r.text, 'html.parser')

        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].replace(" | VK", "").replace("ВКонтакте", "").strip()
            if title and title not in ["VK", "ВКонтакте", "Вход", "Добро пожаловать"]:
                return title

        if soup.title and soup.title.string:
            title = soup.title.string.replace(" | VK", "").replace("ВКонтакте", "").strip()
            if title and title not in ["VK", "Вход", "Добро пожаловать", "Аудиозаписи"]:
                return title

    except Exception as e:
        logger.error(f"Ошибка парсинга ссылки {url}: {e}")
        logger.exception(f"VK ERROR: {url}")

    logger.warning(f"VK PARSE FAIL: {url}")
    return None


def process_vk_link(message, url: str):
    msg = bot.reply_to(message, "🔎 Ищу название...")
    title = get_vk_track_title(url) or "Без названия"
    add_track(message.from_user.id, url, title)
    bot.edit_message_text(f"✅ Добавлено: {title}", message.chat.id, msg.message_id)
    logger.info(f"Трек добавлен: {title} от user {message.from_user.id}")


@bot.message_handler(commands=['vibe'])
def start_ai_recommendation(message):
    logger.info(f"AI запрос от {message.from_user.id}")
    msg = bot.reply_to(message, "🎹 Опиши атмосферу вечеринки (например: 'Рок 2007', 'Грустный дэнс', 'Для качалки'):")
    bot.register_next_step_handler(msg, ask_ai_dj)


@bot.message_handler(func=lambda m: m.text == "🤖 AI Вайб")
def btn_ai_recommendation(message):
    start_ai_recommendation(message)


def ask_ai_dj(message):
    user_text = message.text
    if not user_text:
        bot.reply_to(message, "Ты ничего не написал :(")
        return

    bot.send_chat_action(message.chat.id, 'typing')

    messages = [
        {
            "role": "system",
            "content": "Ты крутой музыкальный DJ. Твоя задача — посоветовать 5 лучших треков под описание пользователя. Формат: 'Исполнитель - Название'. Без лишней болтовни."
        },
        {
            "role": "user",
            "content": f"Подбери музыку: {user_text}"
        }
    ]

    try:
        ai_answer = chat_once(messages)
        bot.reply_to(message, f"🎧 **Рекомендация ИИ:**\n\n{ai_answer}\n\n_Копируй и кидай ссылки!_", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка в main.py при вызове AI: {e}")
        bot.reply_to(message, "Мозг бота сейчас перегружен или недоступен 🤕")


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "🎉 **Party Music Bot**\nКидай ссылки VK или используй меню.",
        reply_markup=make_main_kb(),
        parse_mode="Markdown"
    )


@bot.message_handler(commands=["help"])
def help_cmd(message):
    help_text = """
📖 **Команды бота:**

/add <ссылка> — добавить трек
/now — что играет сейчас
/queue — показать очередь
/skip — голосовать за пропуск
/top — топ треков
/vibe — AI подбор музыки
/clear — очистить очередь
/hide — скрыть меню

💡 Можно просто кидать ссылки VK!
"""
    bot.reply_to(message, help_text, reply_markup=make_main_kb(), parse_mode="Markdown")


@bot.message_handler(commands=['hide'])
def hide(message):
    bot.reply_to(message, "Меню скрыто. /start чтобы вернуть.", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(commands=["add"])
def add_cmd(message):
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        bot.reply_to(message, "❌ Пришли ссылку после команды\nПример:\n/add https://vk.com/audio...")
        return

    url = extract_vk_url(parts[1])

    if not url:
        bot.reply_to(message, "❌ Не могу найти VK ссылку в сообщении")
        return

    process_vk_link(message, url)


@bot.message_handler(func=lambda m: m.text and ("vk.com" in m.text or "vk.ru" in m.text) and not m.text.startswith("/"))
def handle_link(message):
    url = extract_vk_url(message.text)

    if not url:
        bot.reply_to(message, "❌ Не могу найти VK ссылку в сообщении")
        return

    process_vk_link(message, url)


@bot.message_handler(func=lambda m: m.text == "🎵 Сейчас")
def menu_now(message):
    now_playing(message)


@bot.message_handler(func=lambda m: m.text == "📜 Очередь")
def menu_queue(message):
    show_queue(message)


@bot.message_handler(func=lambda m: m.text == "⏭ Скип")
def menu_skip(message):
    skip_track(message)


@bot.message_handler(func=lambda m: m.text == "🔥 Топ")
def menu_top(message):
    top_tracks(message)


@bot.message_handler(commands=["now"])
def now_playing(message):
    track = get_current_track()
    if track:
        bot.reply_to(message, f"🎶 Играет:\n{track[2]}\n🔗 {track[1]}")
    else:
        bot.reply_to(message, "🔇 Тишина... Добавь трек!")


@bot.message_handler(commands=["queue"])
def show_queue(message):
    rows = get_queue_list()
    if not rows:
        bot.reply_to(message, "📭 Очередь пуста")
        return
    text = "\n".join([f"{i+1}. {r[0]}" for i, r in enumerate(rows)])
    bot.reply_to(message, f"📜 **Очередь:**\n{text}", parse_mode="Markdown")


@bot.message_handler(commands=["top"])
def top_tracks(message):
    rows = get_top_stats()
    if not rows:
        bot.reply_to(message, "📊 Статистика пуста")
        return
    text = "\n".join([f"🎵 {r[0]} — {r[1]} раз" for r in rows])
    bot.reply_to(message, f"🔥 **Топ треков:**\n{text}", parse_mode="Markdown")


@bot.message_handler(commands=["skip"])
def skip_track(message):
    track = get_current_track()
    if not track:
        bot.reply_to(message, "🤷 Нечего скипать — очередь пуста.")
        return

    if add_vote(track[0], message.from_user.id):
        votes = count_votes(track[0])
        if votes >= SKIP_VOTES_REQUIRED:
            pop_track()
            clear_votes(track[0])
            bot.reply_to(message, "⏭ Трек пропущен!")
            logger.info(f"Трек пропущен: {track[2]}")
        else:
            bot.reply_to(message, f"✅ Голос принят ({votes}/{SKIP_VOTES_REQUIRED})")
    else:
        bot.reply_to(message, "⚠️ Ты уже голосовал за пропуск этого трека.")


@bot.message_handler(commands=['clear'])
def clear_cmd(message):
    bot.send_message(
        message.chat.id,
        "⚠️ Вы уверены, что хотите очистить всю очередь?",
        reply_markup=make_confirm_kb("clear_queue")
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm:"))
def callback_confirm(c):
    try:
        _, action, choice = c.data.split(":")

        if action == "clear_queue":
            if choice == "yes":
                clear_queue_list()
                bot.answer_callback_query(c.id, "Очередь очищена!")
                bot.edit_message_text(
                    "🗑 **Очередь была полностью очищена.**",
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id,
                    parse_mode="Markdown"
                )
                logger.info(f"Очередь очищена пользователем {c.from_user.id}")
            else:
                bot.answer_callback_query(c.id, "Отмена")
                bot.edit_message_text(
                    "❌ Очистка отменена.",
                    chat_id=c.message.chat.id,
                    message_id=c.message.message_id
                )
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        bot.answer_callback_query(c.id, "Произошла ошибка")


if __name__ == "__main__":
    logger.info("🚀 Bot started")
    bot.infinity_polling(skip_pending=True)