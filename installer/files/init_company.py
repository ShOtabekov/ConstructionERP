# Данные компании и директора после установки (выполняется через odoo-bin shell).
import os

company_name = os.environ.get("ERP_COMPANY", "").strip()
password = os.environ.get("ERP_ADMIN_PASSWORD", "")

company = env.ref("base.main_company")
vals = {}
if company_name:
    vals["name"] = company_name
tj = env.ref("base.tj", raise_if_not_found=False)
if tj:
    vals["country_id"] = tj.id
if vals:
    company.write(vals)

lang = env["res.lang"].with_context(active_test=False).search([("code", "=", "ru_RU")], limit=1)
if lang and not lang.active:
    lang.active = True

admin = env.ref("base.user_admin")
admin_vals = {"lang": "ru_RU", "tz": "Asia/Dushanbe"}
if password:
    admin_vals["password"] = password
admin.write(admin_vals)
if company_name:
    admin.partner_id.name = "Директор"

env.cr.commit()
print("company:", company.name)
