# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ConsignmentLabel(models.Model):
    _name = 'otters.consignment.label'
    _description = 'Sendcloud Label'

    submission_id = fields.Many2one('otters.consignment.submission', string="Inzending", required=True, ondelete='cascade')
    label_url = fields.Char(string="Label URL", required=True, default="Not created")
    tracking_number = fields.Char(string="Tracking Nummer")

    def action_open_url(self):
        """ Hulpknopje om de URL te openen vanuit de lijst """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.label_url,
            'target': 'new',
        }