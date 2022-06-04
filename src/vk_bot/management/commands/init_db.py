import json
import os

from django.core.management.base import BaseCommand

from config.logger import logger
from config.settings import BASE_DIR
from vk_bot import models


class Command(BaseCommand):

    def handle(self, *args, **options):
        logger.info('Инициализация БД...')

        with open(os.path.join(BASE_DIR, 'data/standard_images.json'), encoding='utf-8') as f:
            standard_images = json.load(f)

        models.Collection.objects.filter(standard=True).delete()
        collection = models.Collection.objects.create(standard=True)
        for image_data in standard_images:
            image = collection.images.create(
                attachment_data=image_data['attachment_data'],
            )
            image_words = [models.ImageWord(image=image, name=word) for word in image_data['words']]
            models.ImageWord.objects.bulk_create(image_words)

        logger.info('База данных инициализирована')
