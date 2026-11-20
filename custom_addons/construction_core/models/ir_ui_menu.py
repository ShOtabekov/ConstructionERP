from odoo import api, models


class IrUiMenu(models.Model):
    """Для обычных пользователей (не администраторов) в меню приложений
    остаётся только «Строительная ERP». Администратор видит всё."""

    _inherit = "ir.ui.menu"

    @api.model
    def _construction_hidden_roots(self):
        if self.env.su or self.env.user.has_group("base.group_system"):
            return []
        root = self.env.ref("construction_core.menu_construction_root", raise_if_not_found=False)
        if not root:
            return []
        return self.sudo().search([("parent_id", "=", False), ("id", "!=", root.id)]).ids

    def _load_menus_blacklist(self):
        return list(super()._load_menus_blacklist()) + self._construction_hidden_roots()

    @api.model
    def get_user_roots(self):
        roots = super().get_user_roots()
        hidden = set(self._construction_hidden_roots())
        return roots.filtered(lambda m: m.id not in hidden) if hidden else roots
