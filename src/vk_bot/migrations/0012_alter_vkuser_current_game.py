# Generated by Django 4.0.5 on 2022-06-04 12:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vk_bot', '0011_vkuser_current_score'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vkuser',
            name='current_game',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='vk_bot.game'),
        ),
    ]
