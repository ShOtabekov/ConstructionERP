"""Импорт уже заключённых договоров из Excel («Досье»).

Колонки (как в досье застройщика): №, Сана, Ному насаб, Силсила (серия и номер паспорта),
Аз тарафи ... дода шуд, Сана д/ш, Ҷои истиқомат, Блок, Этаж, Хуҷра, М. мур-ба, нарх, Миқдор.
Договор получает номер из колонки №, сумму и цену за м² — как в досье (площадь по договору).
Оплаты не заносятся. Строки с ошибками пропускаются и показываются списком.
"""
import base64
import datetime
import io
import re

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    parts = [p for p in re.split(r"[^\d]+", str(value or "")) if p]
    if len(parts) < 3:
        return None
    d, m, y = (int(x) for x in parts[:3])
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().strip(",").strip()


class ConstructionDossierImport(models.TransientModel):
    _name = "construction.dossier.import"
    _description = "Импорт договоров из досье (Excel)"

    project_id = fields.Many2one("construction.project", string="Проект", required=True,
                                 default=lambda self: self.env["construction.project"].search([], limit=1))
    file = fields.Binary("Файл Excel (.xlsx)", attachment=False)
    file_name = fields.Char()
    preview_html = fields.Html("Проверка", sanitize=False, readonly=True)
    ready_count = fields.Integer(readonly=True)
    done = fields.Boolean(readonly=True)

    # ------------------------------------------------------------------
    def _read_rows(self):
        if not self.file:
            raise UserError(self.env._("Выберите файл Excel."))
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(self.file)), data_only=True)
        except Exception as e:
            raise UserError(self.env._("Не удалось прочитать файл: %s") % e)
        ws = wb.worksheets[0]
        rows = []
        for idx, r in enumerate(ws.iter_rows(values_only=True), 1):
            r = list(r) + [None] * 13
            if not isinstance(r[0], (int, float)):
                continue
            rows.append((idx, r[:13]))
        return rows

    def _find_unit(self, block, floor, pos):
        Apt = self.env["construction.apartment"]
        letter = _clean(block).upper()
        buildings = self.env["construction.building"].search([("project_id", "=", self.project_id.id)])
        building = buildings.filtered(lambda b: (b.name or "").split()[-1:] == [letter])[:1]
        if not building:
            return None, "нет блока «%s»" % letter
        number = "%d%02d" % (int(floor), int(pos))
        apt = Apt.search([("building_id", "=", building.id), ("number", "=", number)], limit=1)
        if not apt:
            return None, "нет помещения %s в блоке %s" % (number, letter)
        return apt, None

    def _analyze(self):
        Contract = self.env["construction.contract"]
        result, seen = [], {}
        for line, r in self._read_rows():
            no, date, name, passport, issued_by, issued_date, residence, block, floor, pos, area, ppm, amount = r
            item = {"line": line, "no": str(int(no)), "name": _clean(name), "errors": [], "notes": []}
            item["date"] = _date(date)
            if not item["date"]:
                item["errors"].append("дата договора")
            if not item["name"]:
                item["errors"].append("нет ФИО")
            if not block or not floor or not pos:
                item["errors"].append("не указана квартира")
            else:
                apt, err = self._find_unit(block, floor, pos)
                if err:
                    item["errors"].append(err)
                else:
                    item["apt"] = apt
                    key = apt.id
                    if key in seen:
                        item["errors"].append("эта квартира уже в строке №%s" % seen[key])
                    seen[key] = item["no"]
                    if apt.state == "sold":
                        item["errors"].append("уже продана в системе")
                    try:
                        area = float(area or 0)
                        amount = float(amount or 0)
                        ppm = float(ppm or 0)
                    except (TypeError, ValueError):
                        area = amount = ppm = 0
                    if amount <= 0:
                        item["errors"].append("нет суммы")
                    elif area and ppm and abs(area * ppm - amount) > 1:
                        item["errors"].append("сумма ≠ площадь × цена")
                    if apt.unit_type == "shop":
                        item["shop_area"] = area
                    elif area and abs(area - apt.area_total) > 0.05:
                        if abs(area - apt.area_total) > 3:
                            item["errors"].append("площадь %s, а у этой квартиры %s м²" % (area, apt.area_total))
                        else:
                            item["notes"].append("площадь по договору %s м² (по плану %s)" % (area, apt.area_total))
                    if ppm > 2000:
                        item["errors"].append("цена %s за м² — проверьте" % ppm)
                    item.update(area=area, ppm=ppm, amount=amount)
            if Contract.sudo().search_count([("name", "=", item["no"])], limit=1):
                item["errors"].append("договор №%s уже есть" % item["no"])
            ser = _clean(passport).replace(" ", "")
            m = re.match(r"^([^\d]*)(\d+)$", ser)
            item["passport"] = {
                "passport_series": (m.group(1) if m else "") or False,
                "passport_number": (m.group(2) if m else ser) or False,
                "passport_issued_by": _clean(issued_by) or False,
                "passport_issue_date": _date(issued_date) or False,
                "residence": _clean(residence) or False,
            }
            result.append(item)
        return result

    def _render(self, items):
        ok = [i for i in items if not i["errors"]]
        bad = [i for i in items if i["errors"]]
        html = Markup('<p><b>Готово к импорту: %s</b> из %s. С ошибками (будут пропущены): %s.</p>') % (
            len(ok), len(items), len(bad))
        if bad:
            html += Markup('<table class="table table-sm table-bordered"><tr><th>№</th><th>Клиент</th><th>Ошибка</th></tr>')
            for i in bad:
                html += Markup('<tr class="table-danger"><td>%s</td><td>%s</td><td>%s</td></tr>') % (
                    i["no"], i["name"], "; ".join(i["errors"]))
            html += Markup("</table>")
        notes = [i for i in ok if i["notes"] or i.get("shop_area")]
        if notes:
            html += Markup('<p class="text-muted">Примечания:</p><ul class="text-muted">')
            for i in notes:
                text = "; ".join(i["notes"]) or "площадь магазина %s м²" % i["shop_area"]
                html += Markup("<li>№%s %s — %s</li>") % (i["no"], i["apt"].name, text)
            html += Markup("</ul>")
        return html, len(ok)

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new", "name": self.env._("Импорт договоров из досье")}

    def action_check(self):
        self.ensure_one()
        html, n = self._render(self._analyze())
        self.write({"preview_html": html, "ready_count": n, "done": False})
        return self._reopen()

    def _partner(self, item, cache):
        Partner = self.env["res.partner"]
        p = item["passport"]
        key = (p["passport_series"], p["passport_number"]) if p["passport_number"] else item["name"]
        if key in cache:
            return cache[key]
        partner = Partner.browse()
        if p["passport_number"]:
            partner = Partner.search([("passport_number", "=", p["passport_number"])], limit=1)
        if not partner:
            partner = Partner.search([("name", "=", item["name"])], limit=1)
        vals = {k: v for k, v in p.items() if v}
        if partner:
            partner.write({k: v for k, v in vals.items() if not partner[k]})
        else:
            partner = Partner.create(dict(vals, name=item["name"]))
        cache[key] = partner
        return partner

    def action_import(self):
        self.ensure_one()
        items = [i for i in self._analyze() if not i["errors"]]
        if not items:
            raise UserError(self.env._("Нет строк для импорта — нажмите «Проверить» и посмотрите ошибки."))
        Contract = self.env["construction.contract"]
        rate = self.project_id.usd_tjs_rate or 0.0
        cache, created = {}, Contract
        for item in items:
            apt = item["apt"]
            if item.get("shop_area") and abs(item["shop_area"] - apt.area_total) > 0.001:
                apt.sudo().write({"area_total": item["shop_area"]})
            partner = self._partner(item, cache)
            contract = Contract.create({
                "name": item["no"],
                "partner_id": partner.id,
                "apartment_id": apt.id,
                "contract_date": item["date"],
                "price_usd": item["amount"],
                "area_contract": item["area"] if item["notes"] and not item.get("shop_area") else 0.0,
                "exchange_rate": rate,
                "notes": "Перенесён из досье (строка %s). %s" % (item["line"], "; ".join(item["notes"])),
            })
            contract.action_confirm()
            contract.sudo().write({"list_price_usd": item["amount"]})
            created |= contract
        html, _n = self._render(self._analyze())
        self.write({
            "done": True, "ready_count": 0,
            "preview_html": Markup('<p class="text-success"><b>Перенесено договоров: %s.</b> '
                                   'Квартиры отмечены как проданные. Оплаты по ним внесите отдельно.</p>')
                            % len(created) + html,
        })
        return self._reopen()
