from sqlalchemy import select
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from database.database import Tree, Data, session

def find_followong_texts(texts, table, id):
    next = session.scalar(select(Tree.qid).where(Tree.pid==id).where(Tree.properties.like('<text>%')))
    if next:
        texts.append((session.scalar(select(Data.text).where(Data.id==next)), next))
        find_followong_texts(texts, table, next)
    else:
        return texts


async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    id = session.scalar(select(Tree.qid).where(Tree.pid==None))
    text = session.scalar(select(Data.text).where(Data.id==id))
    next = session.scalars(select(Tree.qid).where(Tree.pid==id)).all()
    next_properties = session.scalar(select(Tree.properties).where(Tree.qid==next[0]))
    if '<text>' in next_properties:
        await message.answer(text=text)
        texts = []
        find_followong_texts(texts, Tree, next[0])
        if len(texts) > 1:
            for text in texts:
                await message.answer(text=text[0])
        text = texts[-1][0]
    button_ids = session.scalars(select(Tree.qid).where(Tree.pid==texts[-1][1])).all()
    buttons = []
    for button_id in button_ids:
        buttons.append((session.scalar(select(Data.text).where(Data.id==button_id)), button_id))
    kb = InlineKeyboardMarkup(row_width=1).add(*[InlineKeyboardButton(text=text, callback_data=callback_data) for text, callback_data in buttons])
    await message.answer(text=text, reply_markup=kb)
