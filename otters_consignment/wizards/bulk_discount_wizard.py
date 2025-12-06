# -*- coding: utf-8 -*-
from odoo import models, fields, api

class BulkDiscountWizard(models.TransientModel):
    _name = 'otters.consignment.bulk.discount.wizard'
    _description = 'Bulk Korting Toepassen'

    discount_percentage = fields.Integer(string="Korting (%)", required=True, default=20)
    discount_reason = fields.Char(string="Reden", required=True, default="Solden / Opruiming")

    class BulkDiscountWizard(models.TransientModel):
        _name = 'otters.consignment.bulk.discount.wizard'
    _description = 'Bulk Korting Toepassen'

    discount_percentage = fields.Integer(string="Korting (%)", required=True, default=20)
    discount_reason = fields.Char(string="Reden", required=True, default="Solden / Opruiming")

    def action_apply_bulk(self):
        """ Je bestaande functie (ongewijzigd) """
        active_ids = self.env.context.get('active_ids', [])
        submissions = self.env['otters.consignment.submission'].browse(active_ids)

        submissions.write({
            'discount_percentage': self.discount_percentage,
            'discount_reason': self.discount_reason
        })

        for submission in submissions:
            submission.action_apply_discount()

        return {'type': 'ir.actions.act_window_close'}

    def action_remove_bulk(self):
        active_ids = self.env.context.get('active_ids', [])
        submissions = self.env['otters.consignment.submission'].browse(active_ids)

        submissions.write({
            'discount_percentage': 0,
            'discount_reason': False
        })

        for submission in submissions:
            submission.action_apply_discount()

        return {'type': 'ir.actions.act_window_close'}