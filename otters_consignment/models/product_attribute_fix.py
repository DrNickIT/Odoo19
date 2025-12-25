from odoo import models, api

class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'

    @api.onchange('attribute_id')
    def _onchange_attribute_id_marleen_fix(self):
        if self.attribute_id:
            self.value_ids = False