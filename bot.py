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

import smtplib
from email import encoders
from email.mime.multipart import MIMEMultipart                 
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase

from database.database import Tree, Data, Images, Links, session

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


TOKEN = os.environ.get('TOKEN')
MAIL_BOX = os.environ.get('MAIL_BOX')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
TO_MAIL_BOX = os.environ.get('TO_MAIL_BOX')

COMPLAIN_COLLECTED_TEXT = 'Благодарим Вас за Вашу гражданскую активность, Ваше обращение будет рассмотрено экспертами Общественного штаба по контролю и наблюдению за выборами Челябинской области'


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
    choose_category = State()
    wait_category = State()
    wait_text = State()
    wait_photo = State()
    additionals = State()

# ---------------------------------------------------------------------------

# FUNCTIONS -----------------------------------------------------------------

def find_next(id) -> dict:
    previous = id
    id = session.scalar(select(Tree.qid).where(Tree.pid == id))
    properties = session.scalar(select(Tree.properties).where(Tree.qid == id))
    if not id:
        return None
    text = session.scalar(select(Data.text).where(
        Data.id == id)).split('//delimeter//')
    candidates = {}
    if '<candidates>' in properties:
        for n, el in enumerate(text):
            candidates[n] = el
    photo = session.scalar(select(Images.image).where(Images.id == id))
    next = session.scalars(select(Tree.qid).where(Tree.pid == id)).all()
    
    final = {'id': id, 'text': text, 'next': next, 'photo': photo, 'previous': previous, 'properties': properties, 'candidates': candidates}
    return final

def find_keyboard(id) -> ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove:
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
    elif keyboard_type == '<link>':
        keyboard = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(text=text.split('//delimeter//')[0], callback_data='link', url=text.split('//delimeter//')[1].strip()) for text, callback_data in buttons])
    else:
        keyboard = ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True).add(*[KeyboardButton(text=text) for text, callback_data in buttons])
    return keyboard

async def set_states(data):
    if '<additionals>' in data['properties']:
        return await ComplainStates.additionals.set()
    elif '<choosecat>' in data['properties']:
        return await ComplainStates.choose_category.set()
    elif '<waittext>' in data['properties']:
        return await ComplainStates.wait_text.set()
    elif '<waitphoto>' in data['properties']:
        return await ComplainStates.wait_photo.set()

async def text_to_id(message: types.Message, state: FSMContext):
    async with state.proxy() as st:
        id = st['prev']
    children = session.scalars(select(Tree.qid).where(Tree.pid == id)).all()
    for id in children:
        temp = session.scalar(select(Data.id).where(Data.text == message.text).where(Data.id == id))
        if temp:
            return temp
        
async def send_letter(state: FSMContext):
    async with state.proxy() as st:
        category = st['complain']['title']
        try:
            photo_path = st['complain']['photo_path']
            photo_name = st['complain']['photo_name']
        except KeyError:
            photo_path = None
        try:
            video_path = st['complain']['video_path']
            video_name = st['complain']['video_name']
        except KeyError:
            video_path = None
        text = st['complain']['text']
    message = MIMEMultipart()
    message['From'] = MAIL_BOX
    message['To'] = TO_MAIL_BOX
    message['Subject'] = f'Новая жалоба: {category}'
    body = ''
    for el in text:
        body += f'\t{el}\n'
    message.attach(MIMEText(body, 'plain'))
    if photo_path:
        with open(photo_path, 'rb') as fp:
            image = MIMEImage(fp.read())
            image.add_header('Content-Disposition', 'attachment', filename=f'{photo_name}')
            message.attach(image)
    elif video_path:
        with open(video_path, 'rb') as fp:
            video = MIMEBase('application', "octet-stream")
            video.set_payload(fp.read())
            encoders.encode_base64(video)
            video.add_header('Content-Disposition', 'attachment', filename=f'{video_name}')
            message.attach(video)
        
    smtpObj = smtplib.SMTP('smtp.mail.ru')
    smtpObj.starttls()
    smtpObj.login(MAIL_BOX, MAIL_PASSWORD)
    smtpObj.send_message(message)
    smtpObj.quit()
    if photo_path:
        os.remove(os.path.join(os.path.dirname(__file__), photo_path))
    elif video_path:
        os.remove(os.path.join(os.path.dirname(__file__), video_path))
