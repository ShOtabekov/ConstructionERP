import base64

from odoo import api, fields, models
from odoo.tools import file_open

RAHMONIYON_RENDERS = 14


class ConstructionProjectImage(models.Model):
    _name = "construction.project.image"
    _description = "Фото / визуализация проекта"
    _order = "sequence, id"

    name = fields.Char(string="Подпись")
    project_id = fields.Many2one("construction.project", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    image_1920 = fields.Image(string="Изображение", max_width=1920, max_height=1920, required=True)
    image_512 = fields.Image(related="image_1920", max_width=512, max_height=512, store=True)


class ConstructionProject(models.Model):
    _inherit = "construction.project"

    image_ids = fields.One2many("construction.project.image", "project_id", string="Фото и визуализации")
    image_count = fields.Integer(compute="_compute_image_count")

    def _compute_image_count(self):
        for project in self:
            project.image_count = len(project.image_ids)

    @api.model
    def _fill_rahmoniyon_renders(self):
        """3D-визуализации ЖК Rahmoniyon из PDF «Ландшафт» — только если фото ещё нет."""
        Image = self.env["construction.project.image"]
        for project in self.search([("name", "ilike", "rahmoniyon")]):
            if project.image_ids:
                continue
            for i in range(1, RAHMONIYON_RENDERS + 1):
                path = "construction_core/static/img/rahmoniyon/renders/render_%02d.jpg" % i
                with file_open(path, "rb") as f:
                    Image.create({
                        "project_id": project.id,
                        "sequence": i,
                        "name": "Визуализация %d" % i,
                        "image_1920": base64.b64encode(f.read()),
                    })
        return True

    @api.model
    def get_gallery(self, project_id=False):
        """Для шахматки: список фото проекта (или первого проекта с фото)."""
        domain = [("project_id", "=", project_id)] if project_id else []
        images = self.env["construction.project.image"].search(domain)
        if not project_id and images:
            images = images.filtered(lambda i: i.project_id == images[0].project_id)
        return [{"id": img.id, "name": img.name or "",
                 "url": "/web/image/construction.project.image/%d/image_1920" % img.id,
                 "thumb": "/web/image/construction.project.image/%d/image_512" % img.id}
                for img in images]
