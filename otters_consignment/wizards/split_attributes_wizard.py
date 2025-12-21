# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SplitAttributesWizard(models.TransientModel):
    _name = 'otters.consignment.split.attributes.wizard'
    _description = 'Wizard: Splits Kenmerken met meerdere waarden'

    attribute_ids = fields.Many2many(
        'product.attribute',
        relation='otters_split_attr_rel',  # <--- HIER: Kortere tabelnaam opgeven
        string="Te splitsen kenmerken",
        required=True,
        help="Selecteer de kenmerken die je wilt splitsen (bv. Geslacht, Seizoen)."
    )

    process_all = fields.Boolean(
        string="Verwerk ALLE producten in database",
        default=False,
        help="Indien aangevinkt, wordt de hele database gecontroleerd. Anders enkel de geselecteerde producten."
    )

    def action_split(self):
        # ... (rest van de code blijft identiek)
        self.ensure_one()

        if self.process_all:
            products = self.env['product.template'].search([])
        else:
            active_ids = self.env.context.get('active_ids', [])
            if not active_ids:
                return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'Geen selectie', 'message': 'Selecteer producten of vink "Verwerk ALLE producten" aan.', 'type': 'warning'}}
            products = self.env['product.template'].browse(active_ids)

        total_products_fixed = 0
        target_attr_ids = self.attribute_ids.ids

        for product in products:
            # Zoek lijnen die horen bij de gekozen attributen EN meer dan 1 waarde hebben
            lines_to_split = product.attribute_line_ids.filtered(
                lambda l: l.attribute_id.id in target_attr_ids and len(l.value_ids) > 1
            )

            if not lines_to_split:
                continue

            for line in lines_to_split:
                attribute = line.attribute_id
                values = line.value_ids

                # A. Verwijder de oude gecombineerde regel
                line.unlink()

                # B. Maak nieuwe, enkele regels
                for val in values:
                    self.env['product.template.attribute.line'].create({
                        'product_tmpl_id': product.id,
                        'attribute_id': attribute.id,
                        'value_ids': [(6, 0, [val.id])]
                    })

            total_products_fixed += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Klaar!',
                'message': f'{total_products_fixed} producten zijn succesvol gesplitst.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }