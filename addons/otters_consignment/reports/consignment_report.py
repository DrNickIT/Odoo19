# In otters_consignment/reports/consignment_report.py
# -*- coding: utf-8 -*-
from odoo import fields, models, tools

class ConsignmentReport(models.Model):
    _name = 'otters.consignment.report'
    _description = 'Consignment Verkoop Analyse'
    _auto = False # Dit betekent dat het een SQL view is

    supplier_id = fields.Many2one('res.partner', string='Leverancier', readonly=True)
    product_id = fields.Many2one('product.template', string='Product', readonly=True)
    order_id = fields.Many2one('sale.order', string='Verkooporder', readonly=True)
    price_subtotal = fields.Float(string='Netto Verkoopprijs', readonly=True)
    commission_amount = fields.Float(string='Commissie', readonly=True)
    qty_sold = fields.Float(string='Aantal Verkocht', readonly=True)
    date = fields.Datetime(string='Orderdatum', readonly=True)
    payout_method = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Methode", readonly=True)

    def _query(self):
        # Dit is de gecorrigeerde query
        return """
               SELECT
                   sol.id as id,
                   sub.supplier_id as supplier_id,
                   pt.id as product_id,
                   so.id as order_id,
                   so.date_order as date,
                sol.price_subtotal as price_subtotal,
                sol.product_uom_qty as qty_sold,
                sup.x_payout_method as payout_method,
                
                -- CASE statement om de juiste commissie te berekenen
                (CASE
                    WHEN sup.x_payout_method = 'cash' THEN (sol.price_subtotal * sup.x_cash_payout_percentage)
                    WHEN sup.x_payout_method = 'coupon' THEN (sol.price_subtotal * sup.x_coupon_payout_percentage)
                    ELSE 0
                END) as commission_amount

               FROM
                   sale_order_line sol
                   JOIN
                   sale_order so ON sol.order_id = so.id
                   JOIN
                   product_product pp ON sol.product_id = pp.id
                   JOIN
                   product_template pt ON pp.product_tmpl_id = pt.id
                   JOIN
                   otters_consignment_submission sub ON pt.submission_id = sub.id
                   JOIN
                   res_partner sup ON sub.supplier_id = sup.id
               WHERE
                   pt.submission_id IS NOT NULL
                 AND so.state IN ('sale', 'done') -- Alleen bevestigde verkopen \
               """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
            )
        """ % (self._table, self._query()))
