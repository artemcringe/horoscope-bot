import asyncio
import sys
from datetime import datetime

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import CallbackQuery
from asyncpg import UniqueViolationError
from loguru import logger

from db.db_gino import db
from db.schemas.user import User
from keyboards.client_kb import *
from loader import bot
from states.states import FSMClientRegistration
from utils.funcs import get_background_photo, validate_birthdate, user_exists, prepare_data

MESSAGE_ID = None

logger.add(sys.stderr, format="<white>{time:HH:mm:ss}</white>"
                              " | <green>{level: <8}</green>"
                              " | <cyan>{line}</cyan>"
                              " - <white>{message}</white>")
logger.add('logs/file_{time}.log')


async def start_command(message: types.Message):
    if await user_exists(message.from_user.id):
        await message.answer('Здравствуйте.\n\nСпасибо, что вернулись в нашего бота. Вы получите гороскоп по '
                             'расписанию.\n\nЕсли хотите получить его сейчас нажмите на соответствующую кнопку в меню.')
        asyncio.create_task(schedule(message, 50))
        logger.info(f'Пользователь {message.from_user.id} уже зарегистрирован..')
    else:
        global MESSAGE_ID
        await message.delete()
        await FSMClientRegistration.client_name.set()
        await get_background_photo(message, 'media/backgrounds/background-name.jpg')
        MESSAGE_ID = message.message_id + 1
        logger.info(f'Пользователь {message.from_user.id} начал регистрацию.')


async def send(message: types.Message | CallbackQuery, state: FSMContext):
    user_id = message.from_user.id
    if await user_exists(user_id):
        await prepare_data(user_id)
        logger.info(f'Пользователь {user_id} запросил гороскоп с помощью /send.')
    else:
        await message.answer('Вы пока не прошли регистрацию, введите /start')


async def change(message: types.Message | CallbackQuery, state: FSMContext):
    await FSMClientRegistration.client_change_info.set()
    logger.info(f'Пользователь {message.from_user.id} хочет изменить данные')
    if type(message) == types.Message:
        await bot.send_message(message.chat.id,
                               text='Выберите какие данные необходимо изменить 🥺',
                               reply_markup=change_inline_kb)
    else:
        await bot.send_message(message.message.chat.id,
                               text='Выберите какие данные необходимо изменить 🥺',
                               reply_markup=change_inline_kb)


async def get_my_info(message: types.Message | CallbackQuery, state: FSMContext):
    data = User.select('name', 'gender', 'birth_date', 'birth_place', 'birth_time', 'receive_day_period').where(
        User.user_id == message.from_user.id)
    data = await db.all(data)
    await message.answer(text=f'Имя: {data[0][0]}\n\n'
                              f'Пол: {data[0][1]}\n\n'
                              f'Дата рождения: {data[0][2]}\n\n'
                              f'Место рождения: {data[0][3]}\n\n'
                              f'Время рождения: {data[0][4] if not None else "Не знаете"}\n\n'
                              f'Получать рассылку: {data[0][5]}\n\n'
                              f'Если какие-либо данные неправильные, то выполните команду /change')


async def name_info(message: types.Message, state: FSMContext):
    await message.delete()
    await bot.delete_message(message.chat.id, MESSAGE_ID)
    async with state.proxy() as data:
        data['name'] = message.text
        data['user_id'] = message.from_user.id
        data['message_id'] = message.message_id + 1
    await FSMClientRegistration.next()
    await get_background_photo(message, 'media/backgrounds/background-gender.jpg', reply_markup=client_gender_inline_kb)


async def gender_info(callback_query: CallbackQuery, state: FSMContext):
    gender = callback_query.data
    if gender == 'gender_male':
        gender = 'Мужчина'
    else:
        gender = 'Женщина'
    async with state.proxy() as data:
        data['gender'] = gender
    await FSMClientRegistration.next()

    await get_background_photo(callback_query, 'media/backgrounds/birthdate-img.jpg',
                               caption='Пожалуйста, введите дату своего рождения в формате 15.11.2001')


