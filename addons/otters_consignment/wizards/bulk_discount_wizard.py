# -*- coding: utf-8 -*-
from odoo import models, fields, api

class BulkDiscountWizard(models.TransientModel):
    _name = 'otters.consignment.bulk.discount.wizard'
    _description = 'Bulk Korting Toepassen'

    discount_percentage = fields.Integer(string="Korting (%)", required=True, default=20)
    discount_reason = fields.Char(string="Reden", required=True, default="Solden / Opruiming")

    def action_apply_bulk(self):
        """
        1. Haal geselecteerde inzendingen op.
        2. Schrijf het percentage en de reden weg op die inzendingen.
        3. Roep de bestaande rekenfunctie aan.
        """
        # Haal de ID's op van de regels die Marleen heeft aangevinkt
        active_ids = self.env.context.get('active_ids', [])
        submissions = self.env['otters.consignment.submission'].browse(active_ids)

        # Stap 1: Update de settings op de inzendingen
        submissions.write({
            'discount_percentage': self.discount_percentage,
            'discount_reason': self.discount_reason
        })

        # Stap 2: Trigger de herberekening per inzending
        for submission in submissions:
            # We hergebruiken jouw bestaande logica!
            # Die houdt al rekening met reeds verkochte items (virtual_available check)
            submission.action_apply_discount()

        return {'type': 'ir.actions.act_window_close'}