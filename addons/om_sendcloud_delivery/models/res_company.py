from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    is_sendcloud_enabled = fields.Boolean(string="Sendcloud Connector (Community)")
    sendcloud_public_key = fields.Char(string="Sendcloud Public Key")
    sendcloud_secret_key = fields.Char(string="Sendcloud Secret Key")