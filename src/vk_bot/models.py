from django.db import models


class VkUser(models.Model):
    chat_id = models.CharField(max_length=15, verbose_name='chat_id')
    name = models.CharField(max_length=150, verbose_name='Имя', blank=True)

    current_game = models.ForeignKey('Game', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    current_score = models.PositiveIntegerField(default=0)
    answered = models.BooleanField(default=False)

    # для игры с ведущим
    is_game_host = models.BooleanField(default=False)
    was_game_circle_host = models.BooleanField(default=False)
    cards_in_hand = models.ManyToManyField('Image', blank=True, related_name='cards_in_hand')
    current_card_number = models.PositiveIntegerField(blank=True, null=True)

    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Пользователь Вконтакте'
        verbose_name_plural = 'Пользователи Вконтакте'
        ordering = ['-update_date']

    def __str__(self):
        return f'{self.chat_id} ({self.name})'


class Collection(models.Model):
    standard = models.BooleanField(default=False)
    album_url = models.TextField(blank=True)

    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Коллекиция'
        verbose_name_plural = 'Коллекиции'
        ordering = ['-update_date']


class Image(models.Model):
    collection = models.ForeignKey('Collection', on_delete=models.CASCADE, related_name='images')

    attachment_data = models.CharField(max_length=1000)

    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Изображение'
        verbose_name_plural = 'Изображения'
        ordering = ['-update_date']


class ImageWord(models.Model):
    image = models.ForeignKey('Image', on_delete=models.CASCADE, related_name='words')
    name = models.TextField(db_index=True)

    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Слово изображения'
        verbose_name_plural = 'Слова изображения'
        ordering = ['-update_date']

    def __str__(self):
        return f'{self.name}'


class Game(models.Model):
    collection = models.ForeignKey('Collection', on_delete=models.CASCADE, blank=True, null=True)
    status = models.CharField(
        choices=[('creating', 'creating'), ('waiting', 'waiting'), ('started', 'started'), ('finished', 'finished')],
        default='created', max_length=400)

    creator = models.ForeignKey('VkUser', on_delete=models.PROTECT, related_name='created_games')

    stage = models.CharField(choices=[('getting_answers', 'getting_answers'),
                                      ('distribution_of_cards', 'distribution_of_cards')],
                             default='distribution_of_cards', max_length=400)

    single = models.BooleanField(default=False)

    used_images = models.ManyToManyField('Image', blank=True)

    current_images = models.ManyToManyField('Image', blank=True, related_name='current_images')
    current_attachment_data = models.JSONField(blank=True, null=True)
    current_word = models.CharField(max_length=400, blank=True)
    current_correct_answer = models.PositiveIntegerField(blank=True, null=True)

    with_host = models.BooleanField(default=False)

    creation_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Игра'
        verbose_name_plural = 'Игры'
        ordering = ['-update_date']