async def check_birthdate(message: types.Message, state: FSMContext):
    await message.delete()
    if validate_birthdate(message.text):
        async with state.proxy() as data:
            data['birth_date'] = message.text
        await FSMClientRegistration.next()
        await get_background_photo(message, 'media/backgrounds/birthplace-img.jpg',
                                   caption='Пожалуйста, введите место своего рождения')
    else:
        async with state.proxy() as data:
            await get_background_photo(message, 'media/backgrounds/birthdate-img.jpg',
                                       caption='Пожалуйста, введите дату своего рождения в формате 15.11.2001')


async def birthplace_info(message: types.Message, state: FSMContext):
    await message.delete()
    async with state.proxy() as data:
        data['birth_place'] = message.text
        await FSMClientRegistration.client_birth_time.set()
        await bot.send_message(message.chat.id, text='Вы знаете свое время рождения?', reply_markup=dont_know_inline_kb)


async def birth_time(callback_query: CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if callback_query.data == 'know_no':
            await FSMClientRegistration.client_send_date.set()
            data['birth_time'] = None
            await get_background_photo(callback_query, 'media/backgrounds/horoscope-time.jpg',
                                       caption='Утром - гороскоп на сегодня\nВечером - гороскоп на завтра',
                                       reply_markup=client_date_inline_kb)
        else:
            await FSMClientRegistration.client_birth_time_set.set()
            await get_background_photo(callback_query, 'media/backgrounds/birthtime-img.jpg',
                                       caption='Пожалуйста, введите время своего рождения в таком формате 12:00')


async def set_birth_time(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['message_id'] = message.message_id + 1
        data['birth_time'] = message.text
        await FSMClientRegistration.next()
        await get_background_photo(message, 'media/backgrounds/horoscope-time.jpg',
                                   caption='Утром - гороскоп на сегодня\nВечером - гороскоп на завтра',
                                   reply_markup=client_date_inline_kb)


async def prepare_datas(callback_query: CallbackQuery, state: FSMContext):
    part_of_the_day = callback_query.data
    if part_of_the_day == 'date_morning':
        part_of_the_day = "Утром"
    else:
        part_of_the_day = "Вечером"
    async with state.proxy() as data:
        data['part_of_the_day'] = part_of_the_day
        await FSMClientRegistration.next()
        await bot.send_message(callback_query.message.chat.id,
                               text=f'Проверьте, пожалуйста, данные:\nИмя - {data["name"]}'
                                    f'\nПол: {data["gender"]}'
                                    f'\nДата рождения: {data["birth_date"]}'
                                    f'\nМесто рождения: {data["birth_place"]}'
                                    f'\nВремя рождения: {data["birth_time"]}'
                                    f'\nПолучать рассылку: {data["part_of_the_day"]}',
                               reply_markup=agree_inline_kb)


async def agree(callback_query: CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if data['part_of_the_day'] == 'Утром':
            time_preference = 'morning'
        else:
            time_preference = 'tomorrow'
        user = User(user_id=callback_query.from_user.id,
                    username=callback_query.from_user.username,
                    name=data['name'],
                    gender=data['gender'],
                    birth_date=datetime.strptime(data['birth_date'], '%d.%m.%Y').date(),
                    birth_place=data['birth_place'],
                    birth_time=None if data['birth_time'] is None else datetime.strptime(data['birth_time'],
                                                                                         '%H:%M').time(),
                    receive_day_period=time_preference)
        try:
            await user.create()
            logger.info(f'Пользователь {callback_query.from_user.id} успешно зарегистрирован в базе данных.')
        except UniqueViolationError:
            logger.error(f'Пользователь {callback_query.from_user.id} ранее был зарегистрирован.')

        if callback_query.data == 'client_agree':
            await FSMClientRegistration.schedule.set()
            await send(callback_query, state)
            await schedule(callback_query, 50)

        else:
            await FSMClientRegistration.client_change_info.set()
            await bot.send_message(callback_query.message.chat.id,
                                   text='Выберите какие данные необходимо изменить 🥺',
                                   reply_markup=change_inline_kb)


async def change_info(callback_query: CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        data_to_change = callback_query.data.split('_')[1]
        if data_to_change != 'receive':
            await FSMClientRegistration.client_what_to_change.set()
            data['data_to_change'] = data_to_change
            await bot.send_message(callback_query.message.chat.id,
                                   text='Введите корректные данные 😌')
        else:
            await FSMClientRegistration.client_daytime_change.set()
            with open('media/backgrounds/horoscope-time.jpg', 'rb') as photo:
                await bot.send_photo(callback_query.message.chat.id,
                                     reply_markup=client_day_inline_kb, photo=photo)


async def what_to_change(message: types.Message, state: FSMContext):
    await message.delete()
    user = User(user_id=message.from_user.id)
    async with state.proxy() as data:
        match data['data_to_change']:
            case 'name':
                await user.update(name=message.text).apply()
            case 'gender':
                await user.update(gender=message.text).apply()
            case 'date':
                await user.update(birth_date=datetime.strptime(message.text, '%d.%m.%Y').date()).apply()
            case 'birthplace':
                await user.update(birth_place=message.text).apply()
            case 'birthtime':
                await user.update(birth_time=datetime.strptime(message.text, '%H:%M').time()).apply()
        await bot.send_message(message.from_user.id,
                               text='Данные были успешно изменены 😄')
        logger.info(f'Пользователь {message.from_user.id} изменил данные')
        await state.finish()
        await send(message, state)
        await schedule(message, 50)


async def change_daytime(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    if callback_query.data == "day_morning":
        day_info = 'morning'
    else:
        day_info = 'tomorrow'
    user = User(user_id=callback_query.from_user.id)
    await user.update(receive_day_period=day_info).apply()
    await FSMClientRegistration.schedule.set()
    await bot.send_message(callback_query.from_user.id,
                           text='Данные были успешно изменены 😄')
    logger.info(f'Пользователь {callback_query.from_user.id} изменил время получение гороскопа')
    await send(callback_query, state)
    await schedule(callback_query, 50)


async def schedule(message: types.Message | CallbackQuery, wait_for: int):
    data = await User.select('receive_day_period').where(User.user_id == message.from_user.id).gino.first()
    time_preference = data[0]
    if time_preference == 'tomorrow':
        while True:
            await asyncio.sleep(wait_for)
            now = datetime.now()
            if now.hour == 15 and now.minute == 0:
                await prepare_data(user_id=message.from_user.id)
                logger.success(f'Функция schedule была успешно вызвана в {now.hour}:{now.minute}')
    else:
        while True:
            await asyncio.sleep(wait_for)
            now = datetime.now()
            if now.hour == 6 and now.minute == 39:
                await prepare_data(user_id=message.from_user.id)
                logger.success(f'Функция schedule была успешно вызвана в {now.hour}:{now.minute}')


def register_handlers_client(disp: Dispatcher):
    disp.register_message_handler(start_command, commands=['start', 'help'], state='*')
    disp.register_message_handler(name_info, state=FSMClientRegistration.client_name)
    disp.register_callback_query_handler(gender_info, Text(startswith='gender'),
                                         state=FSMClientRegistration.client_gender)
    disp.register_message_handler(check_birthdate, state=FSMClientRegistration.client_birth_date)
    disp.register_message_handler(birthplace_info, state=FSMClientRegistration.client_birth_place)
    disp.register_callback_query_handler(birth_time, Text(startswith='know'),
                                         state=FSMClientRegistration.client_birth_time)
    disp.register_message_handler(set_birth_time, state=FSMClientRegistration.client_birth_time_set)
    disp.register_callback_query_handler(prepare_datas, Text(startswith='date'),
                                         state=FSMClientRegistration.client_send_date)
    disp.register_callback_query_handler(agree, Text(startswith='client'), state=FSMClientRegistration.client_agree)
    disp.register_callback_query_handler(change_info, Text(startswith='change'),
                                         state=FSMClientRegistration.client_change_info)
    disp.register_message_handler(what_to_change, state=FSMClientRegistration.client_what_to_change)
    disp.register_callback_query_handler(change_daytime, Text(startswith='day'),
                                         state=FSMClientRegistration.client_daytime_change)
    disp.register_message_handler(send, commands=['send'], state='*')
    disp.register_message_handler(change, commands=['change'], state='*')
    disp.register_message_handler(get_my_info, commands=['get_info'], state='*')
    disp.register_message_handler(schedule, state='*')
