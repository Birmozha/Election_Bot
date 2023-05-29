import logging
import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, MediaGroup
from aiogram.types.input_file import InputFile

from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters import Text

from sqlalchemy import select, update, delete, insert
from sqlalchemy.sql import text

import smtplib
from email import encoders
from email.mime.multipart import MIMEMultipart                 
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase

from database.database import Tree, Data, Images, Poll, PollOptions, Admins, session

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)


TOKEN = os.environ.get('TOKEN')
MAIL_BOX = os.environ.get('MAIL_BOX')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
TO_MAIL_BOX = os.environ.get('TO_MAIL_BOX')

ADMIN_IDS = [387605921]

COMPLAIN_COLLECTED_TEXT = 'Благодарим Вас за Вашу гражданскую активность, Ваше обращение будет рассмотрено экспертами Общественного штаба по контролю и наблюдению за выборами Челябинской области. Идентификатор вашего обращения: '
NO_COMPLAIN_TEXT = 'Кажется, Вы не столкнулись с каким-либо нарушением. Вы можете вернуться назад'
FINAL_TEXT = 'Остались вопросы?\n\nВы можете позвонить на горячую линию Общественного штаба по контролю и наблюдению за выборами и проконсультироваться со специалистом: 8(351)737-16-57'

cat_button_text = '🔄 К категориям'
inline_cat_button = InlineKeyboardButton(text=cat_button_text, callback_data='go-cats')
reply_cat_button = KeyboardButton(text=cat_button_text)


back_button_text = '⤴️ Назад'
inline_back_button = InlineKeyboardButton(text=back_button_text, callback_data='go-back')
reply_back_button = KeyboardButton(text=back_button_text)


bot = Bot(TOKEN, parse_mode='HTML')
dp = Dispatcher(bot, storage=MemoryStorage())

# STATE GROUPS --------------------------------------------------------------

class StartStates(StatesGroup):
    start = State()

class InfoStates(StatesGroup):
    dialog = State()


class ComplainStates(StatesGroup):
    choose_category = State()
    wait_category = State()
    wait_text = State()
    wait_photo = State()
    additionals = State()
    wait_confirmation = State()
    change_text = State()
    change_photo = State()
    
class AdminStates(StatesGroup):
    admin = State()
    wait_question = State()
    wait_answer = State()
    wait_id = State()
    
class PollStates(StartStates):
    poll = State()
    
# ---------------------------------------------------------------------------

# FUNCTIONS -----------------------------------------------------------------

admin_keyborad = InlineKeyboardMarkup(row_width=1
                                      ).add(InlineKeyboardButton(text='Текущий опрос', callback_data='get-current')
                                            ).add(InlineKeyboardButton(text='Посмотреть результаты опроса', callback_data='get-results')
                                                     ).add(InlineKeyboardButton(text='Завершить текущий опрос', callback_data='finish-current')
                                                           ).add(InlineKeyboardButton(text='Создать новый опрос', callback_data='new-poll')
                                                                 ).add(InlineKeyboardButton(text='Список администраторов', callback_data='admins')
                                                                       ).add(InlineKeyboardButton(text='Добавить администратора', callback_data='insert'))
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
        buttons.append((session.scalar(select(Data.text).where(Data.id == button_id)),button_id))
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

async def set_states(data, state: FSMContext):
    if '<additionals>' in data['properties']:
        return await ComplainStates.additionals.set()
    elif '<choosecat>' in data['properties']:
        return await ComplainStates.choose_category.set()
    elif '<waittext>' in data['properties']:
        async with state.proxy() as st:
            # st['temp_complain'].append(data['text'])
            st['prefix'] = data['text'][-1]
            data['text'] = data['text'][:-1]
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

