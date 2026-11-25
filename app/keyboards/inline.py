from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import BRANCHES


def admin_branches_inline() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=branch, callback_data=f"admin_branch:{branch}")]
        for branch in BRANCHES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def complaint_reply_inline(complaint_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Javob yozish", callback_data=f"reply_complaint:{complaint_id}")]
        ]
    )
