# -*- coding: utf-8 -*-
from odoo import models, fields, api

class BulkRemoveWizard(models.TransientModel):
    _name = 'otters.consignment.bulk.remove.wizard'
    _description = 'Wizard om volledige zak uit collectie te halen'

    submission_id = fields.Many2one('otters.consignment.submission', string="Inzending", required=True)

    # We nemen dezelfde opties over als op het product
    reason = fields.Selection([
        ('charity', 'Geschonken aan goed doel'),
        ('returned', 'Teruggestuurd naar klant'),
        ('lost', 'Verloren / Beschadigd'),
        ('other', 'Andere')
    ], string="Reden", required=True)

    @api.model
    def default_get(self, fields):
        res = super(BulkRemoveWizard, self).default_get(fields)
        # Pak de actieve ID (de inzending waar Marleen op staat)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['submission_id'] = active_id
        return res

    def action_apply_bulk_remove(self):
        self.ensure_one()
        # 1. Zoek alle producten van deze inzending
        # 2. Filter: Alleen die nog 'actief' zijn en nog geen reden hebben (om dubbel werk te voorkomen)
        # 3. Filter: Alleen die nog VOORRAAD hebben (verkochte items blijven verkocht!)

        products_to_remove = self.submission_id.product_ids.filtered(
            lambda p: not p.x_unsold_reason and p.qty_available > 0
        )

        # 4. Schrijf de reden weg.
        # OPMERKING: Doordat we de write() methode in product_template.py hebben aangepast,
        # zal dit AUTOMATISCH ook de stock op 0 zetten en is_published op False zetten.
        products_to_remove.write({
            'x_unsold_reason': self.reason
        })

        # Logboek berichtje
        self.submission_id.message_post(
            body=f"<b>Bulk actie:</b> {len(products_to_remove)} producten uit collectie gehaald. Reden: {dict(self._fields['reason'].selection).get(self.reason)}"
        )

        return {'type': 'ir.actions.act_window_close'}