async def check_complain(state: FSMContext):
    await ComplainStates.wait_confirmation.set()
    keyboard = InlineKeyboardMarkup(
        ).add(InlineKeyboardButton(text='Отправить сообщение о нарушении', callback_data='submit')
                                          ).add(InlineKeyboardButton(text='Изменить сообщение о нарушении', callback_data='change-text')
                                                ).add(InlineKeyboardButton(text='Добавить фото (или видео)', callback_data='change-media')
                                                      ).add(InlineKeyboardButton(text='Отменить отправку сообщения о нарушении', callback_data='go-cats'))
    final_keyboard = InlineKeyboardMarkup(
        ).add(InlineKeyboardButton(text='Отправить сообщение о нарушении', callback_data='submit')
                                          ).add(InlineKeyboardButton(text='Добавить фото (или видео)', callback_data='change-media')
                                                ).add(InlineKeyboardButton(text='Отменить отправку сообщения о нарушении', callback_data='go-cats'))
    media_keyboard = InlineKeyboardMarkup(
        ).add(InlineKeyboardButton(text='Отправить сообщение о нарушении', callback_data='submit')
              ).add(InlineKeyboardButton(text='Изменить сообщение о нарушении', callback_data='change-text')
                    ).add(InlineKeyboardButton(text='Изменить фото (или видео)', callback_data='change-media')
                          ).add(InlineKeyboardButton(text='Отменить отправку сообщения о нарушении', callback_data='go-cats'))
    final_media_keyboard = InlineKeyboardMarkup(
        ).add(InlineKeyboardButton(text='Отправить сообщение о нарушении', callback_data='submit')
              ).add(InlineKeyboardButton(text='Изменить фото (или видео)', callback_data='change-media')
                    ).add(InlineKeyboardButton(text='Отменить отправку сообщения о нарушении', callback_data='go-cats'))
              
    async with state.proxy() as st:
        user_id = st['user_id']
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
    if not text:
        return await bot.send_message(chat_id=user_id, text=NO_COMPLAIN_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    complain = f'<b>Категория:</b> {category}\n\n<b>Сообщение о нарушении:</b>'
    for el in text:
        complain += el
    if photo_path:
        photo = InputFile(photo_path)
        async with state.proxy() as st:
            if st['temp_complain']:
                await bot.send_photo(chat_id=user_id, photo=photo, caption=complain, reply_markup=media_keyboard)
            else:
                await bot.send_photo(chat_id=user_id, photo=photo, caption=complain, reply_markup=final_media_keyboard)
    elif video_path:
        video = InputFile(video_path)
        if st['temp_complain']:
                await bot.send_video(chat_id=user_id, video=video, caption=complain, reply_markup=media_keyboard)
        else:
            await bot.send_video(chat_id=user_id, video=video, caption=complain, reply_markup=final_media_keyboard)
    else:
        if st['temp_complain']:
            await bot.send_message(chat_id=user_id, text=complain, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=user_id, text=complain, reply_markup=final_keyboard)
            
async def send_letter(state: FSMContext):
    async with state.proxy() as st:
        category = st['complain']['title']
        id = st['complain']['id']
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
    message['Subject'] = f'Новое сообщение о нарушении: {category} - {id}'
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

async def get_poll(callback: types.CallbackQuery, state: FSMContext):
    question = session.scalar(select(Poll.question).where(Poll.id == 1))
    options = session.scalars(select(PollOptions.option).where(PollOptions.pid == 1)).all()
    current_state = await state.get_state()
    if current_state == 'AdminStates:admin':
        return await callback.message.answer(text=question, reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(text=option, callback_data=option) for option in options]))
    else:
        return await callback.message.answer(text=question, reply_markup=InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(text=option, callback_data=option) for option in options]).add(inline_cat_button))

# ---------------------------------------------------------------------------

@dp.message_handler(commands=['start'], state=StartStates.start)
async def cmd_start(message: types.Message, state: FSMContext):
    await StartStates.start.set()
    data = find_next(None)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text, reply_markup=ReplyKeyboardRemove())
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)

@dp.message_handler(commands=['admin'], state=['*'])
async def cmd_admin(message: types.Message, state: FSMContext):
    admins = session.scalars(select(Admins.telegram_id)).all()
    if message.from_user.id not in admins:
        await message.reply(text='Вы не являетесь администратором')
    else:
        await AdminStates.admin.set()
        await message.reply(text='Вы успешно вошли в админ-панель', reply_markup=admin_keyborad)

@dp.message_handler(commands=['start'], state=['*'])
async def cmd_start(message: types.Message, state: FSMContext):
    await StartStates.start.set()
    async with state.proxy() as st:
        st['user_id'] = message.from_user.id
        st['candidates'] = {}
    data = find_next(None)
    if len(data['text']) > 1:
        for text in data['text'][:-1]:
            await message.answer(text=text, reply_markup=ReplyKeyboardRemove())
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(0.2)
        text = data['text'][-1]
    else:
        text = data['text'][0]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)

