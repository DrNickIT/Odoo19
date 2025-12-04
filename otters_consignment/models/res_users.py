# -*- coding: utf-8 -*-
from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _signup_create_user(self, values):
        """
        Overschrijf de signup create methode.
        Als iemand zich registreert met e-mail X, en we hebben al een Partner met e-mail X
        (maar zonder user), koppel dan de nieuwe user aan die BESTAANDE partner.
        """
        login = values.get('login')

        # Als er nog geen partner_id is meegegeven in de waarden...
        if login and not values.get('partner_id'):
            # Zoek een bestaande partner op e-mail (hoofdletterongevoelig)
            # We filteren op partners die nog GEEN user hebben om conflicten te vermijden
            existing_partner = self.env['res.partner'].sudo().search([
                ('email', '=ilike', login),
                ('user_ids', '=', False) # Zorg dat deze partner nog niet gekoppeld is aan iemand anders
            ], limit=1)

            if existing_partner:
                _logger.info(f"Signup: Bestaande partner gevonden voor {login} (ID: {existing_partner.id}). Koppelen maar!")
                values['partner_id'] = existing_partner.id

                # Optioneel: Update de naam van de partner als de gebruiker een nieuwe naam invoert
                # if values.get('name'):
                #     existing_partner.write({'name': values['name']})

        return super(ResUsers, self)._signup_create_user(values)