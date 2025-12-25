from odoo import models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def create(self, vals_list):
        res = super().create(vals_list)
        # Nieuwe voorraad? Update het product!
        res.product_id.product_tmpl_id._update_shop_availability()
        return res

    def write(self, vals):
        res = super().write(vals)
        # Voorraad gewijzigd? Update het product!
        if 'quantity' in vals or 'location_id' in vals:
            self.mapped('product_id.product_tmpl_id')._update_shop_availability()
        return res

    def unlink(self):
        products = self.mapped('product_id.product_tmpl_id')
        res = super().unlink()
        products._update_shop_availability()
        return res

class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        res = super().write(vals)
        # Reservering gewijzigd (iemand bestelt iets)? Update het product!
        if 'state' in vals or 'product_uom_qty' in vals:
            self.mapped('product_id.product_tmpl_id')._update_shop_availability()
        return res