"""Recompute apartment rates from their project after the migration."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["construction.project"].with_context(active_test=False).search(
        []
    ).modified(["usd_tjs_rate"])
    env.flush_all()
