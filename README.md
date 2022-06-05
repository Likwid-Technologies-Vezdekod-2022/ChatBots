# ChatBots

### Стэк
- Python >= 3.9
- Django
- vk_api

## Запуск проекта

1. Установить зависимости (в виртуальном окружении python)
    ```
    pip install -r requirements.txt
    ```
2. Создать и заполнить файл с переменными окружения `src/.env`
    ```
    cp src/.env.example src/.env
    ```
   
    ```
    DEBUG=False # режим запуска web интерфейса
    SECRET_KEY=secret # Django secret
    VK_BOT_TOKEN=bot_token # Токен Вк бота
    VK_STANDALONE_APP_ID=1234 # Id standalone Вк приложения
    VK_STANDALONE_APP_TOKEN=app_token # Token standalone Вк приложения
    ```
3. Выполнить миграции
   ```
   python src/manage.py migrate
   ```
4. Заполнить БД данными 
   ```
   python src/manage.py init_db
   ```
5. Запустить бота Вк
   ```
   python src/manage.py start_vk_bot
   ```