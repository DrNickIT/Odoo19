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

    otters_review_launch_date = fields.Datetime(
        string="Startdatum Review Mails",
        config_parameter='otters_consignment.review_launch_date',
        help="Bestellingen geplaatst ná deze datum/tijd krijgen na 5 dagen automatisch een review e-mail."
    )

    otters_review_delay_days = fields.Integer(
        string="Aantal dagen na bestelling",
        config_parameter='otters_consignment.review_delay_days',
        default=5,
        help="Na hoeveel dagen moet de review mail gestuurd worden? (Standaard is 5)"
    )