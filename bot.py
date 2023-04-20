from collections import namedtuple
import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text
from sqlalchemy import select


from database.database import Tree, Data, Images, session

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


TOKEN = os.environ.get('TOKEN')
MAIL_BOX = os.environ.get('MAIL_BOX')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')


cat_button_text = '<< К категориям'
inline_cat_button = InlineKeyboardButton(text=cat_button_text, callback_data='go-cats')
reply_cat_button = KeyboardButton(text=cat_button_text)


back_button_text = '<< Назад'
inline_back_button = InlineKeyboardButton(text=back_button_text, callback_data='go-back')
reply_back_button = KeyboardButton(text=back_button_text)


bot = Bot(TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# STATE GROUPS --------------------------------------------------------------
class InfoStates(StatesGroup):
    dialog = State()
    candidates = State()

class ComplainStates(StatesGroup):
    choose_categry = State()
    wait_text = State()
    wait_photo = State()
    additionals = State()


# ---------------------------------------------------------------------------


# FUNCTIONS -----------------------------------------------------------------

def find_next(id=None) -> dict:
    previous = id
    id = session.scalar(select(Tree.qid).where(Tree.pid == id))
    candidates_property = session.scalar(select(Tree.properties).where(Tree.qid == id))
    text = session.scalar(select(Data.text).where(
        Data.id == id)).split('//delimeter//')
    candidates = {}
    if '<candidates>' in candidates_property:
        for n, el in enumerate(text):
            candidates[n] = el
    else:
        candidates_property = False
    photo = session.scalar(select(Images.image).where(Images.id == id))
    next = session.scalars(select(Tree.qid).where(Tree.pid == id)).all()
    
    final = {'id': id, 'text': text, 'next': next, 'photo': photo, 'previous': previous, 'candidates_property': candidates_property, 'candidates': candidates}
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


# INFO ----------------------------------------------------------------------

@dp.callback_query_handler(Text(equals='go-back'), state=InfoStates.dialog)
async def goBack(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    async with state.proxy() as st:
        id = st['prev']
    keyboard = find_keyboard(id)
    await callback.message.answer(text='Вернул назад', reply_markup=keyboard.add(reply_back_button))


@dp.callback_query_handler(Text(equals='go-cats'), state=InfoStates.dialog)
async def goCats(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = find_next()
    text = data['text'][-1]
    keyboard = find_keyboard(data['id'])
    await callback.message.edit_text(text=text, reply_markup=keyboard)

@dp.message_handler(Text(equals=back_button_text), state=InfoStates.dialog)
async def goBackReply(message: types.Message, state: FSMContext):
    await bot.send_chat_action(message.from_user.id, action='typing')
    async with state.proxy() as st:
        id = st['prev']
    id = session.scalar(select(Tree.pid).where(Tree.qid == id))
    id = session.scalar(select(Tree.pid).where(Tree.qid == id))
    data = find_next(id)
    text = data['text']
    try:
        keyboard = find_keyboard(id)
    except:
        return await message.answer(text='Вы получили ответы на все вопросы', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_cat_button))
    if isinstance(keyboard, InlineKeyboardMarkup):
        return await message.answer(text='Вернул назад', reply_markup=keyboard.add(inline_cat_button))
    await message.answer(text='Вернул назад', reply_markup=keyboard.add(reply_back_button))
    async with state.proxy() as st:
        st['prev'] = data['previous']

@dp.callback_query_handler(Text(startswith='candidate'), state=InfoStates.dialog)
async def callback_candidates(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        id = int((callback.data.split('-'))[1])
        async with state.proxy() as st:
            await callback.message.edit_text(text=st['candidates'][callback.message['message_id']][id], reply_markup=InlineKeyboardMarkup(row_width=3)
                                    .insert(InlineKeyboardButton(text='<<', callback_data=f'candidate-{id-1}'))
                                    .insert(InlineKeyboardButton(text=f" {id+1} / {len(st['candidates'][callback.message['message_id']])}", callback_data='candidate'))
                                    .insert(InlineKeyboardButton(text='>>', callback_data=f'candidate-{id+1}')))
    except Exception:
        pass

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
    if data['candidates_property']:
        async with state.proxy() as st:
            message = await message.answer(text=data['candidates'][0], reply_markup=InlineKeyboardMarkup(row_width=3)
                                           .insert(InlineKeyboardButton(text='<<', callback_data='candidate-0'))
                                           .insert(InlineKeyboardButton(text=f" 1 / {len(data['candidates'])}", callback_data='candidate'))
                                           .insert(InlineKeyboardButton(text='>>', callback_data='candidate-1')))
            st['candidates'][message["message_id"]] = data['candidates']
            
        keyboard = find_keyboard(data['id'])
        if isinstance(keyboard, ReplyKeyboardRemove):
            await message.answer(text='Используйте инлайн-кнопки для навигации', reply_markup=keyboard)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(1)
            return await message.answer(text='Вы получили ответы на все вопросы', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
        elif isinstance(keyboard, ReplyKeyboardMarkup):
            await message.answer(text='Используйте инлайн-кнопки для навигации', reply_markup=keyboard.add(reply_back_button))
        elif isinstance(keyboard, InlineKeyboardMarkup):
            await message.answer(text='Используйте инлайн-кнопки для навигации', reply_markup=keyboard.add(inline_back_button))
        async with state.proxy() as st:
            st['prev'] = data['id']
        return
        
    if data['photo']:
        photo = InputFile(data['photo'])
        if len(data['text']) > 2:
            text = data['text'][0]
            data['text'] = data['text'][1:]
            keyboard = find_keyboard(data['id'])
            await bot.send_photo(chat_id=message.from_user.id, photo=photo, caption=text, reply_markup=keyboard)
        elif len(data['text']) == 1:
            text = data['text'][0]
            keyboard = find_keyboard(data['id'])
            if isinstance(keyboard, ReplyKeyboardRemove):
                await bot.send_photo(chat_id=message.from_user.id, photo=photo, caption=text, reply_markup=keyboard)
                await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
                await asyncio.sleep(1)
                return await message.answer(text='Вы получили ответы на все вопросы', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
            return await bot.send_photo(chat_id=message.from_user.id, photo=photo, caption=text, reply_markup=keyboard.add(reply_back_button))
        else:
            await bot.send_photo(chat_id=message.from_user.id, photo=photo)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    if isinstance(keyboard, ReplyKeyboardRemove):
        await message.answer(text=text, reply_markup=keyboard)
        await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
        await asyncio.sleep(1)
        return await message.answer(text='Вы получили ответы на все вопросы', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
    elif isinstance(keyboard, ReplyKeyboardMarkup):
        await message.answer(text=text, reply_markup=keyboard.add(reply_back_button))
    elif isinstance(keyboard, InlineKeyboardMarkup):
        await message.answer(text=text, reply_markup=keyboard.add(inline_back_button))
    async with state.proxy() as st:
        st['prev'] = data['id']

# ---------------------------------------------------------------------------

@dp.callback_query_handler()
async def define_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if int(callback.data) == 2:
        async with state.proxy() as st:
            st['candidates'] = {}
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
    await callback.message.edit_text(text=text, reply_markup=keyboard.add(inline_cat_button))
    async with state.proxy() as st:
        st['prev'] = data['id']

if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as exception:
        print(exception)
