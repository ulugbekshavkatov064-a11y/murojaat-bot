from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from config import ADMIN_IDS
from app.keyboards.inline import admin_branches_inline, complaint_reply_inline
from app.keyboards.reply import admin_main_menu, cancel_keyboard
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
        f"✍️ ID: {complaint_id} shikoyatga javobingizni yozing.\n"
        f"Javob {escape(complaint['full_name'] or 'foydalanuvchi')} ga yuboriladi.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(AdminReplyStates.writing_reply)
async def reply_complaint_send(message: Message, state: FSMContext, bot: Bot):
    if message.text in ["⬅️ Bekor qilish", "Bekor qilish", "❌ Bekor qilish"]:
        await state.clear()
        await message.answer("Javob yuborish bekor qilindi.", reply_markup=admin_main_menu())
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Iltimos, javobni matn ko'rinishida yozing.")
        return

    data = await state.get_data()
    complaint = get_complaint_by_id(data.get("reply_complaint_id", 0))
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
    except Exception:
        await state.clear()
        await message.answer(
            "❌ Javobni yuborib bo'lmadi. Foydalanuvchi botni bloklagan bo'lishi mumkin.",
            reply_markup=admin_main_menu(),
        )
        return

    await state.clear()
    await message.answer(
        f"✅ Javob ID: {complaint['id']} shikoyat egasiga yuborildi.",
        reply_markup=admin_main_menu(),
    )
