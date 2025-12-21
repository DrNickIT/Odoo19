# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _signup_create_user(self, values):
        """
        Veilige registratie flow:
        1. Zet e-mail om naar kleine letters (normalisatie).
        2. Check of er al een USER is met dit mailadres (blokkeer hack-poging op Admin).
        3. Als er enkel een PARTNER is (zonder user), koppel die dan.
           (Veiligheid: Odoo vereist e-mailverificatie voor login, dus data blijft veilig).
        """

        # 1. Normalisatie: Alles naar kleine letters
        if values.get('login'):
            values['login'] = values['login'].lower()
        if values.get('email'):
            values['email'] = values['email'].lower()

        login = values.get('login')

        # 2. Security Check: Is dit mailadres al in gebruik door een ANDERE user?
        # (bv. Admin heeft email 'info@...', hacker probeert te registreren met 'info@...')
        if login:
            # We zoeken breed op email, niet op loginnaam
            existing_user = self.env['res.users'].sudo().search([
                ('partner_id.email', '=ilike', login)
            ], limit=1)

            if existing_user:
                # Blokkeer hard. Geen discussie.
                raise UserError(_("Er bestaat reeds een account met dit e-mailadres. Probeer in te loggen."))

        # 3. Slimme Koppeling (Het 'gemak' stukje)
        # Als er nog geen partner_id is meegegeven...
        if login and not values.get('partner_id'):
            # Zoek een bestaande partner.
            # CRUCIAAL: We checken ('user_ids', '=', False).
            # We koppelen dus ALLEEN als die partner nog 'vrij' is.
            existing_partner = self.env['res.partner'].sudo().search([
                ('email', '=ilike', login),
                ('user_ids', '=', False)
            ], limit=1)

            if existing_partner:
                _logger.info(f"Signup: Bestaande (vrije) partner gevonden voor {login} (ID: {existing_partner.id}). Koppelen.")
                values['partner_id'] = existing_partner.id

        return super(ResUsers, self)._signup_create_user(values)