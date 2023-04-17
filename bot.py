from handlers.commands import cmd_start
from handlers.complain import ComplainStates, define_category, wait_for_category
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


TOKEN = os.environ.get('TOKEN')
MAIL_BOX = os.environ.get('MAIL_BOX')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


bot = Bot(TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

dp.register_message_handler(cmd_start, commands=['start'], state=['*'])
dp.register_callback_query_handler(wait_for_category, state=ComplainStates.choose_categry)
dp.register_callback_query_handler(define_category)

def start_bot(dp):
    executor.start_polling(dp, skip_updates=True)
