# Generated by Django 4.0.5 on 2022-06-04 16:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vk_bot', '0014_game_current_attachment_data_game_current_word'),
    ]

    operations = [
        migrations.AddField(
            model_name='vkuser',
            name='answered',
            field=models.BooleanField(default=False),
        ),
    ]
