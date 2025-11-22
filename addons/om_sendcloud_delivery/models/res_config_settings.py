from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # De schakelaar (verbonden met het bedrijf)
    is_sendcloud_enabled = fields.Boolean(
        related='company_id.is_sendcloud_enabled',
        readonly=False,
        string="Sendcloud Connector (Community)"
    )

    sendcloud_public_key = fields.Char(
        related='company_id.sendcloud_public_key',
        readonly=False,
        string="Sendcloud Public Key"
    )
    sendcloud_secret_key = fields.Char(
        related='company_id.sendcloud_secret_key',
        readonly=False,
        string="Sendcloud Secret Key"
    )
