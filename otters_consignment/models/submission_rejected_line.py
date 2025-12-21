# -*- coding: utf-8 -*-
from odoo import models, fields

class ConsignmentRejectedLine(models.Model):
    _name = 'otters.consignment.rejected.line'
    _description = 'Lijst met geweigerde kledingstukken'

    submission_id = fields.Many2one('otters.consignment.submission', string="Inzending", ondelete='cascade')

    # Gewoon tekst, geen link naar een product
    product_name = fields.Char(string="Omschrijving", required=True, help="Bv. Blauwe trui H&M")

    reason = fields.Selection([
        ('stain', 'Vlekken'),
        ('hole', 'Gaatjes / Slijtage'),
        ('brand', 'Merk niet geaccepteerd'),
        ('outdated', 'Te oud / Uit de mode'),
        ('season', 'Verkeerd seizoen'),
        ('other', 'Andere')
    ], string="Reden", required=True, default='stain')

    note = fields.Char(string="Extra Info")