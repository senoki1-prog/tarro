#!/usr/bin/env python3
"""
AI Tarot Bot — клон @tarot_astrobot
Полноценный Telegram-бот с AI-интерпретациями раскладов Таро

Требования:
pip install aiogram openai python-dotenv

Запуск:
1. Создай бота у @BotFather и получи токен
2. Зарегистрируйся на https://groq.com → получи бесплатный API ключ
3. Создай файл .env с:
   BOT_TOKEN=твой_токен
   GROQ_API_KEY=твой_groq_ключ
4. python tarot_astrobot_clone.py

Деплой: Railway, Render.com или любой VPS
"""

import asyncio
import logging
import os
import random
from datetime import datetime
from typing import List, Tuple

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand
)
from openai import AsyncOpenAI
from dotenv import load_dotenv

# ==================== НАСТРОЙКИ ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")

# Инициализация LLM (Groq — быстро и бесплатно)
llm_client = None
if GROQ_API_KEY:
    llm_client = AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=GROQ_API_KEY
    )
else:
    logging.warning("⚠️ GROQ_API_KEY не найден — интерпретации будут упрощёнными")

# ==================== ДАННЫЕ КОЛОДЫ ====================
def get_tarot_deck() -> List[str]:
    """Полная колода Таро на русском (78 карт)"""
    majors = [
        "Шут", "Маг", "Верховная Жрица", "Императрица", "Император",
        "Иерофант", "Влюблённые", "Колесница", "Сила", "Отшельник",
        "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть",
        "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце",
        "Суд", "Мир"
    ]
    
    suits = ["Жезлы", "Кубки", "Мечи", "Пентакли"]
    minors = []
    for suit in suits:
        for i in range(1, 11):
            if i == 1:
                minors.append(f"Туз {suit}")
            else:
                minors.append(f"{i} {suit}")
        minors.extend([
            f"Паж {suit}", f"Рыцарь {suit}", 
            f"Королева {suit}", f"Король {suit}"
        ])
    
    return majors + minors


def draw_cards(count: int) -> List[Tuple[str, str]]:
    """Тянет указанное количество карт со случайной ориентацией"""
    deck = get_tarot_deck()
    random.shuffle(deck)
    drawn = deck[:count]
    orientations = [
        random.choice(["Прямая", "Перевёрнутая"]) 
        for _ in range(count)
    ]
    return list(zip(drawn, orientations))


def format_cards(cards: List[Tuple[str, str]]) -> str:
    """Красиво форматирует выпавшие карты"""
    lines = []
    for i, (card, orient) in enumerate(cards, 1):
        emoji = "🃏" if orient == "Прямая" else "🔄"
        lines.append(f"{emoji} **{i}. {card}** ({orient})")
    return "\n".join(lines)


# ==================== FSM (состояния) ====================
class TarotStates(StatesGroup):
    choosing_spread = State()
    waiting_question = State()


# ==================== РОУТЕР ====================
router = Router()


# ==================== КОМАНДЫ ====================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    welcome_text = (
        "🃏 **Добро пожаловать в АстроТаро AI!**\n\n"
        "Я — ваш персональный AI-таролог.\n"
        "Задавайте вопросы — я сделаю расклад и дам глубокую интерпретацию.\n\n"
        "Выберите тип расклада ниже 👇"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🃏 1 карта (Совет / Энергия)", callback_data="spread:1"),
        ],
        [
            InlineKeyboardButton(text="🃏🃏🃏 3 карты (Прошлое — Настоящее — Будущее)", callback_data="spread:3"),
        ],
        [
            InlineKeyboardButton(text="✨ 5 карт (Детальный расклад)", callback_data="spread:5"),
        ],
        [
            InlineKeyboardButton(text="❓ Задать свой вопрос (свободный)", callback_data="spread:custom"),
        ],
        [
            InlineKeyboardButton(text="📖 Как пользоваться", callback_data="help"),
        ]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📖 **Как пользоваться ботом**\n\n"
        "1. Выберите тип расклада\n"
        "2. Напишите свой вопрос (чем конкретнее — тем лучше)\n"
        "3. Получите карты + AI-интерпретацию\n\n"
        "**Рекомендации:**\n"
        "• Задавайте конкретные вопросы («Что меня ждёт в отношениях с X?»)\n"
        "• Не задавайте вопросы типа «да/нет» — Таро любит развёрнутые ответы\n"
        "• Можно делать несколько раскладов в день\n\n"
        "Бот использует мощную нейросеть для интерпретаций."
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()


# ==================== ВЫБОР РАСКЛАДА ====================
SPREADS = {
    "1": {"name": "Одна карта", "count": 1, "description": "Совет или текущая энергия"},
    "3": {"name": "Три карты", "count": 3, "description": "Прошлое — Настоящее — Будущее"},
    "5": {"name": "Пять карт", "count": 5, "description": "Детальный анализ ситуации"},
    "custom": {"name": "Свободный вопрос", "count": 3, "description": "Любой вопрос — 3 карты"},
}


