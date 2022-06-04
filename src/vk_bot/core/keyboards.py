from dataclasses import dataclass

from vk_api.keyboard import VkKeyboardColor, VkKeyboard


@dataclass
class KeyBoardButton:
    text: str
    color: VkKeyboardColor = VkKeyboardColor.PRIMARY


def get_keyboard(button_rows: list[list[KeyBoardButton]]):
    keyboard = VkKeyboard()
    for row in button_rows:
        for button in row:
            keyboard.add_button(label=button.text, color=button.color)
        if row != button_rows[-1]:
            keyboard.add_line()
    return keyboard


def get_answers_keyboard(count=5):
    button_rows = []
    row = []
    for answer in range(1, count + 1):
        row.append(KeyBoardButton(text=str(answer)))

        if len(row) >= 3:
            button_rows.append(row)
            row = []
    if row:
        button_rows.append(row)

    return get_keyboard(button_rows)


def get_next_circle_keyboard():
    button_rows = [
        [KeyBoardButton(text='Следующий круг', color=VkKeyboardColor.POSITIVE)],
        [KeyBoardButton(text='Результаты')],
        [KeyBoardButton(text='Завершить игру', color=VkKeyboardColor.NEGATIVE)]
    ]
    return get_keyboard(button_rows)


def get_main_menu_keyboard():
    button_rows = [
        [KeyBoardButton(text='Одиночная игра')],
        [KeyBoardButton(text='Мультиплеер')]
    ]
    return get_keyboard(button_rows)


def get_select_collection_keyboard():
    button_rows = [
        [KeyBoardButton(text='Загрузить свою', color=VkKeyboardColor.POSITIVE)],
        [KeyBoardButton(text='Стандартная')],
    ]
    return get_keyboard(button_rows)


def get_back_keyboard():
    button_rows = [
        [KeyBoardButton(text='Назад', color=VkKeyboardColor.SECONDARY)]
    ]
    return get_keyboard(button_rows)
