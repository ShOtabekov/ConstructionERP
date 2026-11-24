import json
import logging

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import update_core as upd

_logger = logging.getLogger(__name__)
P = "construction_core.update_"


class ConstructionUpdate(models.AbstractModel):
    _name = "construction.update"
    _description = "Обновления Строительной ERP"

    @api.model
    def _check(self, raise_errors=False):
        ICP = self.env["ir.config_parameter"].sudo()
        cur = upd.current_version()
        if not cur:
            if raise_errors:
                raise UserError(self.env._("Обновления работают только в установленной программе."))
            return {}
        try:
            latest = upd.fetch_latest()
        except Exception as e:
            _logger.info("Проверка обновлений не удалась: %s", e)
            if raise_errors:
                raise UserError(self.env._("Не удалось проверить обновления. Проверьте интернет.\n%s") % e)
            return {}
        ICP.set_param(P + "latest", json.dumps(latest, ensure_ascii=False))
        ICP.set_param(P + "checked", fields.Datetime.to_string(fields.Datetime.now()))
        return latest

    @api.model
    def _cron_check(self):
        self._check()

    @api.model
    def get_info(self):
        """Для плашки в шапке: только администратору и только если есть новая версия."""
        if not self.env.user.has_group("base.group_system"):
            return {}
        cur = upd.current_version()
        raw = self.env["ir.config_parameter"].sudo().get_param(P + "latest")
        if not (cur and raw):
            return {}
        latest = json.loads(raw)
        if upd.vtuple(latest.get("version")) > upd.vtuple(cur):
            return {"current": cur, "available": latest.get("version")}
        return {}


class ConstructionUpdateWizard(models.TransientModel):
    _name = "construction.update.wizard"
    _description = "Обновление программы"

    info_html = fields.Html("Состояние", compute="_compute_info", sanitize=False)
    can_install = fields.Boolean(compute="_compute_info")
    package = fields.Binary("Файл обновления", attachment=False)
    package_name = fields.Char()

    def _compute_info(self):
        cur = upd.current_version()
        raw = self.env["ir.config_parameter"].sudo().get_param(P + "latest")
        latest = json.loads(raw) if raw else {}
        status = upd.last_status()
        html = Markup("")
        if not cur:
            html += Markup("<p>Режим разработки: обновления работают только в установленной программе.</p>")
            can = False
        else:
            html += Markup("<p>Установлена версия: <b>%s</b></p>") % cur
            newer = latest and upd.vtuple(latest.get("version")) > upd.vtuple(cur)
            can = bool(newer)
            if newer:
                html += Markup('<p style="color:#198754;font-size:16px"><b>Доступна версия %s</b> (%s)</p>') % (
                    latest.get("version"), latest.get("date", ""))
                if latest.get("notes"):
                    html += Markup('<div style="white-space:pre-line;border-left:3px solid #ccc;padding-left:8px">%s</div>') % latest["notes"]
            elif latest:
                html += Markup("<p>У вас последняя версия.</p>")
            if status:
                color = "#198754" if status.get("state") == "ok" else "#dc3545"
                html += Markup('<p style="color:%s">Последнее обновление (%s): %s</p>') % (
                    color, status.get("date", ""), status.get("message", ""))
        for rec in self:
            rec.info_html = html
            rec.can_install = can

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form",
                "target": "new", "name": self.env._("Обновление программы")}

    def action_check(self):
        self.env["construction.update"]._check(raise_errors=True)
        return self._reopen()

    def _install(self, path):
        try:
            meta = upd.verify_package(path)
        except ValueError as e:
            raise UserError(str(e))
        cur = upd.current_version()
        if upd.vtuple(meta["version"]) <= upd.vtuple(cur):
            raise UserError(self.env._("Версия %(new)s не новее установленной %(cur)s.",
                                       new=meta["version"], cur=cur))
        try:
            upd.start_install(path)
        except ValueError as e:
            raise UserError(str(e))
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": self.env._("Обновление началось"), "sticky": True, "type": "warning",
                       "message": self.env._(
                           "Сначала делается резервная копия, затем программа перезапустится. "
                           "Через 3–5 минут обновите страницу (F5).")},
        }

    def action_install_online(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(self.env._("Обновлять программу может только администратор."))
        raw = self.env["ir.config_parameter"].sudo().get_param(P + "latest")
        latest = json.loads(raw) if raw else {}
        if not latest.get("url"):
            raise UserError(self.env._("Сначала нажмите «Проверить обновления»."))
        try:
            path = upd.download(latest["url"], latest["version"])
        except Exception as e:
            raise UserError(self.env._("Не удалось скачать обновление: %s") % e)
        return self._install(path)

    def action_install_file(self):
        if not self.env.user.has_group("base.group_system"):
            raise UserError(self.env._("Обновлять программу может только администратор."))
        if not upd.app_root():
            raise UserError(self.env._("Обновления работают только в установленной программе."))
        if not self.package:
            raise UserError(self.env._("Выберите файл StroyERP-update-....zip"))
        import base64
        import os
        folder = os.path.join(upd.app_root(), "updates")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "uploaded-update.zip")
        with open(path, "wb") as f:
            f.write(base64.b64decode(self.package))
        return self._install(path)
