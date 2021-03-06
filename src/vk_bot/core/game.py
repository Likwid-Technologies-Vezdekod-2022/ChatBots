import random
from dataclasses import dataclass
from typing import Union

from django.db.models import Q

from config.logger import logger
from vk_bot import models


@dataclass
class GameCircle:
    attachment_data: list
    word: str


# @dataclass()
# class GameCircleWithHost:
#     attachment_data: list
#     word: str
#     ho


class GameProcess:
    def __init__(self, game: models.Game):
        self.game = game
        self.collection = game.collection

    def start_circle(self) -> Union[GameCircle, None]:
        images = self.game.collection.images.order_by('?')
        used_images_ids = self.game.used_images.values_list('id', flat=True)
        if used_images_ids:
            images = images.exclude(id__in=used_images_ids)

        if not images:
            return

        words = images.values_list('words__name', flat=True).distinct()
        right_word = random.choice(words)

        other_images = images.filter(~Q(words__name=right_word))[:4]
        right_image: models.Image = images.filter(words__name=right_word).first()

        self.game.used_images.add(*other_images)
        self.game.used_images.add(right_image)

        current_images = [right_image] + list(other_images)
        self.game.current_images.set(current_images)

        attachment_data = [image.attachment_data for image in current_images]
        random.shuffle(attachment_data, random.random)

        if len(attachment_data) < 5:
            return

        self.game.current_attachment_data = attachment_data
        self.game.current_word = right_word
        self.game.current_correct_answer = attachment_data.index(right_image.attachment_data) + 1
        logger.info(f'game: {self.game.id}, current_correct_answer: {self.game.current_correct_answer}')

        self.game.stage = 'getting_answers'
        self.game.save()

        return GameCircle(attachment_data=attachment_data, word=f'Загаданное слово: {right_word}')

    def get_current_circle(self):
        return GameCircle(attachment_data=self.game.current_attachment_data,
                          word=f'Загаданное слово: {self.game.current_word}')

    def init_game_with_host(self):
        users = self.game.users.all()
        users_count = users.count()
        images = self.game.collection.images.order_by('?')

        i = 0
        for user in users:
            dealt_images = images[i: i + users_count]
            user.cards_in_hand.set(dealt_images)
            self.game.used_images.add(*dealt_images)

            i += i + users_count

    def give_game_users_one_card(self):
        users = self.game.users.all()
        images = self.game.collection.images.order_by('?')

        i = 0
        for user in users:
            user.cards_in_hand.add(images[i])
            self.game.used_images.add(images[i])
            i += 1

    def start_circle_with_host(self, ) -> Union[GameCircle, None]:
        images = self.game.collection.images.order_by('?')
        used_images_ids = self.game.used_images.values_list('id', flat=True)
        if used_images_ids:
            images = images.exclude(id__in=used_images_ids)

        if not images:
            return

        words = images.values_list('words__name', flat=True).distinct()
        right_word = random.choice(words)

        other_images = images.filter(~Q(words__name=right_word))[:4]
        right_image: models.Image = images.filter(words__name=right_word).first()

        self.game.used_images.add(*other_images)
        self.game.used_images.add(right_image)

        current_images = [right_image] + list(other_images)
        self.game.current_images.set(current_images)

        attachment_data = [image.attachment_data for image in current_images]
        random.shuffle(attachment_data, random.random)

        if len(attachment_data) < 5:
            return

        self.game.current_attachment_data = attachment_data
        self.game.current_word = right_word
        self.game.current_correct_answer = attachment_data.index(right_image.attachment_data) + 1
        logger.info(f'game: {self.game.id}, current_correct_answer: {self.game.current_correct_answer}')

        self.game.stage = 'getting_answers'
        self.game.save()

        return GameCircle(attachment_data=attachment_data, word=f'Загаданное слово: {right_word}')


def clear_user_game_data(user: models.VkUser):
    user.current_game = None
    user.current_score = 0
    user.answered = False
    user.is_game_host = False
    user.answer = None
    user.save()


def end_game(game: models.Game):
    game.status = 'finished'
    game.users.update(current_game=None,
                      current_score=0,
                      answered=False,
                      is_game_host=False,
                      answer=None)
    game.save()


def get_game_results_table(game: models.Game, user: models.VkUser) -> str:
    game_users = game.users.order_by('-current_score').distinct()

    result = 'Общий счет\n===============\n'
    i = 1
    for game_user in game_users:
        result += f'{i}. {game_user.name}. Счет: {game_user.current_score}'
        if game_user == user:
            result += ' ⬅️'
        result += '\n'
        i += 1

    return result