@router.callback_query(F.data.startswith("spread:"))
async def choose_spread(callback: CallbackQuery, state: FSMContext):
    spread_key = callback.data.split(":")[1]
    spread = SPREADS.get(spread_key)
    
    if not spread:
        await callback.answer("Неизвестный расклад")
        return
    
    await state.update_data(spread_key=spread_key, spread_name=spread["name"], card_count=spread["count"])
    await state.set_state(TarotStates.waiting_question)
    
    text = (
        f"✨ **Выбран расклад:** {spread['name']}\n"
        f"_{spread['description']}_\n\n"
        "Напишите свой вопрос одним сообщением.\n"
        "Например:\n"
        "• «Что меня ждёт в карьере в ближайшие 3 месяца?»\n"
        "• «Как развиваются мои отношения с партнёром?»\n"
        "• «Какой урок мне нужно извлечь из текущей ситуации?»"
    )
    
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


# ==================== ОБРАБОТКА ВОПРОСА И ГЕНЕРАЦИЯ ====================
@router.message(TarotStates.waiting_question)
async def process_question(message: Message, state: FSMContext):
    question = message.text.strip()
    
    if len(question) < 5:
        await message.answer("Пожалуйста, напишите более развёрнутый вопрос (минимум 5 символов).")
        return
    
    data = await state.get_data()
    spread_name = data.get("spread_name", "Расклад")
    card_count = data.get("card_count", 3)
    
    # Рисуем карты
    cards = draw_cards(card_count)
    cards_formatted = format_cards(cards)
    
    # Показываем карты сразу
    cards_msg = (
        f"🃏 **Ваш расклад: {spread_name}**\n\n"
        f"**Вопрос:** _{question}_\n\n"
        f"**Выпавшие карты:**\n{cards_formatted}\n\n"
        "⏳ Генерирую глубокую интерпретацию с помощью AI..."
    )
    
    status_msg = await message.answer(cards_msg, parse_mode=ParseMode.MARKDOWN)
    
    # Генерируем интерпретацию
    interpretation = await generate_ai_interpretation(
        question=question,
        cards=cards,
        spread_name=spread_name
    )
    
    # Финальный ответ
    final_text = (
        f"🃏 **Ваш расклад: {spread_name}**\n\n"
        f"**Вопрос:** _{question}_\n\n"
        f"**Выпавшие карты:**\n{cards_formatted}\n\n"
        f"**Интерпретация:**\n{interpretation}\n\n"
        "✨ Хотите сделать ещё один расклад? Нажмите /start"
    )
    
    await status_msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    await state.clear()


async def generate_ai_interpretation(
    question: str, 
    cards: List[Tuple[str, str]], 
    spread_name: str
) -> str:
    """Генерирует интерпретацию через Groq LLM"""
    
    if not llm_client:
        # Fallback без LLM
        return (
            "К сожалению, AI-интерпретация временно недоступна.\n"
            "Но карты выпали не случайно. Почувствуйте, что они говорят именно вам.\n\n"
            "Общий совет: прислушайтесь к своей интуиции."
        )
    
    cards_str = "\n".join([
        f"{i+1}. {card} — {orient}" 
        for i, (card, orient) in enumerate(cards)
    ])
    
    prompt = f"""Ты — профессиональный таролог с 25-летним опытом, empathetic и честный.

Пользователь задал вопрос: "{question}"

Это расклад "{spread_name}".

Выпали карты:
{cards_str}

Напиши подробную, структурированную, тёплую и профессиональную интерпретацию на русском языке.

Структура ответа:
1. **Общий смысл расклада** (2-3 предложения)
2. **Разбор по позициям** (что показывает каждая карта в контексте вопроса)
3. **Возможные вызовы и скрытые возможности**
4. **Совет / рекомендация** (конкретная и полезная)
5. **Итоговый посыл** (коротко и вдохновляюще)

Правила:
- Не обещай 100% точное будущее
- Говори об энергиях, вероятностях и уроках
- Будь empathetic, но честным
- Избегай шаблонных фраз вроде "всё будет хорошо"
- Длина: 250-450 слов"""

    try:
        response = await llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # Отличная модель на Groq (быстрая и умная)
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=1200,
        )
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        logging.error(f"LLM error: {e}")
        return (
            "Произошла ошибка при генерации интерпретации.\n"
            "Карты выпали, и их энергия уже работает. "
            "Попробуйте переформулировать вопрос и сделать новый расклад."
        )


# ==================== ЗАПУСК ====================
async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не задан в .env")
        return
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    # Устанавливаем команды меню
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать новый расклад"),
        BotCommand(command="help", description="Как пользоваться ботом"),
    ])
    
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен.")