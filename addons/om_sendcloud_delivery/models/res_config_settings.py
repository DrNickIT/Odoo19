from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # We linken deze velden direct aan de velden op het bedrijf (res.company)
    # readonly=False is nodig zodat je ze ook kunt opslaan vanuit de settings
    sendcloud_public_key = fields.Char(
        related='company_id.sendcloud_public_key',
        readonly=False,
        string="Sendcloud Public Key (Community)"
    )
    sendcloud_secret_key = fields.Char(
        related='company_id.sendcloud_secret_key',
        readonly=False,
        string="Sendcloud Secret Key (Community)"
    )
