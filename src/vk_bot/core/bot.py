import random
import time
import traceback

import vk_api
from vk_api import VkUpload
from vk_api.keyboard import VkKeyboard
from vk_api.longpoll import VkLongPoll, VkEventType, Event

from config.logger import logger
from config.settings import VK_BOT_TOKEN, VK_STANDALONE_APP_ID, VK_STANDALONE_APP_TOKEN
from vk_bot.core import keyboards
from vk_bot import models
from vk_bot.core.game import GameProcess, clear_user_game_data, end_game, get_game_results_table

if not VK_BOT_TOKEN:
    raise ValueError('VK_TOKEN не может быть пустым')

if not VK_STANDALONE_APP_ID:
    raise ValueError('VK_STANDALONE_APP_ID не может быть пустым')

if not VK_STANDALONE_APP_TOKEN:
    raise ValueError('VK_STANDALONE_APP_TOKEN не может быть пустым')


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
            self.start_single_game(user=user, collection=collection, start_text='Привет!\n'
                                                                                'Добро пожаловть в чат бота с игрой "Имаджинариум"\n\n'
                                                                                'Задача игры - угадать какую картинку я загадал\n'
                                                                                'Укажите номер изображения на котором изображено слово '
                                                                                '(номера считаются с лева на право)\n\n'
                                                                                'Игра завершится, когда в колоде закончатся карты')
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

        elif event_text.lower() == 'создать игру с ведущим':
            user.current_game = models.Game.objects.create(single=False, with_host=True, status='creating',
                                                           stage='getting_answers',
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
            self.game_waiting(user=user, game=game, event_text=event_text)
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
        # == игра с ведущим
        if game.stage == 'game_host_writing_word':
            if user.is_game_host:
                try:
                    user.sent_card = user.cards_in_hand.all()[int(event_text) - 1]
                    user.save()
                except:
                    photo_attachments = [image.attachment_data for image in user.cards_in_hand.all()]
                    self.send_message(user_id=user.chat_id,
                                      text=f'Введите корректный номер карты',
                                      photo_attachments=photo_attachments,
                                      keyboard=keyboards.get_answers_keyboard(count=len(photo_attachments)))
                    return
                self.send_message(user_id=user.chat_id,
                                  text=f'Введите слово, которое обозначет то, что изображено на карте')
                game.current_images.add(user.sent_card)
                game.stage = 'sending_word'
                game.save()
            else:
                self.send_message(user_id=user.chat_id, text='Дождитесь пока ведущий загадает слово',
                                  keyboard=keyboards.get_wait_circle_keyboard())
            return

        elif game.stage == 'sending_word':
            if user.is_game_host:
                game.stage = 'send_cards'
                game.current_word = event_text

                self.send_message(user_id=user.chat_id, text='Отлично!\n'
                                                             'Теперь дождитесь пока все сделают свой ход',
                                  keyboard=keyboards.get_wait_circle_keyboard())

                for game_user in game.users.exclude(is_game_host=True):
                    self.send_message(user_id=game_user.chat_id,
                                      text=f'Ведущий загадал: {game.current_word}')
                    photo_attachments = [image.attachment_data for image in game_user.cards_in_hand.all()]
                    self.send_message(user_id=game_user.chat_id,
                                      text='Отправьте карту, которая асоциируется у вас с этим словом',
                                      photo_attachments=photo_attachments,
                                      keyboard=keyboards.get_answers_keyboard(count=len(photo_attachments)))

                game.save()
            return

        elif game.stage == 'send_cards':
            if user.is_game_host:
                self.send_message(user_id=user.chat_id, text='Дождитесь пока все сделают свой ход',
                                  keyboard=keyboards.get_wait_circle_keyboard())
                return
            else:
                try:
                    user.sent_card = user.cards_in_hand.all()[int(event_text) - 1]
                    user.save()
                except:
                    photo_attachments = [image.attachment_data for image in user.cards_in_hand.all()]
                    self.send_message(user_id=user.chat_id,
                                      text=f'Введите корректный номер карты',
                                      photo_attachments=photo_attachments,
                                      keyboard=keyboards.get_answers_keyboard(count=len(photo_attachments)))
                    return

                game.current_images.add(user.sent_card)
                game.save()

                self.send_message(user_id=user.chat_id, text='Отлично!\n'
                                                             'Теперь дождитесь пока все сделают свой ход',
                                  keyboard=keyboards.get_wait_circle_keyboard())

                # отправка всем списка карт
                if game.current_images.count() >= game.users.filter(is_game_host=False).count():
                    photo_attachments = [image.attachment_data for image in game.current_images.all()]
                    random.shuffle(photo_attachments, random.random)
                    game.current_attachment_data = photo_attachments

                    for game_user in game.users.all():
                        if game_user.is_game_host:
                            # определяем каку юкарту загадали
                            game.current_correct_answer = \
                                photo_attachments.index(game_user.sent_card.attachment_data) + 1
                            self.send_message(user_id=game_user.chat_id,
                                              text=f'Полученный набор карт',
                                              photo_attachments=photo_attachments,
                                              keyboard=keyboards.get_wait_circle_keyboard())
                        else:
                            self.send_message(user_id=game_user.chat_id,
                                              text=f'Отдагайте на какой карте изображено загаданное слово',
                                              photo_attachments=photo_attachments,
                                              keyboard=keyboards.get_answers_keyboard(count=len(photo_attachments)))
                    game.stage = 'getting_answers'
                    game.save()
            return

        # ==

        # ожидание ответа всех игроков
        if not game.single and user.answered:
            self.send_message(user_id=user.chat_id, text='Следующий круг начнется, '
                                                         'когда все игроки ответят',
                              keyboard=keyboards.get_wait_circle_keyboard())
            return

        if game.stage == 'getting_answers':
            self.getting_game_answers(game=game, user=user, event_text=event_text)
            return

        if game.stage == 'distribution_of_cards':
            self.distribution_of_cards_in_game(game=game, users=[user])
            return

    def game_waiting(self, user, game, event_text):
        """
        Ожидание подключения игроков
        """
        if event_text.lower() == 'покинуть игру':
            self.send_message(user_id=user.chat_id, text=f'Вы покинули игру')
            if game.users.count() <= 1:
                end_game(game)
            else:
                clear_user_game_data(user)
            return

        if 'vk.com' in event_text:
            self.invite_person_by_link(game=game, user=user, inviting_person_url=event_text)
            return
        elif event_text.lower() == 'начать игру':
            game.status = 'started'
            game.save()
            if game.with_host:
                game_process = GameProcess(game=game)
                game_process.init_game_with_host()
                self.game_host_move(game=game, start_game=True)
            else:
                self.distribution_of_cards_in_game(game=game, users=game.users.all(), next_circle_text='Игра началась!')
            return

    def invite_person_by_link(self, game, user, inviting_person_url: str):
        """
        Приглашение человека в игру
        """
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

    def getting_game_answers(self, game, user, event_text):
        """
        Получение ответов
        """
        if event_text not in ['1', '2', '3', '4', '5']:
            self.send_message(user_id=user.chat_id, text='Воспользуйтесь клавиатурой или введите число от 1 до 5',
                              keyboard=keyboards.get_answers_keyboard())
            return
        user_answer = int(event_text)

        if game.with_host:
            if user.answered:
                self.send_message(user_id=user.chat_id, text='Прекрасно!\n'
                                                             'Дождитесь, пока все дадут свой ответ',
                                  keyboard=keyboards.get_answers_keyboard())
                return

            user.answer = user_answer
            user.answered = True
            user.save()

            self.send_message(user_id=user.chat_id, text='Прекрасно!\n'
                                                         'Осталось подождать, пока все дадут свой ответ',
                              keyboard=keyboards.get_answers_keyboard())

            # если все дали свой ответ
            if game.users.filter(answered=True).count() >= game.users.exclude(is_game_host=True).count():
                game_users = game.users.all()
                game_current_attachment_data = game.current_attachment_data

                host_card_answers_count = 0
                users_card_answers = {}

                for attachment_data, answer in zip(game_current_attachment_data,
                                                   range(1, len(game_current_attachment_data) + 1)):

                    image = models.Image.objects.get(attachment_data=attachment_data)
                    image_user = game_users.get(sent_card=image)
                    answers_count = game_users.exclude(is_game_host=True).filter(answer=answer).count()

                    if image_user.is_game_host:
                        host_card_answers_count += answers_count
                    else:
                        if not users_card_answers.get(image_user):
                            users_card_answers[image_user] = 0
                        users_card_answers[image_user] += answers_count

                if host_card_answers_count == 0 \
                        or host_card_answers_count >= game_users.exclude(is_game_host=True).count():
                    for game_user in game_users:
                        if game_user.is_game_host:
                            users_card_answers[game_user] = 0
                            continue
                        game_user.current_score += 2
                        users_card_answers[game_user] = 2
                        game_user.save()
                else:
                    for game_user in game_users:
                        if game_user.is_game_host:
                            game_user.current_score += 2
                            users_card_answers[game_user] = 2
                        else:
                            game_user.current_score += users_card_answers[game_user]
                        game_user.save()

                users_card_answers_table = ''
                for game_user, score in users_card_answers.items():
                    users_card_answers_table += f'\n{game_user} {score}'

                won_user = None
                for game_user in game_users:
                    if game_user.current_score >= 40:
                        won_user = game_user

                    self.send_message(user_id=game_user.chat_id,
                                      text=f'Баллы в этом круге:\n {users_card_answers_table}\n\n'
                                           f'{get_game_results_table(game=game, user=game_user)}\n\n'
                                           f'Отличная работа 😉')

                    game_user.cards_in_hand.remove(game_user.sent_card)
                    game_user.is_game_host = False
                    game_user.answered = False
                    game_user.sent_card = None
                    game_user.answer = None
                    game_user.save()

                if won_user:
                    end_game(game=game)
                    for game_user in game_users:
                        self.send_message(user_id=game_user.chat_id,
                                          text=f'Игра завершена!\n'
                                               f'Победитель: {won_user.name} 🥳',
                                          keyboard=keyboards.get_main_menu_keyboard())

                    return

                game_process = GameProcess(game=game)
                game_process.give_game_users_one_card()
                self.game_host_move(game)

            return



        else:
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

    def choosing_collection_by_url_step(self, event, user: models.VkUser):
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

        if user.current_game.single:
            self.start_single_game(user, collection=collection)
        else:
            self.start_multiplayer_game(user, collection=collection)

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

    def game_host_move(self, game: models.Game, start_game=False):
        game_users = game.users.all()
        host = game.users.filter(was_game_circle_host=False).first()
        if not host:
            game.users.update(was_game_circle_host=False)
            host = game_users.first()
        host.is_game_host = True
        host.was_game_circle_host = True
        host.save()

        for user in game_users:
            if start_game:
                self.send_message(user_id=user.chat_id, text='Игра началась!')
            else:
                self.send_message(user_id=user.chat_id, text='Начинаем новый круг!')

            photo_attachments = [image.attachment_data for image in user.cards_in_hand.all()]

            if user == host:
                self.send_message(user_id=user.chat_id, text=f'Вы ведущий этого круга\n'
                                                             f'Загадайте одну из своих карт',
                                  photo_attachments=photo_attachments,
                                  keyboard=keyboards.get_answers_keyboard(count=len(photo_attachments)))
            else:
                self.send_message(user_id=user.chat_id, text=f'Ваши карты\n\n'
                                                             f'Дождитесь пока ведущий загадает слово',
                                  photo_attachments=photo_attachments,
                                  keyboard=keyboards.get_wait_circle_keyboard())

        game.current_images.set([])
        game.current_attachment_data = None
        game.current_correct_answer = None
        game.current_word = ''
        game.stage = 'game_host_writing_word'
        game.save()

    def game_host_writing_word(self, game: models.Game, host):
        host = game.users.filter(is_game_host=True).first()
        if not host:
            self.game_host_move(host)
        self.send_message(user_id=host.chat_id, text=f'Введите слово, которое обозначет то, что изображено на карте')

    def distribution_of_cards_in_game_with_host(self, game, event_text):
        pass


bot = VkBot(VK_BOT_TOKEN)
