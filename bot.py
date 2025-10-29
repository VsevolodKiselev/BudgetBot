import os
import json
import requests
import calendar
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ---------- Загружаем переменные из .env ----------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_TOKEN = os.getenv("YANDEX_TOKEN")
YANDEX_DIR = os.getenv("YANDEX_DIR")

# ---------- Работа с Яндекс.Диском ----------
def upload_to_yandex(filename, data):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/upload?path={YANDEX_DIR}/{filename}&overwrite=true'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    upload_url = r['href']
    requests.put(upload_url, data=json.dumps(data, ensure_ascii=False).encode('utf-8'))

def download_from_yandex(filename):
    url = f'https://cloud-api.yandex.net/v1/disk/resources/download?path={YANDEX_DIR}/{filename}'
    headers = {'Authorization': f'OAuth {YANDEX_TOKEN}'}
    r = requests.get(url, headers=headers).json()
    if 'href' not in r:
        raise FileNotFoundError
    download_url = r['href']
    resp = requests.get(download_url)
    return json.loads(resp.content)

# ---------- Шаблон нового месяца ----------
def new_month_template(month: str, year: int):
    return {
        'month': month,
        'year': year,
        'expenses': [],
        'income': [],
        'last_message_id': None,
        'awaiting_emoji': None
    }

# ---------- Генерация текста бюджета ----------
def generate_template_text(data):
    text = f"💸 Расходы/Доходы {data['month']} {data['year']}\n\n"
    if data['expenses']:
        for idx, exp in enumerate(data['expenses'], 1):
            text += f"{idx}. {exp['emoji']} {exp['name']} — {exp['amount']} ₽\n"
    else:
        text += "Расходов пока нет\n"
    text += "\n💰 Доходы\n"
    if data['income']:
        for idx, inc in enumerate(data['income'], 1):
            text += f"{idx}. {inc['name']} — {inc['amount']} ₽\n"
    else:
        text += "Доходов пока нет\n"
    return text

# ---------- Команда /start ----------
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Привет! Бот бюджета запущен.\nВведи 'новый месяц', чтобы создать шаблон.")

# ---------- Основная обработка сообщений ----------
def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    chat_id = update.message.chat_id
    now = datetime.now()
    month_name = now.strftime('%B')
    year = now.year
    filename = f'budget_{month_name}_{year}.json'

    # Пытаемся загрузить текущие данные
    try:
        data = download_from_yandex(filename)
    except:
        data = new_month_template(month_name, year)

    # ---------- Если бот ждёт смайлик ----------
    if data.get('awaiting_emoji'):
        emoji = text.strip()[0]
        new_exp = data['awaiting_emoji']
        data['expenses'].append({
            'name': new_exp['name'],
            'amount': new_exp['amount'],
            'emoji': emoji,
            'account': new_exp['account']
        })
        data['awaiting_emoji'] = None
        update.message.reply_text(f'✅ Расход "{new_exp["name"]}" добавлен с смайликом {emoji}')

    else:
        ltext = text.lower()

        # ---------- Новый месяц ----------
        if ltext.startswith('новый месяц'):
            month_index = now.month
            year_new = now.year
            next_month_index = 1 if month_index == 12 else month_index + 1
            if month_index == 12:
                year_new += 1
            month_name = calendar.month_name[next_month_index]
            data = new_month_template(month_name, year_new)
            filename = f'budget_{month_name}_{year_new}.json'
            update.message.reply_text(f'Создан новый месяц: {month_name} {year_new}')

        # ---------- Добавление расхода ----------
        elif ltext.startswith('расход'):
            parts = text.split()
            try:
                amount = int(parts[1])
                name = parts[2]
                account = ' '.join(parts[3:]) if len(parts) > 3 else ''
            except:
                update.message.reply_text('❌ Ошибка формата. Используй: расход <сумма> <название> [аванс/зарплата]')
                return
            # Проверяем, есть ли такой расход
            for exp in data['expenses']:
                if exp['name'] == name:
                    exp['amount'] += amount
                    update.message.reply_text(f'Обновлён расход "{name}" (+{amount} ₽)')
                    break
            else:
                # Новый расход — ждём смайлик
                data['awaiting_emoji'] = {'name': name, 'amount': amount, 'account': account}
                update.message.reply_text(f'Введите смайлик для нового расхода "{name}"')
                upload_to_yandex(filename, data)
                return

        # ---------- Добавление дохода ----------
        elif ltext.startswith('доход'):
            parts = text.split()
            try:
                amount = int(parts[1])
                name = ' '.join(parts[2:])
            except:
                update.message.reply_text('❌ Ошибка формата. Используй: доход <сумма> <название>')
                return
            for inc in data['income']:
                if inc['name'] == name:
                    inc['amount'] += amount
                    update.message.reply_text(f'Обновлён доход "{name}" (+{amount} ₽)')
                    break
            else:
                data['income'].append({'name': name, 'amount': amount})
                update.message.reply_text(f'Добавлен новый доход "{name}"')

        # ---------- Отчёт ----------
        elif ltext == 'отчёт':
            text_out = generate_template_text(data)
            update.message.reply_text(text_out)
            return

        # ---------- Удаление расхода ----------
        elif ltext.startswith('удали'):
            parts = text.split()
            if len(parts) < 2:
                update.message.reply_text('❌ Укажи название: удали <название>')
                return
            name = parts[1]
            before = len(data['expenses'])
            data['expenses'] = [x for x in data['expenses'] if x['name'] != name]
            if len(data['expenses']) < before:
                update.message.reply_text(f'Удалён расход "{name}"')
            else:
                update.message.reply_text(f'Расход "{name}" не найден')

    # ---------- Отправляем обновлённый шаблон ----------
    text_template = generate_template_text(data)
    if data.get('last_message_id'):
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=data['last_message_id'])
        except:
            pass
    msg = update.message.reply_text(text_template)
    data['last_message_id'] = msg.message_id
    upload_to_yandex(filename, data)

# ---------- Запуск ----------
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
