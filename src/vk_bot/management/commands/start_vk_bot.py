from django.core.management.base import BaseCommand

from config.settings import DEBUG
from vk_bot.core.bot import bot


class Command(BaseCommand):
    help = 'Запуск Вк бота'

    def handle(self, *args, **options):
        if DEBUG:
            bot.polling()
        else:
            bot.infinity_polling()
