# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _signup_create_user(self, values):
        # 1. Normalisatie: Alles naar kleine letters
        if values.get('login'):
            values['login'] = values['login'].lower()
        if values.get('email'):
            values['email'] = values['email'].lower()

        login = values.get('login')

        # 2. Extra Veiligheid: Check of dit e-mailadres al bestaat bij een user
        # (Odoo checkt standaard op login, maar wij checken extra streng op e-mail match)
        if login:
            existing_user = self.env['res.users'].sudo().search([
                ('partner_id.email', '=ilike', login)
            ], limit=1)

            if existing_user:
                raise UserError(_("Er bestaat reeds een account met dit e-mailadres. Probeer in te loggen."))

        # 3. Voer de standaard aanmaak uit (maakt nieuwe user + nieuwe partner)
        return super(ResUsers, self)._signup_create_user(values)