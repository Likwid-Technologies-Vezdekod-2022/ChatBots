import json
import os

from django.core.management.base import BaseCommand

from config.logger import logger
from config.settings import BASE_DIR
from vk_bot.core.bot import bot


class Command(BaseCommand):

    def handle(self, *args, **options):
        with open(os.path.join(BASE_DIR, r'data/words.txt')) as f:
            uploaded_files = []
            all_words = []
            i = 0
            for file_data in f.readlines():
                i += 1
                file_name, words = file_data.split('\t')
                words = words.replace('\n', '').split()

                response = bot.upload.photo_messages(f'data/standard_images/{file_name}')[0]
                owner_id = response['owner_id']
                photo_id = response['id']
                access_key = response['access_key']
                attachment = f'photo{owner_id}_{photo_id}_{access_key}'
                logger.info(f'Загружено: {attachment} ({i}/98)')

                all_words += words
                uploaded_files.append({
                    'file_name': file_name,
                    'words': words,
                    'attachment_data': attachment
                })

        with open(os.path.join(BASE_DIR, 'data/standard_images.json'), 'w', encoding='utf-8') as f:
            json.dump(uploaded_files, f, indent=4, ensure_ascii=False)

        with open(os.path.join(BASE_DIR, 'data/standard_words.json'), 'w', encoding='utf-8') as f:
            json.dump(list(set(all_words)), f, indent=4, ensure_ascii=False)
