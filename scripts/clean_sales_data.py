"""Очистка базы от продаж: остаётся только структура ЖК.

Удаляет: договоры, брони, платёжные планы и графики, платежи, приходные и расходные
ордера, возвраты/расторжения и клиентов, созданных под эти сделки (с паспортными данными).
Оставляет: проекты, блоки, этажи, квартиры (все становятся «Свободна», кроме
заблокированных), планировки, фото, реквизиты, пользователей, лицензию, настройки.
Площадь магазинов возвращается к 100 м².

Запуск (Odoo остановлен, СНАЧАЛА СДЕЛАЙТЕ КОПИЮ БАЗЫ):
  scripts\\clean_sales_data.bat   (спросит подтверждение)
"""
from odoo import models

SHOP_AREA = 100.0
env = env(su=True)  # noqa: F821  (env даёт odoo shell)
counts = {}


def wipe(model):
    if model not in env:
        return
    recs = env[model].with_context(active_test=False).search([])
    counts[model] = len(recs)
    if recs:
        models.Model.unlink(recs)   # без проверок «только черновик»


for m in ("construction.cash.receipt", "construction.cash.expense", "construction.refund.line",
          "construction.refund", "construction.payment", "construction.payment.schedule",
          "construction.payment.plan", "construction.contract", "construction.reservation"):
    wipe(m)

Apt = env["construction.apartment"]
apts = Apt.search([("state", "in", ("sold", "reserved"))])
counts["квартир освобождено"] = len(apts)
if apts:
    models.Model.write(apts, {"state": "free"})
shops = Apt.search([("unit_type", "=", "shop"), ("area_total", "!=", SHOP_AREA)])
counts["магазинов: площадь 100 м²"] = len(shops)
if shops:
    shops.write({"area_total": SHOP_AREA})

# клиенты, заведённые под сделки (паспорт), если они не пользователи и не компании
Partner = env["res.partner"].with_context(active_test=False)
partners = Partner.search([("passport_number", "!=", False), ("user_ids", "=", False),
                           ("is_company", "=", False)])
removed = 0
for p in partners:
    try:
        with env.cr.savepoint():
            p.unlink()
            removed += 1
    except Exception:
        p.active = False
counts["клиентов удалено"] = removed

# нумерация договоров и ордеров — с 1
for code in ("construction.contract", "construction.cash.receipt", "construction.cash.expense",
             "construction.refund"):
    for seq in env["ir.sequence"].search([("code", "=", code)]):
        seq.number_next = 1

env.cr.commit()
for k, v in counts.items():
    print("%-35s %s" % (k, v))
print("\nГотово: база чистая, можно загружать досье (Продажи -> Импорт договоров из Excel).")
