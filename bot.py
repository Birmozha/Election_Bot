from collections import namedtuple
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text
from sqlalchemy import select

from database.database import Tree, Data, session

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


TOKEN = os.environ.get('TOKEN')
MAIL_BOX = os.environ.get('MAIL_BOX')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


bot = Bot(TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# STATE GROUPS --------------------------------------------------------------
class InfoStates(StatesGroup):
    dialog = State()

class ComplainStates(StatesGroup):
    choose_categry = State()
    additionals = State()


# ---------------------------------------------------------------------------


# FUNCTIONS -----------------------------------------------------------------

def find_next(id=None) -> dict:
    id = session.scalar(select(Tree.qid).where(Tree.pid == id))
    text = session.scalar(select(Data.text).where(
        Data.id == id)).split('<delimetr>')
    next = session.scalars(select(Tree.qid).where(Tree.pid == id)).all()
    final = {'id': id, 'text': text, 'next': next}
    return final

def find_keyboard(id) -> ReplyKeyboardMarkup | InlineKeyboardMarkup:
    keyboard_type = session.scalar(
        select(Tree.properties).where(Tree.qid == id)).split(', ')[1]
    button_ids = session.scalars(select(Tree.qid).where(
        Tree.pid == id).where(Tree.properties.like('<button%'))).fetchall()
    buttons = []
    for button_id in button_ids:
        buttons.append(
            (
                session.scalar(select(Data.text).where(Data.id == button_id)),
                button_id
            )
        )
    if not buttons:
        keyboard = ReplyKeyboardRemove()
        return keyboard
    if keyboard_type == '<ikb>':
        keyboard = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in buttons])
    elif keyboard_type == '<kb>':
        keyboard = ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True).add(*[KeyboardButton(text=text) for text, callback_data in buttons])
    return keyboard

# ---------------------------------------------------------------------------


@dp.message_handler(commands=['start'], state=['*'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    data = find_next()
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)


@dp.callback_query_handler()
async def define_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if int(callback.data) == 2:
        await InfoStates.dialog.set()
    elif int(callback.data) == 17:
        await ComplainStates.choose_categry.set()
    await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
    data = find_next(int(callback.data))
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await callback.message.answer(text=text)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await callback.message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['prev'] = data['id']


@dp.callback_query_handler(state=InfoStates.dialog)
async def callback_dialog(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
    data = find_next(int(callback.data))
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await callback.message.answer(text=text)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await callback.message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['prev'] = data['id']



@dp.message_handler(state=InfoStates.dialog)
async def dailog(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    async with state.proxy() as st:
        id = st['prev']
    children = session.scalars(select(Tree.qid).where(Tree.pid == id)).all()
    for id in children:
        temp = session.scalar(select(Data.id).where(Data.text == message.text).where(Data.id == id))
        if temp:
            break
    data = find_next(temp)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['prev'] = data['id']


if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as exception:
        print(exception)
