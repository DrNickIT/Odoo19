# -*- coding: utf-8 -*-
from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # We koppelen dit veld direct aan de systeemparameter
    otters_consignment_closed = fields.Boolean(
        string="Inzendingen tijdelijk stoppen",
        config_parameter='otters_consignment.is_closed',
        help="Vink dit aan om het formulier op de website te blokkeren (bv. bij vakantie of vol magazijn)."
    )

    otters_consignment_closed_message = fields.Char(
        string="Melding op website",
        config_parameter='otters_consignment.closed_message',
        default="Wegens grote drukte nemen we momenteel even geen nieuwe verzendzakken aan. Probeer het later opnieuw!",
        translate=True
    )