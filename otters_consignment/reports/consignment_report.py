# -*- coding: utf-8 -*-
from odoo import models, fields, tools

class ConsignmentReport(models.Model):
    _name = "otters.consignment.report"
    _description = "Consignatie Verkoop Rapport"
    _auto = False

    # De velden waren correct
    supplier_id = fields.Many2one('res.partner', string="Leverancier", readonly=True)
    product_id = fields.Many2one('product.template', string="Product", readonly=True)
    order_id = fields.Many2one('sale.order', string="Order", readonly=True)
    order_line_id = fields.Many2one('sale.order.line', string="Verkooporder Lijn", readonly=True)
    date = fields.Datetime(string="Verkoopdatum", readonly=True)
    price_subtotal = fields.Float(string="Netto Verkoopprijs", readonly=True)
    qty_sold = fields.Float(string="Aantal Verkocht", readonly=True)
    payout_method = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Uitbetaalmethode", readonly=True)
    commission_amount = fields.Float(string="Commissiebedrag", readonly=True)
    x_is_paid_out = fields.Boolean(string="Uitbetaald", readonly=True)

    def init(self):
        """
        DE SQL QUERY MET DE GECORRIGEERDE JOINS
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sol.id AS id,
                    sol.id AS order_line_id,
                    sol.x_is_paid_out AS x_is_paid_out,
                    so.id AS order_id,
                    pt.id AS product_id,  -- Dit is de product.template ID
                    sub.supplier_id AS supplier_id,
                    so.date_order AS date,
                    sol.price_subtotal AS price_subtotal,
                    sol.qty_invoiced AS qty_sold,
                    sub.payout_method AS payout_method,
                    
                    CASE
                        WHEN sub.payout_method = 'cash' THEN
                            sol.price_subtotal * (rp.x_cash_payout_percentage / 100.0)
                        WHEN sub.payout_method = 'coupon' THEN
                            sol.price_subtotal * (rp.x_coupon_payout_percentage / 100.0)
                        ELSE 0
                    END AS commission_amount
                    
                FROM sale_order_line sol
                JOIN sale_order so ON sol.order_id = so.id
                
                -- === HIER ZIT DE CORRECTIE ===
                -- We moeten van sale_order_line naar product.product
                JOIN product_product pp ON sol.product_id = pp.id
                -- En dan van product.product naar product.template
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                -- === EINDE CORRECTIE ===

                JOIN otters_consignment_submission sub ON pt.submission_id = sub.id
                JOIN res_partner rp ON sub.supplier_id = rp.id
                
                WHERE
                    pt.submission_id IS NOT NULL
                    AND so.state IN ('sale', 'done')
                    AND sol.qty_invoiced > 0
            )
        """ % (self._table,))
