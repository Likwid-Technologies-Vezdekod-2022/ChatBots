import random
import time
import traceback
from pprint import pprint
from typing import Union

import vk_api
from vk_api import VkUpload
from vk_api.keyboard import VkKeyboard
from vk_api.longpoll import VkLongPoll, VkEventType, Event

from config.logger import logger
from config.settings import VK_BOT_TOKEN, VK_STANDALONE_APP_ID, VK_STANDALONE_APP_TOKEN
from vk_bot.core import keyboards
from vk_bot import models
from vk_bot.core.game import GameProcess, clear_user_game_data, end_game, get_game_results_table
from vk_bot.core.keyboards import KeyBoardButton

if not VK_BOT_TOKEN:
    raise ValueError('VK_TOKEN не может быть пустым')


class NextStep:
    def __init__(self, callback, *args, **kwargs):
        self.callback = callback
        self.args = args
        self.kwargs = kwargs


class VkBot:
    def __init__(self, token):
        self.vk_bot = vk_api.VkApi(token=token)
        self.vk_standalone = vk_api.VkApi(app_id=VK_STANDALONE_APP_ID, token=VK_STANDALONE_APP_TOKEN)
        self.long_poll = VkLongPoll(self.vk_bot)
        self.upload = VkUpload(self.vk_bot)
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
        self.vk_bot.method('messages.send', values)

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
            try:
                self.event_handling(event)
            except:
                logger.error(traceback.format_exc())
                self.send_message(user_id=event.user_id, text='Что-то пошло не так 😞\n\n'
                                                              'Попробуйте позже или перезапустите бота командой "Старт"️\n'
                                                              'Мы уже работает над исправлением проблемы ⚙️')

    def infinity_polling(self):
        """
        Получение обновлений от Вк без остановки.
        :return:
        """
        while True:
            try:
                self.polling()
            except KeyboardInterrupt:
                exit(0)
            except Exception as e:
                time.sleep(1)
                continue

    def get_user(self, event) -> models.VkUser:
        """
        Получение или создание пользователя из базы данных.
        """
        vk_user = self.vk_bot.method("users.get", {"user_ids": event.user_id})
        fullname = vk_user[0]['first_name'] + ' ' + vk_user[0]['last_name']
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
            next_step.callback(event, user, *next_step.args, **next_step.kwargs)
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

            user.current_game = models.Game.objects.create(single=True, status='creating', stage='getting_answers',
                                                           creator=user)
            self.start_single_game(user=user, collection=collection, start_text='Привет!')
            return

        current_game = user.current_game
        if current_game and current_game.status != 'creating':
            self.game_execution(user=user, game=current_game, event_text=event_text)
            return

        if event_text.lower() == 'одиночная игра':
            user.current_game = models.Game.objects.create(single=True, status='creating', stage='getting_answers',
                                                           creator=user)
            user.save()
            self.send_message(user_id=user.chat_id,
                              text='Выберите коллекцию изображений',
                              keyboard=keyboards.get_select_collection_keyboard())

        elif event_text.lower() == 'мультиплеер':
            # self.send_in_development_message(user)

            self.send_message(user_id=user.chat_id,
                              text='Мультиплеер',
                              keyboard=keyboards.get_multiplayer_keyboard())

        elif event_text.lower() == 'найти игру':
            games = models.Game.objects.filter(status__in=['waiting', 'started'], single=False)[:5]

            if not games:
                self.send_message(user_id=user.chat_id,
                                  text=f'Сейчас нет активных игр 💁‍♂️\n'
                                       f'Создайте свою 😉')

            for game in games:
                self.send_message(user_id=user.chat_id,
                                  text=f'Игра #{game.id}\n'
                                       f'Статус: {game.status}\n'
                                       f'Игроки: {game.users.count()}',
                                  keyboard=keyboards.get_connect_to_game_keyboard(game.id))
        elif 'подключиться к игре ' in event_text.lower():
            try:
                game_id = int(event_text.split('#')[-1])
            except:
                self.send_message(user_id=user.chat_id,
                                  text=f'Не удалось распознать игру',
                                  keyboard=keyboards.get_main_menu_keyboard())
                return

            game = models.Game.objects.filter(id=game_id, status__in=['waiting', 'started'], single=False).first()
            if not game:
                self.send_message(user_id=user.chat_id,
                                  text=f'Похоже игра к которой вы пытаетесь подключиться, уже завершилась',
                                  keyboard=keyboards.get_multiplayer_keyboard())
                return

            self.connect_to_game(user=user, game=game)

        elif event_text.lower() == 'создать игру':
            user.current_game = models.Game.objects.create(single=False, status='creating', stage='getting_answers',
                                                           creator=user)
            user.save()
            self.send_message(user_id=user.chat_id,
                              text='Выберите коллекцию изображений',
                              keyboard=keyboards.get_select_collection_keyboard())

        elif event_text.lower() == 'стандартная':
            collection = models.Collection.objects.filter(standard=True).first()
            if user.current_game.single:
                self.start_single_game(user, collection=collection)
            else:
                self.start_multiplayer_game(user, collection=collection)

        elif event_text.lower() == 'загрузить свою':
            self.send_message(user_id=user.chat_id,
                              text='Отправьте ссылку на альбом с изображениями', keyboard=keyboards.get_back_keyboard())
            self.register_next_step(event, self.choosing_collection_by_url_step)

        elif event_text.lower() == 'основное меню':
            clear_user_game_data(user=user)
            self.send_message(user_id=user.chat_id,
                              text='Основное меню',
                              keyboard=keyboards.get_main_menu_keyboard())

        else:
            self.send_not_understand_message(user)

    def send_in_development_message(self, user):
        self.send_message(user_id=user.chat_id, text=f'Этот раздел находится в разработке 🔧')

    def send_not_understand_message(self, user):
        self.send_message(user_id=user.chat_id, text=f'Я вас не понял 🙈\n'
                                                     f'Воспользуйтесь клавиатурой😉',
                          keyboard=keyboards.get_main_menu_keyboard())

    def start_single_game(self, user, collection: models.Collection, start_text: str = 'Начинаем новую игру! 😎'):
        game = user.current_game
        game.collection = collection
        game.status = 'started'
        game.save()

        user.current_score = 0
        user.save()

        game_process = GameProcess(game=game)
        game_circle = game_process.start_circle()

        self.send_message(user_id=user.chat_id, text=start_text,
                          photo_attachments=game_circle.attachment_data)
        self.send_message(user_id=user.chat_id, text=game_circle.word,
                          keyboard=keyboards.get_answers_keyboard())

    def start_multiplayer_game(self, user, collection: models.Collection):
        game = user.current_game
        game.collection = collection
        game.status = 'waiting'
        game.save()

        user.current_score = 0
        user.save()

        self.send_message(user_id=user.chat_id, text='Всё готово 😎\n'
                                                     'Вы сможете начать игру, когда к ней кто-то подключится',
                          keyboard=keyboards.get_leave_game_keyboard())

        self.send_message(user_id=user.chat_id, text='Для того чтобы отправить приглашение на игру человеку, '
                                                     'отправьте ссылку на его профиль Вк в чат')

    def game_execution(self, user, game, event_text):
        if game.status == 'waiting':
            if event_text.lower() == 'покинуть игру':
                self.send_message(user_id=user.chat_id, text=f'Вы покинули игру')
                if game.users.count() <= 1:
                    end_game(game)
                else:
                    clear_user_game_data(user)
                return

            if 'vk.com' in event_text:
                inviting_person_url: str = event_text
                try:
                    inviting_person_username = \
                        inviting_person_url[inviting_person_url.find('vk.com/') + len('vk.com/'):].split('/')[0]
                    inviting_person_vk = self.vk_bot.method("users.get", {'user_ids': inviting_person_username})[0]
                    inviting_person = models.VkUser.objects.get(chat_id=inviting_person_vk['id'])
                except:
                    logger.error(traceback.format_exc())
                    self.send_message(user_id=user.chat_id, text=f'Не удалось пригласить человека')
                    return

                if inviting_person.current_game:
                    self.send_message(user_id=user.chat_id, text=f'Пользователь {inviting_person.name} '
                                                                 f'сейчас находится в игре')
                    return

                self.send_message(user_id=inviting_person.chat_id,
                                  text=f'{user.name} приглашает вас на игру #{game.id}\n'
                                       f'Статус: {game.status}\n'
                                       f'Игроки: {game.users.count()}',
                                  keyboard=keyboards.get_connect_to_game_keyboard(game.id))

                self.send_message(user_id=user.chat_id, text=f'Приглашение отправлено пользователю '
                                                             f'{inviting_person.name}')
                return
            elif event_text.lower() == 'начать игру':
                game.status = 'started'
                game.save()
                self.distribution_of_cards_in_game(game=game, users=game.users.all(), next_circle_text='Игра началась!')
                return
            return

        if game.single:
            if event_text.lower() == 'результаты':
                self.send_message(user_id=user.chat_id, text=f'Ваш счет в этой игре: {user.current_score} ✅',
                                  keyboard=keyboards.get_next_circle_keyboard())
                return
            elif event_text.lower() == 'завершить игру':
                self.send_message(user_id=user.chat_id, text=f'Игра звершена\n'
                                                             f'Ваш счет: {user.current_score} ✅',
                                  keyboard=keyboards.get_main_menu_keyboard())
                end_game(game)
                return
        else:
            if event_text.lower() == 'таблица результатов':
                self.send_message(user_id=user.chat_id, text=get_game_results_table(game=game, user=user),
                                  keyboard=keyboards.get_wait_circle_keyboard())
                return
            elif event_text.lower() == 'покинуть игру':
                self.send_message(user_id=user.chat_id, text=f'Вы покинули игру\n\n'
                                                             f'{get_game_results_table(game=game, user=user)}',
                                  keyboard=keyboards.get_main_menu_keyboard())
                if game.users.count() <= 1:
                    end_game(game)
                else:
                    clear_user_game_data(user)
                return

            if game.users.count() <= 1:
                self.send_message(user_id=user.chat_id, text=f'Игра завершена, так как все игроки вышли\n\n'
                                                             f'{get_game_results_table(game=game, user=user)}',
                                  keyboard=keyboards.get_main_menu_keyboard())
                end_game(game)
                return

        if not game.single and user.answered:
            self.send_message(user_id=user.chat_id, text='Следующий круг начнется, '
                                                         'когда все игроки ответят',
                              keyboard=keyboards.get_wait_circle_keyboard())
            return

        if game.stage == 'getting_answers':
            if event_text not in ['1', '2', '3', '4', '5']:
                self.send_message(user_id=user.chat_id, text='Воспользуйтесь клавиатурой или введите число от 1 до 5',
                                  keyboard=keyboards.get_answers_keyboard())
                return
            user_answer = int(event_text)

            if user.current_game.current_correct_answer == user_answer:
                message_text = 'Вы угадали! 🥳\n' \
                               'Вам начислено 3 балла'
                user.current_score += 3
            else:
                message_text = 'Вы не угадали 🤷‍♂️\n' \
                               'В этом раунде вы не зарабатываете очков'

            message_text += f'\n\nВаш счет в этой игре: {user.current_score} ✅'
            if game.single:
                self.send_message(user_id=user.chat_id, text=message_text,
                                  keyboard=keyboards.get_next_circle_keyboard())
            else:
                self.send_message(user_id=user.chat_id, text=message_text)
                self.send_message(user_id=user.chat_id, text='Следующий круг начнется, '
                                                             'когда все игроки ответят',
                                  keyboard=keyboards.get_wait_circle_keyboard())

            user.answered = True
            user.save()

            if not game.single and game.users.all().count() == game.users.filter(answered=True).count():
                self.distribution_of_cards_in_game(game=game, users=game.users.all())
                return

            if game.single:
                game.stage = 'distribution_of_cards'
                game.save()

            return

        if game.stage == 'distribution_of_cards':
            self.distribution_of_cards_in_game(game=game, users=[user])
            return

    def distribution_of_cards_in_game(self, game, users, next_circle_text='Следующий круг'):
        game.stage = 'getting_answers'
        game.save()

        game_process = GameProcess(game=game)
        game_circle = game_process.start_circle()

        need_end_game = False
        for game_user in users:
            game_user.answered = False

            if not game_circle:
                if game.single:
                    self.send_message(user_id=game_user.chat_id, text=f'Игра звершена!\n'
                                                                      f'Ваш счет: {game_user.current_score} ✅\n\n'
                                                                      f'Отличная работа 😉',
                                      keyboard=keyboards.get_main_menu_keyboard())
                else:
                    self.send_message(user_id=game_user.chat_id, text=f'Игра звершена!\n'
                                                                      f'{get_game_results_table(game=game, user=game_user)}\n\n'
                                                                      f'Отличная работа 😉',
                                      keyboard=keyboards.get_main_menu_keyboard())
                need_end_game = True

                continue
            if not need_end_game:
                self.send_message(user_id=game_user.chat_id, text=next_circle_text,
                                  photo_attachments=game_circle.attachment_data)
                self.send_message(user_id=game_user.chat_id, text=game_circle.word,
                                  keyboard=keyboards.get_answers_keyboard())
                game_user.save()

        if need_end_game:
            end_game(game)

    def choosing_collection_by_url_step(self, event, user, single=True):
        event_text = event.text

        if event_text == 'назад':
            self.send_message(user_id=event.user_id, text='Тогда в другой раз😊')
            self.send_message(user_id=event.user_id,
                              text='Выберите коллекцию изображений',
                              keyboard=keyboards.get_select_collection_keyboard())
            return

        album_url = event_text

        try:
            album_images = self.get_album_images(album_url=event_text)
        except:
            self.send_message(user_id=event.user_id,
                              text='Не удалось получить изображения из альбома\n'
                                   'Указана некорректная ссылка, либо альбом является закрытым\n\n'
                                   'Отправьте ссылку на альбом',
                              keyboard=keyboards.get_back_keyboard())
            self.register_next_step(event, self.choosing_collection_by_url_step)
            return

        album_images_count = len(album_images)
        if album_images_count < 6:
            self.send_message(user_id=event.user_id,
                              text='В этом альбоме слишком мало изображений с описанием\n'
                                   'Укажите другой альбом', keyboard=keyboards.get_back_keyboard())
            self.register_next_step(event, self.choosing_collection_by_url_step)
            return

        collection = models.Collection.objects.get_or_create(standard=False, album_url=album_url)[0]

        if collection.images.count() != album_images_count:
            collection.images.all().delete()

            for album_image in album_images:
                owner_id = album_image['owner_id']
                photo_id = album_image['id']

                photo_text: str = album_image['text']
                if not photo_text:
                    continue
                words = photo_text.lower().split()

                image = collection.images.create(
                    attachment_data=f'photo{owner_id}_{photo_id}'
                )

                image_words = [models.ImageWord(image=image, name=word) for word in words]
                models.ImageWord.objects.bulk_create(image_words)

        if single:
            self.start_single_game(user, collection=collection)

    def get_album_images(self, album_url):
        album_id = album_url.split('/')[-1].split('_')[1]
        owner_id = album_url.split('/')[-1].split('_')[0].replace('album', '')

        values = {
            'owner_id': owner_id,
            'album_id': album_id
        }

        album_images = self.vk_standalone.method('photos.get', values)['items']
        album_images = [album_image for album_image in album_images if album_image['text']]
        return album_images

    def connect_to_game(self, user, game):
        user.current_game = game
        user.current_score = 0
        user.answered = False
        user.save()

        game_process = GameProcess(game=game)
        game_circle = game_process.get_current_circle()

        self.send_message(user_id=user.chat_id, text=f'Вы подключились к игре #{game.id}',
                          photo_attachments=game_circle.attachment_data)

        if game.status == 'started':
            self.send_message(user_id=user.chat_id, text=game_circle.word,
                              keyboard=keyboards.get_answers_keyboard())
        else:
            self.send_message(user_id=user.chat_id, text='Ожидание начала игры\n\n',
                              keyboard=keyboards.get_start_multiplayer_game_keyboard())
            self.send_message(user_id=user.chat_id, text='Для того чтобы отправить приглашение на игру человеку, '
                                                         'отправьте ссылку на его профиль Вк в чат')

            self.send_message(user_id=game.creator.chat_id, text=f'К игре подключился {user.name}',
                              keyboard=keyboards.get_start_multiplayer_game_keyboard())


bot = VkBot(VK_BOT_TOKEN)
