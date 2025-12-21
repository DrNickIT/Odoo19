# -*- coding: utf-8 -*-
from odoo import fields, models, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_is_paid_out = fields.Boolean(
        string="Uitbetaald aan Consignant",
        default=False,
        copy=False
    )
    x_payout_date = fields.Date(string="Uitbetaald op")

    x_old_id = fields.Char(string="Oud Bestelregel ID", index=True, readonly=True)

    x_fixed_commission = fields.Monetary(string="Vastgelegde Commissie", currency_field='currency_id', copy=False)
    x_fixed_percentage = fields.Float(string="Vastgelegd Percentage", copy=False, digits=(16, 2))

    x_computed_percentage = fields.Float(
        string="Percentage",
        compute='_compute_commission',
        digits=(16, 2)
    )

    x_computed_commission = fields.Monetary(
        string="Commissie",
        compute='_compute_commission',
        currency_field='currency_id'
    )

    @api.depends('x_fixed_commission', 'x_fixed_percentage', 'x_is_paid_out', 'price_total', 'product_id.submission_id.payout_percentage')
    def _compute_commission(self):
        for line in self:
            submission = line.product_id.submission_id

            if line.x_is_paid_out:
                # REEDS BETAALD: Toon wat er in het geheugen zit
                # (Fallback naar live percentage als het een oude betaling is zonder fixed percentage)
                line.x_computed_percentage = line.x_fixed_percentage or (submission.payout_percentage if submission else 0.0)
                line.x_computed_commission = line.x_fixed_commission
            else:
                # NOG NIET BETAALD: Toon de live berekening
                if submission:
                    line.x_computed_percentage = submission.payout_percentage
                    line.x_computed_commission = line.price_total * submission.payout_percentage
                else:
                    line.x_computed_percentage = 0.0
                    line.x_computed_commission = 0.0