@dp.message_handler(commands=['admin'], state=['*'])
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.reply(text='Вы не являетесь администратором')
    else:
        await AdminStates.admin.set()
        await message.reply(text='Вы успешно вошли в админ-панель', reply_markup=admin_keyborad)
        

# BACK ----------------------------------------------------------------------

@dp.callback_query_handler(Text(equals='go-back'), state=['*'])
async def goBack(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    async with state.proxy() as st:
        id = st['prev']
    keyboard = find_keyboard(id)
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    try:
        await callback.message.answer(text='Вернул назад', reply_markup=keyboard.add(reply_back_button))
    except Exception:
        await callback.message.answer(text='Вернул назад', reply_markup=keyboard.add(inline_back_button))


@dp.callback_query_handler(Text(equals='go-cats'), state=['*'])
async def goCats(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state == 'PollStates:poll':
        async with state.proxy() as st:
            poll_id = st['poll-id']
        await bot.delete_message(chat_id=callback.message.chat.id, message_id=poll_id)
    await callback.answer()
    data = find_next(None)
    text = data['text'][-1]
    keyboard = find_keyboard(data['id'])
    if current_state == 'PollStates:poll':
        await callback.message.answer(text=text, reply_markup=keyboard)
    else:
        await callback.message.edit_text(text=text, reply_markup=keyboard)
    await StartStates.start.set()

@dp.message_handler(Text(equals=cat_button_text), state=['*'])
async def goCatsReply(message: types.Message, state: FSMContext):
    data = find_next(None)
    text = data['text'][-1]
    keyboard = find_keyboard(data['id'])
    await message.answer(text=text, reply_markup=keyboard)
    await StartStates.start.set()

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
        return await message.answer(text='Вы можете вернуться к категориям', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_cat_button))
    if isinstance(keyboard, InlineKeyboardMarkup):
        return await message.answer(text='Вернул назад', reply_markup=keyboard.add(inline_cat_button))
    await message.answer(text='Вернул назад', reply_markup=keyboard.add(reply_back_button))
    async with state.proxy() as st:
        st['prev'] = data['previous']
        
# ---------------------------------------------------------------------------

# INFO ----------------------------------------------------------------------

@dp.callback_query_handler(Text(startswith='candidate'), state=InfoStates.dialog)
async def callback_candidates(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        id = int((callback.data.split('-'))[1])
        async with state.proxy() as st:
            await callback.message.edit_text(text=st['candidates'][callback.message['message_id']][id], reply_markup=InlineKeyboardMarkup(row_width=3)
                                    .insert(InlineKeyboardButton(text='⬅️', callback_data=f'candidate-{id-1}'))
                                    .insert(InlineKeyboardButton(text=f" {id+1} / {len(st['candidates'][callback.message['message_id']])}", callback_data='candidate'))
                                    .insert(InlineKeyboardButton(text='➡️', callback_data=f'candidate-{id+1}')))
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
    if message.text not in session.scalars(select(Data.text)).all():
        media = MediaGroup()
        media.attach_photo(InputFile('database/bot_photos/ikb_buttons.jpg'), 'Инлайн кнопки')
        media.attach_photo(InputFile('database/bot_photos/kb_buttons.jpg'), 'Обычные кнопки')
        # photo = InputFile('database/bot_photos/ikb_buttons.jpg')
        # await bot.send_photo(chat_id=message.from_user.id, caption='Пожалуйста, используйте инлайн-кнопки', photo=photo)
        # photo = InputFile('database/bot_photos/kb_buttons.jpg')
        # return await bot.send_photo(chat_id=message.from_user.id, caption='Или используйте кнопки', photo=photo)
        await bot.send_media_group(chat_id=message.from_user.id, media=media)
        return await message.answer(text='Пожалуйста, следуйте инструкции')
    if '<candidates>' in data['properties'] :
        async with state.proxy() as st:
            message = await message.answer(text=data['candidates'][0], reply_markup=InlineKeyboardMarkup(row_width=3)
                                           .insert(InlineKeyboardButton(text='⬅️', callback_data='candidate-0'))
                                           .insert(InlineKeyboardButton(text=f" 1 / {len(data['candidates'])}", callback_data='candidate'))
                                           .insert(InlineKeyboardButton(text='➡️', callback_data='candidate-1')))
            st['candidates'][message["message_id"]] = data['candidates']
            
        keyboard = find_keyboard(data['id'])
        if isinstance(keyboard, ReplyKeyboardRemove):
            await message.answer(text='Используйте кнопки ⬅️ и ➡️ для навигации', reply_markup=keyboard)
            await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
            await asyncio.sleep(1)
            return await message.answer(text='Вы можете вернуться назад', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
        elif isinstance(keyboard, ReplyKeyboardMarkup):
            await message.answer(text='Используйте кнопки ⬅️ и ➡️ для навигации', reply_markup=keyboard.add(reply_back_button))
        elif isinstance(keyboard, InlineKeyboardMarkup):
            await message.answer(text='Используйте кнопки, прикрепленные к сообщению, для навигации', reply_markup=keyboard.add(inline_back_button))
        async with state.proxy() as st:
            st['prev'] = data['id']
        return
    elif '<links>' in data['properties'] :
        texts = []
        buttons = []
        links = []
        for el in data['text']:
            el = el.split('//link//')
            texts.append(el[0])
            try:
                buttons.append(el[1])
                links.append(el[2])
            except IndexError:
                keyboard = find_keyboard(data['id'])
                for text in texts:
                    if isinstance(keyboard, ReplyKeyboardRemove):
                        await message.answer(text=text, reply_markup=keyboard)  
                        return await message.answer(text='Вы можете вернуться назад', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
                    elif isinstance(keyboard, ReplyKeyboardMarkup):
                        await message.answer(text=text, reply_markup=keyboard.add(reply_back_button))
                    elif isinstance(keyboard, InlineKeyboardMarkup):
                        await message.answer(text=text, reply_markup=keyboard.add(inline_back_button))
                async with state.proxy() as st:
                    st['prev'] = data['id']
                return 
        for n, text in enumerate(texts):
            await asyncio.sleep(0.2)
            await message.answer(text=text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text=buttons[n], url=links[n].strip())))
        keyboard = find_keyboard(data['id'])
        keyboard = find_keyboard(data['id'])
        await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
        await asyncio.sleep(0.5)
        if isinstance(keyboard, ReplyKeyboardRemove):
            await message.answer(text='Вы можете использовать кнопки для перехода на внешний ресурс', reply_markup=keyboard)  
            return await message.answer(text='Вы можете вернуться назад', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
        elif isinstance(keyboard, ReplyKeyboardMarkup):
            await message.answer(text='Вы можете использовать кнопки для перехода на внешний ресурс', reply_markup=keyboard.add(reply_back_button))
        elif isinstance(keyboard, InlineKeyboardMarkup):
            await message.answer(text='Вы можете использовать кнопки для перехода на внешний ресурс', reply_markup=keyboard.add(inline_back_button))
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
        return await message.answer(text='Вы можете вернуться назад', reply_markup=InlineKeyboardMarkup(row_width=1).add(inline_back_button).add(inline_cat_button))
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
        id = st['complain']['id']
    data = find_next(prev)
    if not data:
        await send_letter(state)
        await StartStates.start.set()
        await callback.message.answer(text=COMPLAIN_COLLECTED_TEXT+str(id))
        return await callback.message.answer(text=FINAL_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await set_states(data, state)
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
            id = st['complain']['id']
    if message.photo or message.video:
        if message.photo:
            await message.photo[-1].download(destination_file=f'database\complain_photos/{category}_{id}.jpg')
            async with state.proxy() as st:
                st['complain']['photo_path'] = f'database\complain_photos/{category}_{id}.jpg'
                st['complain']['photo_name'] = f'{category}_{id}.jpg'
        elif message.video:
            await message.video.download(destination_file=f'database\complain_videos/{category}_{id}.mp4')
            async with state.proxy() as st:
                st['complain']['video_path'] = f'database\complain_videos/{category}_{id}.mp4'
                st['complain']['video_name'] = f'{category}_{id}.mp4'
        data = find_next(prev)
        if not data:
            await send_letter(state)
            await StartStates.start.set()
            await message.answer(text=COMPLAIN_COLLECTED_TEXT+str(id))
            return await message.answer(text=FINAL_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        await set_states(data, state)
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
        st['complain']['text'].append(f"{st['prefix']}: {message.text}")
        prev = st['prev']
    data = find_next(prev)
    if not data:
        await check_complain(state)
        return
        await send_letter(state)
        await StartStates.start.set()
        await message.answer(text=COMPLAIN_COLLECTED_TEXT)
        return await message.answer(text=FINAL_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    await set_states(data, state)
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
        async with state.proxy() as st:
            st['temp_complain'].append((text, st['prefix']))
        await message.answer(text=text, reply_markup=ReplyKeyboardRemove())
    async with state.proxy() as st:
        st['prev'] = data['id']

@dp.callback_query_handler(Text(equals='submit'), state=ComplainStates.wait_confirmation)
async def submit_complain(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    async with state.proxy() as st:
        id = st['complain']['id']
    await send_letter(state)
    await StartStates.start.set()
    await callback.message.delete()
    await callback.message.answer(text=COMPLAIN_COLLECTED_TEXT+str(id))
    return await callback.message.answer(text=FINAL_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))

@dp.callback_query_handler(Text(equals='change-text'), state=ComplainStates.wait_confirmation)
async def change_complain_text(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    async with state.proxy() as st:
        # st['temp_complain'] = st['complain']['text']
        text = st['temp_complain'].pop(0)
        st['complain']['text'] = []
    await ComplainStates.change_text.set()
    await callback.message.delete()
    await callback.message.answer(text=text[0])
    async with state.proxy() as st:
        st['prefix'] = text[1]
        
@dp.callback_query_handler(Text(equals='change-media'), state=ComplainStates.wait_confirmation)
async def change_complain_media(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await ComplainStates.change_photo.set()
    await callback.message.answer('Пришлите фотографию (или видео)')

@dp.message_handler(content_types=['any'], state=ComplainStates.change_photo)
async def change_photo(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    async with state.proxy() as st:
        id = st['complain']['id']
        category = st['complain']['title'].lower().strip().replace(' ', '_')
        try:
            photo_path = st['complain']['photo_path']
        except KeyError:
            photo_path = None
        try:
            video_path = st['complain']['video_path']
        except KeyError:
            video_path = None
        if photo_path:
            os.remove(os.path.join(os.path.dirname(__file__), photo_path))
        elif video_path:
            os.remove(os.path.join(os.path.dirname(__file__), video_path))
    if message.photo or message.video:
        if message.photo:
            await message.photo[-1].download(destination_file=f'database\complain_photos/{category}_{id}.jpg')
            async with state.proxy() as st:
                st['complain']['photo_path'] = f'database\complain_photos/{category}_{id}.jpg'
                st['complain']['photo_name'] = f'{category}_{id}.jpg'
        elif message.video:
            await message.video.download(destination_file=f'database\complain_videos/{category}_{id}.mp4')
            async with state.proxy() as st:
                st['complain']['video_path'] = f'database\complain_videos/{category}_{id}.mp4'
                st['complain']['video_name'] = f'{category}_{id}.mp4'
        await check_complain(state)
    else:
        await ComplainStates.change_photo.set()
        await message.reply(text='Пришлите, пожалуйста, фотографию', reply_markup=InlineKeyboardMarkup()
                            .add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))
    
@dp.message_handler(state=ComplainStates.change_text)
async def rewrite_complain(message: types.Message, state: FSMContext):
    if message.photo or message.video:
        return await message.reply('Пришлите, пожалуйста, текст')
    async with state.proxy() as st:
        st['complain']['text'].append(f"{st['prefix']}: {message.text}")
        try:
            text = st['temp_complain'].pop(0)
        except:
            text = None
    if not text:
        return await check_complain(state)
    await message.answer(text=text[0])
    async with state.proxy() as st:
        st['prefix'] = text[1]
    
@dp.message_handler(state=ComplainStates.additionals)
async def wait_category(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    temp = await text_to_id(message, state)
    data = find_next(temp)
    if message.text not in session.scalars(select(Data.text)).all():
        media = MediaGroup()
        media.attach_photo(InputFile('database/bot_photos/ikb_buttons.jpg'), 'Инлайн кнопки')
        media.attach_photo(InputFile('database/bot_photos/kb_buttons.jpg'), 'Обычные кнопки')
        # photo = InputFile('database/bot_photos/ikb_buttons.jpg')
        # await bot.send_photo(chat_id=message.from_user.id, caption='Пожалуйста, используйте инлайн-кнопки', photo=photo)
        # photo = InputFile('database/bot_photos/kb_buttons.jpg')
        # return await bot.send_photo(chat_id=message.from_user.id, caption='Или используйте кнопки', photo=photo)
        await bot.send_media_group(chat_id=message.from_user.id, media=media)
        return await message.answer(text='Пожалуйста, следуйте инструкции')
    if not data:
        await check_complain(state)
        return
    await set_states(data, state)
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
        await check_complain(state)
        return
        await send_letter(state)
        await StartStates.start.set()
        await message.answer(text=text, reply_markup=keyboard)
        await message.answer(text=COMPLAIN_COLLECTED_TEXT)
        return await message.answer(text=FINAL_TEXT, reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        
    elif '<waitphoto>' in data['properties']:
        await message.answer(text=text, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Пропустить добавление фото', callback_data='skip-photo')))
    else:
        async with state.proxy() as st:
            st['temp_complain'].append((text, st['prefix']))
        await message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['prev'] = data['id']

@dp.message_handler(state=ComplainStates.choose_category)
async def choose_category(message: types.Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.from_user.id, action='typing')
    temp = await text_to_id(message, state)
    data = find_next(temp)
    if message.text not in session.scalars(select(Data.text)).all():
        media = MediaGroup()
        media.attach_photo(InputFile('database/bot_photos/ikb_buttons.jpg'), 'Инлайн кнопки')
        media.attach_photo(InputFile('database/bot_photos/kb_buttons.jpg'), 'Обычные кнопки')
        # photo = InputFile('database/bot_photos/ikb_buttons.jpg')
        # await bot.send_photo(chat_id=message.from_user.id, caption='Пожалуйста, используйте инлайн-кнопки', photo=photo)
        # photo = InputFile('database/bot_photos/kb_buttons.jpg')
        # return await bot.send_photo(chat_id=message.from_user.id, caption='Или используйте кнопки', photo=photo)
        await bot.send_media_group(chat_id=message.from_user.id, media=media)
        return await message.answer(text='Пожалуйста, следуйте инструкции')
    await set_states(data, state)
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
            await StartStates.start.set()
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
    if '<waittext>' in data['properties']:
        async with state.proxy() as st:
            st['temp_complain'].append((text, st['prefix']))
    await message.answer(text=text, reply_markup=keyboard)
    async with state.proxy() as st:
        st['complain']['title'] = message.text
        st['prev'] = data['id']
        data = find_next(st['prev'])
    if not data:
        await StartStates.start.set()
        return await message.answer(text='Вернуться обратно?', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))

# ---------------------------------------------------------------------------

# POLL ----------------------------------------------------------------------

@dp.callback_query_handler(state=PollStates.poll)
async def collect_poll_answer(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(text='Спасибо за прохождение опроса!', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
    id = callback.from_user.id
    session.execute(update(Poll).where(Poll.id == 1).values(passed=(Poll.passed + f' {str(id)}')))
    session.execute(update(PollOptions).where(PollOptions.option == callback.data).values(count=PollOptions.count + 1))
    session.commit()
    await StartStates.start.set()
    
# ---------------------------------------------------------------------------

# ADMIN ---------------------------------------------------------------------

@dp.callback_query_handler(Text(startswith='delete'), state=AdminStates.admin)
async def delete_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    id = callback.data.split('-')[1]
    session.execute(delete(Admins).where(Admins.telegram_id == id))
    session.commit()
    await callback.message.delete()

@dp.message_handler(state=AdminStates.wait_id)
async def wait_admin(message: types.Message, state: FSMContext):
    id = int(message.text.strip())
    session.execute(insert(Admins).values(telegram_id = id))
    session.commit()
    await message.reply(text='Администратор добавлен', reply_markup=admin_keyborad)
    await AdminStates.admin.set()

@dp.callback_query_handler(Text(startswith='insert'), state=AdminStates.admin)
async def insert_admin(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(text='Введите ID пользователя в Telegram')
    await AdminStates.wait_id.set()

@dp.callback_query_handler(state=AdminStates.admin)
async def admin_handler(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == 'get-current':
        await callback.answer()
        try:
            await get_poll(callback, state)
        except Exception:
            await callback.message.answer('Действующего опроса нет')
    elif callback.data == 'get-results':
        await callback.answer()
        results = session.scalars(select(PollOptions).where(PollOptions.pid == 1)).all()
        if not results:
            return await callback.message.answer('Действующего опроса нет')
        text_results = 'Результаты:\n\n'
        for result in results:
            text_results += str('<b>' + result.option.split('🔸 ')[1] + '</b>') + ':    ' + str(result.count) + '\n'
        await callback.message.answer(text_results)
    elif callback.data == 'finish-current':
        await callback.answer()
        results = session.scalars(select(PollOptions).where(PollOptions.pid == 1)).all()
        if not results:
            return await callback.message.answer('Действующего опроса нет')
        text_results = 'Результаты:\n\n'
        for result in results:
            text_results += str('<b>' + result.option.split('🔸 ')[1] + '</b>') + ':    ' + str(result.count) + '\n'
        await callback.message.answer(text_results)
        session.query(Poll).delete()
        session.commit()
    elif callback.data == 'new-poll':
        await callback.answer()
        session.query(Poll).delete()
        session.commit()
        await callback.message.answer(text='Введите вопрос')
        await AdminStates.wait_question.set()
    elif callback.data == 'admins':
        await callback.answer()
        admins = session.scalars(select(Admins.telegram_id)).all()
        for id in admins:
            await callback.message.answer(text=f'<a href="tg://user?id={id}">{id}</a>', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Удалить', callback_data=f'delete-{id}')))
    else:
        await callback.answer('Вы находитесь в админ-панели. Используйте команду /start')
        

@dp.message_handler(state=AdminStates.wait_question)
async def admin_handler(message: types.Message, state: FSMContext):
    question = Poll(question = message.text)
    session.add(question)
    session.commit()
    await message.reply('Вопрос записан')
    await message.answer('Введите вариант ответа')
    await AdminStates.wait_answer.set()

@dp.message_handler(state=AdminStates.wait_answer)
async def admin_handler(message: types.Message, state: FSMContext):
    option = PollOptions(pid = 1, option = '🔸 ' + message.text)
    session.add(option)
    session.commit()
    if len(session.scalars(select(PollOptions).where(PollOptions.pid == 1)).all()) < 2:
        await message.reply('Вопрос записан')
        await message.answer('Введите вариант ответа')
    else:
        await message.reply('Вопрос записан')
        await message.answer(text='Введите вариант ответа', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(text='Создать опрос', callback_data='create-poll')))
    
@dp.callback_query_handler(Text(equals='create-poll'), state=AdminStates.wait_answer)
async def create_poll(callback: types.CallbackQuery, state: FSMContext):
    await AdminStates.admin.set()
    await callback.answer()
    await callback.message.answer('Опрос создан!', reply_markup=admin_keyborad)
        
# ---------------------------------------------------------------------------

@dp.callback_query_handler(state=StartStates.start)
async def define_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if 'candidate' in callback.data:
        return await callback_candidates(callback, state)
    if int(callback.data) == 17:
        await InfoStates.dialog.set()
    elif int(callback.data) == 186:
        try:
            passed = session.scalar(select(Poll.passed).where(Poll.id == 1)).split( )
        except AttributeError:
            return await callback.message.text(text='Действующего опроса нет', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        if str(callback.from_user.id) in passed:
            return await callback.message.edit_text(text='Вы уже проходили опрос', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
        else:
            try:
                await PollStates.poll.set()
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=callback.message.message_id)
                poll = await get_poll(callback, state)
                async with state.proxy() as st:
                    st['poll-id'] = poll['message_id']
                return
            except Exception:
                try:
                    await callback.message.edit_text(text='Действующего опроса нет', reply_markup=InlineKeyboardMarkup().add(inline_cat_button))
                finally:
                    return
    elif int(callback.data) == 2:
        async with state.proxy() as st:
            st['complain'] = {}
            st['complain']['text'] = []
            st['complain']['id'] = f'{callback.message.chat.id}-{callback.message.message_id}'
            st['temp_complain'] = []
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
    logging.basicConfig(level=logging.ERROR, filename="py_log.log",filemode="w")
    session.execute(text("PRAGMA foreign_keys=ON"))
    executor.start_polling(dp, skip_updates=True)