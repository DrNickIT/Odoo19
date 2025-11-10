# -*- coding: utf-8 -*-
from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_is_paid_out = fields.Boolean(
        string="Uitbetaald aan Consignant",
        default=False,
        copy=False,  # Zorg ervoor dat dit niet gekopieerd wordt bij dupliceren
        help="Vink dit aan als de commissie voor deze lijn is uitbetaald aan de leverancier."
    )
