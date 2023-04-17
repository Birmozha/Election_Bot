from sqlalchemy import select
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from database.database import Tree, Data, session

def find_followong_texts(texts, table, id):
    next = session.scalar(select(Tree.qid).where(Tree.pid==id).where(Tree.properties.like('<text>%')))
    if next:
        texts.append((session.scalar(select(Data.text).where(Data.id==next)), next))
        find_followong_texts(texts, table, next)
    else:
        return texts

class ComplainStates(StatesGroup):
    choose_categry = State()
    additionals = State()


async def define_category(callback: types.CallbackQuery, state: FSMContext):
    if int(callback.data) == 2:
        await callback.answer()
        await callback.message.answer(text='Скоро появится...')
    elif int(callback.data) == 17:
        await callback.answer()
        async with state.proxy() as st:
            st['prev'] = callback.data
        next = session.scalar(
            select(Tree.qid).where(Tree.pid == callback.data))
        next_properties = session.scalar(
            select(Tree.properties).where(Tree.qid == next)).split(', ')
        if next_properties[1] == '<choosecat>':
            await ComplainStates.choose_categry.set()
        text = session.scalar(select(Data.text).where(Data.id == next))
        button_ids = session.scalars(
            select(Tree.qid).where(Tree.pid == next)).all()
        buttons = []
        for button_id in button_ids:
            buttons.append(
                (session.scalar(select(Data.text).where(Data.id == button_id)), button_id))
        kb = InlineKeyboardMarkup(row_width=1).add(
            *[InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in buttons])
        await callback.message.edit_text(text=text, reply_markup=kb)


async def wait_for_category(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    next = session.scalar(select(Tree.qid).where(Tree.pid == callback.data))
    next_properties = session.scalar(
        select(Tree.properties).where(Tree.qid == next)).split(', ')
    if next_properties[1] == '<additionals>':
        await ComplainStates.additionals.set()
        texts = []
        find_followong_texts(texts, Tree, next)
        if len(texts) > 1:
            for text in texts[:-1]:
                await callback.message.answer(text=text[0])
        print(texts)
        # text = texts[-1][0]
        # button_ids = session.scalars(select(Tree.qid).where(Tree.pid==texts[-1][1])).all()
        # buttons = []
        # for button_id in button_ids:
        #     buttons.append((session.scalar(select(Data.text).where(Data.id==button_id)), button_id))
        # kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(*[KeyboardButton(text=button) for button, callback_data in buttons])
        # await callback.message.answer(text=text, reply_markup=kb)

