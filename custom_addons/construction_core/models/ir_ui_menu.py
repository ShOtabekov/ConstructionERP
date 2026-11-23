from odoo import api, models

from ..tools import license_core as lic


class IrUiMenu(models.Model):
    """Для обычных пользователей (не администраторов) в меню приложений
    остаётся только «Строительная ERP». Администратор видит всё.
    Без лицензии вместо «Строительной ERP» показывается только «Лицензия»."""

    _inherit = "ir.ui.menu"

    @api.model
    def _construction_hidden_roots(self):
        root = self.env.ref("construction_core.menu_construction_root", raise_if_not_found=False)
        lic_root = self.env.ref("construction_core.menu_license_root", raise_if_not_found=False)
        if not root:
            return []
        expired = lic.get_status(self.env)["state"] == "expired"
        hidden = []
        if expired:
            hidden.append(root.id)
        elif lic_root:
            hidden.append(lic_root.id)
        if not (self.env.su or self.env.user.has_group("base.group_system")):
            keep = [root.id] + ([lic_root.id] if lic_root else [])
            hidden += self.sudo().search([("parent_id", "=", False), ("id", "not in", keep)]).ids
        return hidden

    def _load_menus_blacklist(self):
        return list(super()._load_menus_blacklist()) + self._construction_hidden_roots()

    @api.model
    def get_user_roots(self):
        roots = super().get_user_roots()
        hidden = set(self._construction_hidden_roots())
        return roots.filtered(lambda m: m.id not in hidden) if hidden else roots
