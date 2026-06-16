from aiogram.fsm.state import State, StatesGroup

from bot.keyboards.profile import ProfileField


class UserSession(StatesGroup):
    blocked = State()


class Registration(StatesGroup):
    works_alone = State()
    packages = State()
    price_60 = State()
    withdrawal_method = State()
    work_start = State()
    work_end = State()
    finished_filling = State()


class ProfileEdit(StatesGroup):
    menu = State()
    works_alone = State()
    packages = State()
    price_60 = State()
    withdrawal_method = State()
    work_start = State()
    work_end = State()


REGISTRATION_INPUT_STATES = (
    Registration.works_alone,
    Registration.packages,
    Registration.price_60,
    Registration.withdrawal_method,
    Registration.work_start,
    Registration.work_end,
)

STATE_BY_FIELD = {
    ProfileField.works_alone: ProfileEdit.works_alone,
    ProfileField.packages: ProfileEdit.packages,
    ProfileField.price_60: ProfileEdit.price_60,
    ProfileField.withdrawal_method: ProfileEdit.withdrawal_method,
    ProfileField.work_start: ProfileEdit.work_start,
    ProfileField.work_end: ProfileEdit.work_end,
}

EDIT_FIELD_STATES = tuple(STATE_BY_FIELD.values())
