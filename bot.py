import os
import json
import requests
from datetime import datetime
import calendar
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ---------------- Переменные окружения ----------------
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
YANDEX_TOKEN = os.getenv('YANDEX_TOKEN')
YANDEX_DIR = os.getenv('YANDEX_DIR')

if not BOT_TOKEN or not YANDEX_TOKEN or not YANDEX_DIR:
    raise ValueError('Не найдены токены или папка YANDEX_DIR в .env')

# ---------------- Работа с Яндекс.Диском ----------------
def upload_to_yandex(filename, data):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={YANDEX_DIR}/{filename}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    if 'href' not in r:
        print('Ошибка получения ссылки для загрузки на Яндекс.Диск:', r)
        return False
    upload_url = r['href']
    requests.put(upload_url, data=json.dumps(data).encode('utf-8'))
    return True

def download_from_yandex(filename):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={YANDEX_DIR}/{filename}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    if 'href' not in r:
        raise FileNotFoundError(f'Файл {filename} не найден на Яндекс.Диске')
    download_url = r['href']
    resp = requests.get(download_url)
    return json.loads(resp.content)

# ---------------- Шаблон бюджета ----------------
DEFAULT_EXPENSES = [
    {'emoji': '🎁', 'name': 'Подарок', 'amount': 0},
    {'emoji': '🏠', 'name': 'Ипотека', 'amount': 0},
    {'emoji': '💳', 'name': 'Кредиты', 'amount': 0},
    {'emoji': '📌', 'name': 'Долг Гоше', 'amount': 0},
    {'emoji': '🏢', 'name': 'Коммуналка', 'amount': 0},
    {'emoji': '🚌', 'name': 'Проездной', 'amount': 0},
    {'emoji': '🧪', 'name': 'Анализы ВНЖ', 'amount': 0},
    {'emoji': '🛁', 'name': 'Акрил ванны', 'amount': 0},
    {'emoji': '🚗', 'name': 'Проезд', 'amount': 0},
    {'emoji': '🍴', 'name': 'Еда в офисе', 'amount': 0},
    {'emoji': '💄', 'name': 'Бьюти', 'amount': 0},
    {'emoji': '📝', 'name': 'Англ. язык', 'amount': 0},
    {'emoji': '💅', 'name': 'Косметика', 'amount': 0}
]

DEFAULT_INCOME = [
    {'name': 'Зарплата', 'amount': 0},
    {'name': 'Аванс', 'amount': 0},
    {'name': 'Дополнительные доходы', 'amount': 0}
]

def new_month_template(month: str, year: int):
    return {
        'month': month,
        'year': year,
        'expenses': [exp.copy() for exp in DEFAULT_EXPENSES],
        'income': [inc.copy() for inc in DEFAULT_INCOME],
        'last_message_id': None,
        'awaiting_emoji': None
    }

# ---------------- Генерация текста шаблона ----------------
def generate_template_text(data):
    text = f"💸 Расходы/Доходы {data['month']} {data['year']}\n\n"
    for idx, exp in enumerate(data['expenses'], 1):
        text += f"{idx}. {exp['emoji']} {exp['name']} — {exp['amount']} ₽\n"
    text += "\n💰 Доходы\n"
    for inc in data['income']:
        text += f"{inc['name']} — {inc['amount']} ₽\n"
    return text

# ---------------- Telegram ----------------
def start(update: Update, context: CallbackContext):
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)
        upload_to_yandex(filename, data)

    text = generate_template_text(data)
    update.message.reply_text('Привет! Бот бюджета запущен.')
    update.message.reply_text(text)

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)

    # Ожидание смайлика
    if data.get('awaiting_emoji'):
        emoji = text[0]
        new_exp = data['awaiting_emoji']
        data['expenses'].append({
            'name': new_exp['name'],
            'amount': new_exp['amount'],
            'emoji': emoji
        })
        data['awaiting_emoji'] = None
        update.message.reply_text(f'Расход "{new_exp["name"]}" добавлен с смайликом {emoji}')
        upload_to_yandex(filename, data)
        return

    parts = text.split()
    ltext = text.lower()

    if ltext.startswith('новый месяц'):
        month_index = now.month
        year_new = now.year
        next_month_index = 1 if month_index == 12 else month_index + 1
        if month_index == 12:
            year_new += 1
        next_month_name = calendar.month_name[next_month_index]
        data = new_month_template(next_month_name, year_new)
        filename = f'budget_{next_month_name}_{year_new}.json'
        upload_to_yandex(filename, data)
        update.message.reply_text(f'Создан новый месяц: {next_month_name} {year_new}')
        update.message.reply_text(generate_template_text(data))
        return

    elif ltext.startswith('доход'):
        try:
            amount = int(parts[1])
            name = ' '.join(parts[2:]) or 'Доход'
        except:
            update.message.reply_text('Ошибка формата. Используй: доход <сумма> <название>')
            return
        for inc in data['income']:
            if inc['name'].lower() == name.lower():
                inc['amount'] += amount
                break
        else:
            data['income'].append({'name': name, 'amount': amount})
        upload_to_yandex(filename, data)
        update.message.reply_text(f'Добавлен новый доход "{name}"')

    elif ltext.startswith('расход'):
        try:
            amount = int(parts[1])
            name = parts[2]
        except:
            update.message.reply_text('Ошибка формата. Используй: расход <сумма> <название>')
            return
        for exp in data['expenses']:
            if exp['name'].lower() == name.lower():
                exp['amount'] += amount
                upload_to_yandex(filename, data)
                update.message.reply_text(f'Расход "{name}" обновлён на {amount} ₽')
                return
        data['awaiting_emoji'] = {'name': name, 'amount': amount}
        update.message.reply_text(f'Введите смайлик для нового расхода "{name}"')
        upload_to_yandex(filename, data)
        return

    elif ltext.startswith('удали'):
        if len(parts) < 2:
            update.message.reply_text('Укажи название расхода для удаления: удали <название>')
            return
        name = parts[1]
        before_len = len(data['expenses'])
       
