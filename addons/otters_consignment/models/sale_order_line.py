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

    def write(self, vals):
        """
        Als 'x_is_paid_out' op True wordt gezet (door Marleen via de actie),
        dan vergrendelen we de bijbehorende inzending.
        """
        # 1. Voer de wijziging eerst uit
        res = super(SaleOrderLine, self).write(vals)

        # 2. Check of er uitbetaald wordt
        if vals.get('x_is_paid_out'):
            # Zoek de unieke inzendingen die aan deze lijnen hangen
            # self kan hier bv. 50 geselecteerde regels zijn
            submissions = self.mapped('product_template_id.submission_id')

            if submissions:
                # Zet ze op slot (alleen degene die nog niet gelockt waren)
                submissions.filtered(lambda s: not s.x_is_locked).sudo().write({'x_is_locked': True})

        return res