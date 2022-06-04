import json

from django.core.management.base import BaseCommand

from config.logger import logger
from vk_bot import models


class Command(BaseCommand):

    def handle(self, *args, **options):
        logger.info('Инициализация БД...')

        with open('data/standard_images.json', encoding='utf-8') as f:
            standard_images = json.load(f)

        with open('data/standard_words.json', encoding='utf-8') as f:
            standard_words = json.load(f)

        models.Collection.objects.filter(standard=True).delete()
        collection = models.Collection.objects.create(standard=True, words=standard_words)
        for image_data in standard_images:
            image = collection.images.create(
                attachment_data=image_data['attachment_data'],
            )
            image_words = [models.ImageWord(image=image, name=word) for word in image_data['words']]
            models.ImageWord.objects.bulk_create(image_words)

        logger.info('База данных инициализирована')
