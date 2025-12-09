# -*- coding: utf-8 -*-
from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_is_paid_out = fields.Boolean(
        string="Uitbetaald aan Consignant",
        default=False,
        copy=False,
        help="Vink dit aan als de commissie voor deze lijn is uitbetaald aan de leverancier."
    )

    x_fixed_commission = fields.Monetary(string="Vastgelegde Commissie", currency_field='currency_id', copy=False)

    # NIEUW: Om duplicaten te voorkomen bij herstarten van migratie
    x_old_id = fields.Char(string="Oud Bestelregel ID", index=True, readonly=True)