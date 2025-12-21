# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_payout_method = fields.Selection(
        [('cash', 'Cash'), ('coupon', 'Coupon')],
        string="Payout Method",
        copy=False,
        index=True,
        help="The preferred payout method for this contact."
    )

    x_cash_payout_percentage = fields.Float(
        string="Cash Payout %",
        help="The specific cash payout percentage for this partner. Overrides the system default."
    )

    x_coupon_payout_percentage = fields.Float(
        string="Coupon Payout %",
        help="The specific coupon payout percentage for this partner. Overrides the system default."
    )

    x_consignment_prefix = fields.Char(
        string="Consignment Prefix",
        copy=False,
        index=True,
        help="The unique prefix for this contact's consignment submissions."
    )

    x_old_id = fields.Char(string="Oud Klant ID", copy=False, readonly=True, help="ID uit de oude webshop", default="new")
