# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    # Dit veld onthoudt welk 'Type' (attribuutwaarde) bij deze categorie hoort
    x_linked_type_value_id = fields.Many2one(
        'product.attribute.value',
        string="Automatisch Type Kenmerk",
        domain="[('attribute_id.name', '=', 'Type')]"
    )