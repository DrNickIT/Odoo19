# -*- coding: utf-8 -*-
from odoo import fields, models, api # <--- API toevoegen!

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_is_paid_out = fields.Boolean(
        string="Uitbetaald aan Consignant",
        default=False,
        copy=False,
        help="Vink dit aan als de commissie voor deze lijn is uitbetaald aan de leverancier."
    )
    x_payout_date = fields.Date(string="Uitbetaald op")

    x_fixed_commission = fields.Monetary(string="Vastgelegde Commissie", currency_field='currency_id', copy=False)

    # NIEUW VELD:
    x_computed_percentage = fields.Float(
        string="Percentage",
        compute='_compute_commission',
        digits=(16, 2)
    )

    x_old_id = fields.Char(string="Oud Bestelregel ID", index=True, readonly=True)

    x_computed_commission = fields.Monetary(
        string="Commissie",
        compute='_compute_commission',
        currency_field='currency_id'
    )

    @api.depends('x_fixed_commission', 'x_is_paid_out', 'price_total', 'product_id.submission_id.payout_percentage')
    def _compute_commission(self):
        for line in self:
            submission = line.product_id.submission_id

            # 1. Percentage ophalen
            if submission:
                line.x_computed_percentage = submission.payout_percentage
            else:
                line.x_computed_percentage = 0.0

            # 2. Bedrag berekenen (zoals hiervoor)
            if line.x_is_paid_out:
                line.x_computed_commission = line.x_fixed_commission
            else:
                if submission:
                    line.x_computed_commission = line.price_total * submission.payout_percentage
                else:
                    line.x_computed_commission = 0.0