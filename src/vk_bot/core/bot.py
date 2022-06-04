import random
import time
from typing import Union

import vk_api
from vk_api import VkUpload
from vk_api.keyboard import VkKeyboard
from vk_api.longpoll import VkLongPoll, VkEventType, Event

from config.logger import logger
from config.settings import VK_TOKEN
from vk_bot.core import keyboards
from vk_bot import models
from vk_bot.core.game import GameProcess
from vk_bot.core.keyboards import KeyBoardButton

if not VK_TOKEN:
    raise ValueError('VK_TOKEN не может быть пустым')


class NextStep:
    def __init__(self, callback, *args, **kwargs):
        self.callback = callback
        self.args = args
        self.kwargs = kwargs


class VkBot:
    def __init__(self, token):
        self.vk = vk_api.VkApi(token=token)
        self.long_poll = VkLongPoll(self.vk)
        self.upload = VkUpload(self.vk)
        self.next_step_users: {str: NextStep} = {}

    def send_message(self, user_id: str, text, keyboard: VkKeyboard = None, photo_attachments: list = None):
        """
        Отправка сообщения пользователю.
        """

        values = {
            'user_id': user_id,
            'message': text,
            'random_id': random.randint(0, 2048)
        }

        if keyboard:
            values['keyboard'] = keyboard.get_keyboard(),

        if photo_attachments:
            values['attachment'] = ','.join(photo_attachments)
        self.vk.method('messages.send', values)

    def upload_photos(self, photo) -> list:
        response = self.upload.photo_messages(photo)
        attachments = ''
        for img in response:
            owner_id = img['owner_id']
            photo_id = img['id']
            access_key = img['access_key']
            attachments += f'photo{owner_id}_{photo_id}_{access_key},'
        if attachments:
            attachments = attachments[:-1]
        return attachments

    def polling(self):
        """
        Получение обновлений от Вк.
        :return:
        """
        logger.info('Вк бот запущен...')
        for event in self.long_poll.listen():
            event: Event
            self.event_handling(event)

    def infinity_polling(self):
        """
        Получение обновлений от Вк без остановки.
        :return:
        """
        while True:
            try:
                self.polling()
            except Exception as e:
                time.sleep(1)
                continue

    def get_user(self, event) -> models.VkUser:
        """
        Получение или создание пользователя из базы данных.
        :param event:
        :return:
        """
        user = self.vk.method("users.get", {"user_ids": event.user_id})
        fullname = user[0]['first_name'] + ' ' + user[0]['last_name']
        try:
            user_object = models.VkUser.objects.get(chat_id=event.user_id)
        except models.VkUser.DoesNotExist:
            user_object = models.VkUser.objects.create(chat_id=event.user_id, name=fullname)
        return user_object

    def register_next_step_by_user_id(self, user_id, callback, *args, **kwargs):
        """
        Регистрация функции, которая обработает слдующий ивент по user_id.
        """
        next_step = NextStep(callback, *args, **kwargs)
        self.next_step_users[user_id] = next_step

    def register_next_step(self, event, callback, *args, **kwargs):
        """
        Регистрация функции, которая обработает слдующий ивент.
        """
        user_id = event.user_id
        self.register_next_step_by_user_id(user_id, callback, *args, **kwargs)

    def processing_next_step(self, event, user):
        """
        Обработка запланированных ивентов
        """
        user_id = event.user_id
        if self.next_step_users.get(user_id):
            next_step = self.next_step_users[user_id]
            del self.next_step_users[user_id]
            next_step.callback(event, *next_step.args, **next_step.kwargs)
            return True

    def event_handling(self, event):
        """
        Обработка событий бота.
        """
        if event.to_me:
            user = self.get_user(event)
            logger.info(f'New event [user: {user}, type: {event.type}]: "{event.text}"')
            if self.processing_next_step(event, user):
                return
            elif event.type == VkEventType.MESSAGE_NEW:
                self.message_processing(event, user)

    def message_processing(self, event, user: models.VkUser):
        """
        Обработка текстовых сообщений.
        """

        event_text = event.text

        if event_text.lower() in ['начать', 'start']:
            collection = models.Collection.objects.filter(standard=True).first()
            if not collection:
                self.send_message(user_id=user.chat_id, text='Чат бот в разработке 😉')

            game = models.Game.objects.create(single=True, collection=collection, status='started',
                                              stage='getting_answers')
            user.current_game = game
            user.save()

            game_process = GameProcess(game=game)
            attachment_data, word = game_process.start_circle()
            print('ababa')

            self.send_message(user_id=user.chat_id, text='Привет!',
                              photo_attachments=attachment_data)
            self.send_message(user_id=user.chat_id, text=word, keyboard=keyboards.get_answers_keyboard())
            return

        current_game = user.current_game
        if current_game:
            self.game_execution(user=user, game=current_game, event_text=event_text)
            return

    def game_execution(self, user, game, event_text):
        if game.stage == 'getting_answers':
            if event_text not in ['1', '2', '3', '4', '5']:
                self.send_message(user_id=user.chat_id, text='Воспользуйтесь клавиатурой или введите число от 1 до 5',
                                  keyboard=keyboards.get_answers_keyboard())
                return
            user_answer = int(event_text)

            if user.current_game.current_correct_answer == user_answer:
                self.send_message(user_id=user.chat_id, text='Хорош', keyboard=keyboards.get_next_circle_keyboard())
            else:
                self.send_message(user_id=user.chat_id, text='Не хорош', keyboard=keyboards.get_next_circle_keyboard())

            if game.single:
                game.stage = 'distribution_of_cards'
                game.save()
            return

        if game.stage == 'distribution_of_cards':
            if game.single:
                game_process = GameProcess(game=game)
                attachment_data, word = game_process.start_circle()

                self.send_message(user_id=user.chat_id, text='Следующий круг',
                                  photo_attachments=attachment_data)
                self.send_message(user_id=user.chat_id, text=word, keyboard=keyboards.get_answers_keyboard())
            return


bot = VkBot(VK_TOKEN)
