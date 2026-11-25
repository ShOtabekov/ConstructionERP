from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..tools import license_core as lic

FREE_MODELS = {"construction.license.wizard"}


class Base(models.AbstractModel):
    """Без действующей лицензии (после пробного периода) данные
    «Строительной ERP» недоступны никому, кроме окна ввода ключа."""

    _inherit = "base"

    def _check_access(self, operation):
        res = super()._check_access(operation)
        if res or not self._name.startswith("construction.") or self._name in FREE_MODELS:
            return res
        if lic.get_status(self.env)["state"] == "expired":
            return self, lambda: AccessError(self.env._(
                "Пробный период или срок лицензии закончился.\n"
                "Откройте меню «Лицензия», отправьте разработчику код компьютера "
                "и введите полученный ключ."))
        return None


class ConstructionLicense(models.AbstractModel):
    _name = "construction.license"
    _description = "Лицензия Строительной ERP"

    @api.model
    def get_status(self):
        lic.touch(self.env)
        return lic.get_status(self.env, fresh=True)

    @api.model
    def _cron_touch(self):
        lic.touch(self.env)
        lic.get_status(self.env, fresh=True)


class ConstructionLicenseWizard(models.TransientModel):
    _name = "construction.license.wizard"
    _description = "Ввод лицензионного ключа"

    status_html = fields.Html("Состояние", compute="_compute_info", sanitize=False)
    machine_code = fields.Char("Код компьютера", compute="_compute_info")
    license_key = fields.Text("Лицензионный ключ")
    license_file = fields.Binary("Файл лицензии (.lic)", attachment=False)
    license_file_name = fields.Char()

    def _compute_info(self):
        st = lic.get_status(self.env, fresh=True)
        color = {"licensed": "#198754", "trial": "#fd7e14", "expired": "#dc3545"}[st["state"]]
        html = Markup('<div style="font-size:16px;font-weight:600;color:%s">%s</div>') % (
            color, st["message"])
        if st.get("company"):
            html += Markup('<div class="text-muted">Владелец лицензии: %s</div>') % st["company"]
        for rec in self:
            rec.status_html = html
            rec.machine_code = st["machine"]

    def action_activate(self):
        self.ensure_one()
        key = "".join((self.license_key or "").split())
        if not key and self.license_file:
            import base64
            try:
                text = base64.b64decode(self.license_file).decode("utf-8-sig")
            except Exception:
                raise UserError(self.env._("Не удалось прочитать файл лицензии."))
            # в файле могут быть строки-пояснения; ключ — самая длинная строка с точкой
            lines = [l.strip() for l in text.splitlines() if "." in l and " " not in l.strip()]
            key = max(lines, key=len) if lines else ""
        if not key:
            raise UserError(self.env._("Вставьте ключ или выберите файл лицензии, полученный от разработчика."))
        try:
            lic.decode_key(key)
        except ValueError as e:
            raise UserError(str(e))
        lic.touch(self.env)
        self.env["ir.config_parameter"].sudo().set_param("construction_license.key", key)
        lic.clear_cache(self.env)
        return {"type": "ir.actions.client", "tag": "reload"}
