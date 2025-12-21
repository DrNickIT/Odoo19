from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sendcloud_service_point_id = fields.Char(string="Sendcloud Servicepunt ID")
    sendcloud_service_point_name = fields.Char(string="Gekozen Servicepunt")