# ---------------------------------------------------------------------------

@dp.message_handler(commands=['start'], state=['*'])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    data = find_next(None)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)


# INFO ----------------------------------------------------------------------

@dp.callback_query_handler(Text(equals='go-back'), state=['*'])
async def goBack(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    async with state.proxy() as st:
        id = st['prev']
    keyboard = find_keyboard(id)
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await callback.message.answer(text='Вернул назад', reply_markup=keyboard.add(reply_back_button))


@dp.callback_query_handler(Text(equals='go-cats'), state=['*'])
async def goCats(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = find_next(None)
    text = data['text'][-1]
    keyboard = find_keyboard(data['id'])
    await callback.message.edit_text(text=text, reply_markup=keyboard)
    await state.finish()

@dp.message_handler(Text(equals=cat_button_text), state=['*'])
async def goCatsReply(message: types.Message, state: FSMContext):
    data = find_next(None)
    text = data['text'][-1]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)
    await state.finish()

@dp.message_handler(Text(equals=back_button_text), state=['*'])
async def goBackReply(message: types.Message, state: FSMContext):
    await bot.send_chat_action(message.from_user.id, action='typing')
    async with state.proxy() as st:
        try:
            id = st['prev']
        except Exception:
            return
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
            await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
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
    if '<candidates>' in data['properties'] :
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
                async with state.proxy() as st:
                    st['prev'] = data['id']
                return await message.answer(text='Вы получили ответы на все вопросы', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
            async with state.proxy() as st:
                    st['prev'] = data['id']
            return await bot.send_photo(chat_id=message.from_user.id, photo=photo, caption=text, reply_markup=keyboard.add(reply_back_button))
        else:
            await bot.send_photo(chat_id=message.from_user.id, photo=photo)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
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


# COMPLAINS -----------------------------------------------------------------

@dp.callback_query_handler(state=ComplainStates.wait_photo)
async def skip_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
    async with state.proxy() as st:
        prev = st['prev']
    data = find_next(prev)
    if not data:
        await send_letter(state)
        await state.finish()
        return await callback.message.answer(text=COMPLAIN_COLLECTED_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await set_states(data)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await callback.message.answer(text=text)
            await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    if '<additionals>' in data['properties']:
        keyboard = find_keyboard(data['id'])
        await callback.message.answer(text=text, reply_markup=keyboard)
    else:    
        await callback.message.answer(text=text)
    async with state.proxy() as st:
        st['prev'] = data['id']

@dp.message_handler(content_types=['any'], state=ComplainStates.wait_photo)
async def wait_text(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    async with state.proxy() as st:
            prev = st['prev']
            category = st['complain']['title'].lower().strip().replace(' ', '_')
    if message.photo or message.video:
        if message.photo:
            await message.photo[-1].download(destination_file=f'database\complain_photos/{category}_{message.message_id}.jpg')
            async with state.proxy() as st:
                st['complain']['photo_path'] = f'database\complain_photos/{category}_{message.message_id}.jpg'
                st['complain']['photo_name'] = f'{category}_{message.message_id}.jpg'
        elif message.video:
            await message.video.download(destination_file=f'database\complain_videos/{category}_{message.message_id}.mp4')
            async with state.proxy() as st:
                st['complain']['video_path'] = f'database\complain_videos/{category}_{message.message_id}.mp4'
                st['complain']['video_name'] = f'{category}_{message.message_id}.mp4'
        data = find_next(prev)
        if not data:
            await send_letter(state)
            await state.finish()
            return await message.answer(text=COMPLAIN_COLLECTED_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        await set_states(data)
        if len(data['text']) > 1:
            for text in data['text'][:-1]:
                await message.answer(text=text)
                await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
                await asyncio.sleep(0.2)
            text = data['text'][-1]
        else:
            text = data['text'][0]
        if '<additionals>' in data['properties']:
            keyboard = find_keyboard(data['id'])
            await message.answer(text=text, reply_markup=keyboard)
        elif '<waitphoto>' in data['properties']:
            await message.answer(text=text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))
        else:
            await message.answer(text=text)
        async with state.proxy() as st:
            st['prev'] = data['id']
    else:
        await ComplainStates.wait_photo.set()
        await message.reply(text='Пришлите, пожалуйста, фотографию', reply_markup=InlineKeyboardMarkup()
                            .add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))

@dp.message_handler(content_types=['any'], state=ComplainStates.wait_text)
async def wait_text(message: types.Message, state: FSMContext):
    if message.photo or message.video:
        return await message.reply('Пришлите, пожалуйста, текст')
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    async with state.proxy() as st:
        st['complain']['text'].append(message.text)
        prev = st['prev']
    data = find_next(prev)
    if not data:
        await send_letter(state)
        await state.finish()
        return await message.answer(text=COMPLAIN_COLLECTED_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await set_states(data)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    if '<additionals>' in data['properties']:
        keyboard = find_keyboard(data['id'])
        await message.answer(text=text, reply_markup=keyboard)
    elif '<waitphoto>' in data['properties']:
        await message.answer(text=text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))
    else:
        await message.answer(text=text, reply_markup=ReplyKeyboardRemove())
    async with state.proxy() as st:
        st['prev'] = data['id']


@dp.message_handler(state=ComplainStates.additionals)
async def wait_category(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    temp = await text_to_id(message, state)
    data = find_next(temp)
    if not data:
        await send_letter(state)
        await state.finish()
        return await message.answer(text=COMPLAIN_COLLECTED_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await set_states(data)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    if '<additionals>' in data['properties'] and isinstance(keyboard, ReplyKeyboardRemove):
        await send_letter(state)
        await state.finish()
        await message.answer(text=text, reply_markup=keyboard)
        await message.answer(text=COMPLAIN_COLLECTED_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    elif '<waitphoto>' in data['properties']:
        await message.answer(text=text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))
    else:
        await message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['prev'] = data['id']

@dp.message_handler(state=ComplainStates.choose_category)
async def choose_category(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    temp = await text_to_id(message, state)
    data = find_next(temp)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    if '<link>' in data['properties']:
        await message.answer(text=text, reply_markup=keyboard)
        data = find_next(data['next'][0])
        if not data:
            await state.finish()
            return await message.answer(text='Вернуться обратно?', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        if len(data['text']) > 1:
            for text in data['text'][:-1]:
                await message.answer(text=text)
                await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
                await asyncio.sleep(0.2)
            text = data['text'][-1]
        else:
            text = data['text'][0]
        keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)
    await set_states(data)
    async with state.proxy() as st:
        st['complain']['title'] = message.text
        st['prev'] = data['id']
        data = find_next(st['prev'])
    if not data:
        await state.finish()
        return await message.answer(text='Вернуться обратно?', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))

# ---------------------------------------------------------------------------

@dp.callback_query_handler()
async def define_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if int(callback.data) == 2:
        async with state.proxy() as st:
            st['candidates'] = {}
        await InfoStates.dialog.set()
    elif int(callback.data) == 17:
        async with state.proxy() as st:
            st['complain'] = {}
            st['complain']['text'] = []
        await ComplainStates.choose_category.set()
        
    await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
    data = find_next(int(callback.data))
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await callback.message.edit_text(text=text)
            await bot.send_chat_action(chat_id=callback.message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    if isinstance(keyboard, InlineKeyboardMarkup):
        await callback.message.edit_text(text=text, reply_markup=keyboard.add(inline_cat_button))
    elif isinstance(keyboard, ReplyKeyboardMarkup):
        await callback.message.answer(text=text, reply_markup=keyboard.add(reply_cat_button))
    async with state.proxy() as st:
        st['prev'] = data['id']


if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as exception:
        print(exception)
