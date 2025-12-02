# -*- coding: utf-8 -*-
from odoo import models, fields, api

class OttersBrand(models.Model):
    _name = 'otters.brand'
    _description = 'Kleding Merk'
    _inherit = ['website.seo.metadata', 'website.published.mixin']
    _order = 'name'

    name = fields.Char(string="Merknaam", required=True)
    description = fields.Html(string="Omschrijving")
    logo = fields.Image(string="Logo", max_width=512, max_height=512)

    # Koppeling naar producten
    product_ids = fields.One2many('product.template', 'brand_id', string="Producten")

    # Slimme teller
    product_count = fields.Integer(compute='_compute_product_count', string="Aantal Stuks")

    @api.depends('product_ids')
    def _compute_product_count(self):
        for record in self:
            record.product_count = len(record.product_ids)