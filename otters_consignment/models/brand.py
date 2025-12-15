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

    product_ids = fields.One2many('product.template', 'brand_id', string="Producten")

    product_count = fields.Integer(compute='_compute_product_count', string="Aantal Stuks", store=False)

    def _compute_product_count(self):
        for record in self:
            # We tellen alleen de producten die:
            # 1. Gepubliceerd zijn op de website
            # 2. Vrij zijn voor verkoop (Virtuele stock > 0)
            available_products = record.product_ids.filtered(
                lambda p: p.is_published and p.virtual_available > 0
            )
            record.product_count = len(available_products)

    @api.model_create_multi
    def create(self, vals_list):
        """ Als we een merk aanmaken, maak dan ook direct de Kenmerk-waarde aan. """
        brands = super().create(vals_list)
        for brand in brands:
            brand._ensure_attribute_value()
        return brands

    def write(self, vals):
        """ Als we de naam wijzigen, update (of maak) de Kenmerk-waarde. """
        res = super().write(vals)
        if 'name' in vals:
            for brand in self:
                brand._ensure_attribute_value()
        return res

    def _ensure_attribute_value(self):
        """ Hulpfunctie: Zorg dat dit merk bestaat als Attribuutwaarde """
        # 1. Zoek het attribuut 'Merk'
        brand_attribute = self.env['product.attribute'].search([('name', '=ilike', 'Merk')], limit=1)
        if not brand_attribute:
            # Bestaat 'Merk' nog niet? Maak het dan nu aan
            brand_attribute = self.env['product.attribute'].create({
                'name': 'Merk',
                'create_variant': 'no_variant',
                'display_type': 'radio'
            })

        # 2. Zoek of de waarde al bestaat
        val_name = self.name
        existing_val = self.env['product.attribute.value'].search([
            ('attribute_id', '=', brand_attribute.id),
            ('name', '=ilike', val_name)
        ], limit=1)

        # 3. Bestaat niet? Maak aan!
        if not existing_val:
            self.env['product.attribute.value'].create({
                'name': val_name,
                'attribute_id': brand_attribute.id,
                'sequence': 10
            })