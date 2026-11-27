from html import escape
import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, FSInputFile, Message

from config import ADMIN_IDS
from app.keyboards.inline import admin_branches_inline, complaint_reply_inline
from app.keyboards.reply import admin_main_menu
from app.services.database import get_complaint_by_id, get_complaints_by_branch
from app.services.report import build_excel_report
from app.utils.states import AdminReplyStates

router = Router()


@router.message(F.text == "📂 Shikoyatlar")
async def complaints_menu(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Filialni tanlang:", reply_markup=admin_branches_inline())


@router.callback_query(F.data.startswith("admin_branch:"))
async def complaints_by_branch(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Siz admin emassiz.", show_alert=True)
        return

    branch = callback.data.split(":", 1)[1]
    rows = get_complaints_by_branch(branch)

    if not rows:
        await callback.message.answer(f"{branch} filialida hozircha shikoyatlar yo'q.")
        await callback.answer()
        return

    await callback.message.answer(f"🏢 {branch} filialidagi shikoyatlar soni: {len(rows)} ta")

    for row in rows[:20]:
        text = (
            f"🆔 ID: {row['id']}\n"
            f"👤 Kim ustidan: {row['target_role']}\n"
            f"🕒 Sana: {row['created_at']}\n"
            f"🙍 Yuborgan: {escape(row['full_name'] or '-')}\n"
            f"📞 Telefon: {row['phone'] or '-'}\n"
            f"🔗 Username: @{row['username'] if row['username'] else '-'}\n"
            f"📝 Shikoyat:\n{escape(row['complaint_text'])}"
        )
        await callback.message.answer(text, reply_markup=complaint_reply_inline(row["id"]))

    if len(rows) > 20:
        await callback.message.answer("Faqat oxirgi 20 ta shikoyat ko'rsatildi.")

    await callback.answer()


@router.message(F.text == "📊 Shikoyatlar soni")
async def complaint_counts(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    file_path = build_excel_report()
    document = FSInputFile(file_path)
    await message.answer_document(
        document=document,
        caption="Excel hisobot tayyor bo'ldi. Unda umumiy son, filiallar kesimida son va batafsil ro'yxat bor.",
    )


REPLY_PROMPT_PREFIX = "✍️ Javob yozish | ID:"
CANCEL_TEXTS = ["⬅️ Bekor qilish", "Bekor qilish", "❌ Bekor qilish"]
MENU_TEXTS = ["📝 Talab yoki Taklif qilish", "📂 Shikoyatlar", "📊 Shikoyatlar soni"]


def _reply_target_id(message: Message) -> int | None:
    """Admin javob yozish xabariga (Reply) javob bergan bo'lsa, shikoyat ID sini qaytaradi."""
    replied = message.reply_to_message
    if not replied or not replied.text or not replied.from_user or not replied.from_user.is_bot:
        return None
    if replied.text.startswith(REPLY_PROMPT_PREFIX):
        match = re.search(r"ID:\s*(\d+)", replied.text)
    else:
        # Admin shikoyat kartasining o'ziga Reply qilib yozsa ham ishlaydi
        match = re.search(r"🆔 ID:\s*(\d+)", replied.text)
    return int(match.group(1)) if match else None


@router.callback_query(F.data.startswith("reply_complaint:"))
async def reply_complaint_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Siz admin emassiz.", show_alert=True)
        return

    complaint_id = int(callback.data.split(":", 1)[1])
    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        await callback.answer("Shikoyat topilmadi.", show_alert=True)
        return

    await state.set_state(AdminReplyStates.writing_reply)
    await state.update_data(reply_complaint_id=complaint_id)
    await callback.message.answer(
        f"{REPLY_PROMPT_PREFIX} {complaint_id}\n\n"
        f"Javobingizni shu xabarga yozing. "
        f"Javob {escape(complaint['full_name'] or 'foydalanuvchi')} ga yuboriladi.\n"
        f"Bekor qilish uchun: ⬅️ Bekor qilish",
        reply_markup=ForceReply(input_field_placeholder="Javobingizni yozing..."),
    )
    await callback.answer()


async def _is_reply_to_admin_prompt(message: Message, state: FSMContext) -> bool:
    if message.from_user.id not in ADMIN_IDS:
        return False
    text = message.text or ""
    if text.startswith("/") or text in MENU_TEXTS:
        return False
    if _reply_target_id(message) is not None:
        return True
    return await state.get_state() == AdminReplyStates.writing_reply.state


@router.message(_is_reply_to_admin_prompt)
async def reply_complaint_send(message: Message, state: FSMContext, bot: Bot):
    if message.text in CANCEL_TEXTS:
        await state.clear()
        await message.answer("Javob yuborish bekor qilindi.", reply_markup=admin_main_menu())
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Iltimos, javobni matn ko'rinishida yozing.")
        return

    complaint_id = _reply_target_id(message)
    if complaint_id is None:
        data = await state.get_data()
        complaint_id = data.get("reply_complaint_id", 0)

    complaint = get_complaint_by_id(complaint_id)
    if not complaint:
        await state.clear()
        await message.answer("Shikoyat topilmadi.", reply_markup=admin_main_menu())
        return

    user_text = (
        f"📩 Murojaatingizga javob keldi!\n\n"
        f"📝 Sizning murojaatingiz:\n{escape(complaint['complaint_text'])}\n\n"
        f"💬 Javob:\n{escape(text)}"
    )

    try:
        await bot.send_message(complaint["user_id"], user_text)
    except Exception as error:
        logging.exception("Javobni foydalanuvchiga yuborib bo'lmadi (ID: %s)", complaint["id"])
        await state.clear()
        await message.answer(
            f"❌ Javobni yuborib bo'lmadi. Foydalanuvchi botni bloklagan bo'lishi mumkin.\n"
            f"Sabab: {escape(str(error))}",
            reply_markup=admin_main_menu(),
        )
        return

    await state.clear()
    await message.answer(
        f"✅ Javob ID: {complaint['id']} shikoyat egasiga yuborildi.",
        reply_markup=admin_main_menu(),
    )
