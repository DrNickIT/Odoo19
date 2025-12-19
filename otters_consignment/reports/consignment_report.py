# -*- coding: utf-8 -*-
from odoo import models, fields, tools, _
from odoo.exceptions import UserError

class ConsignmentReport(models.Model):
    _name = "otters.consignment.report"
    _description = "Consignatie Verkoop Rapport"
    _auto = False
    _order = 'date desc'

    submission_id = fields.Many2one('otters.consignment.submission', string="Inzending", readonly=True)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", readonly=True)
    product_id = fields.Many2one('product.template', string="Product", readonly=True)
    order_id = fields.Many2one('sale.order', string="Order", readonly=True)
    order_line_id = fields.Many2one('sale.order.line', string="Verkooporder Lijn", readonly=True)
    date = fields.Datetime(string="Verkoopdatum", readonly=True)
    price_subtotal = fields.Float(string="Netto Verkoopprijs", readonly=True)
    price_total = fields.Float(string="Bruto Verkoopprijs (Incl. BTW)", readonly=True)
    qty_sold = fields.Float(string="Aantal Verkocht", readonly=True)
    payout_method = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Uitbetaalmethode", readonly=True)
    commission_amount = fields.Float(string="Commissiebedrag", readonly=True)
    x_is_paid_out = fields.Boolean(string="Uitbetaald", readonly=True)
    x_payout_date = fields.Date(string="Uitbetaald op", readonly=True)
    x_old_id = fields.Char(string="Oude Id", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sol.id AS id,
                    sub.id AS submission_id,
                    sol.id AS order_line_id,
                    sol.x_is_paid_out AS x_is_paid_out,
                    sol.x_payout_date AS x_payout_date,
                    so.id AS order_id,
                    pt.id AS product_id,
                    pt.x_old_id as x_old_id,
                    sub.supplier_id AS supplier_id,
                    so.date_order AS date,
                    sol.price_subtotal AS price_subtotal,
                    sol.price_total AS price_total,
                    sol.product_uom_qty AS qty_sold, -- AANGEPAST: Kijk naar besteld aantal (product_uom_qty) ipv gefactureerd
                    sub.payout_method AS payout_method,
                    
                    COALESCE(sol.x_fixed_commission, (sub.payout_percentage * sol.price_total)) AS commission_amount
                    
                FROM sale_order_line sol
                JOIN sale_order so ON sol.order_id = so.id
                JOIN product_product pp ON sol.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                JOIN otters_consignment_submission sub ON pt.submission_id = sub.id
                JOIN res_partner rp ON sub.supplier_id = rp.id
                
                WHERE
                    pt.submission_id IS NOT NULL
                    AND so.state IN ('sale', 'done')
                    AND sol.product_uom_qty > 0 -- AANGEPAST: Kijk naar besteld aantal
            )
        """ % (self._table,))

    def action_mark_paid(self):
        """ Markeer geselecteerde regels als betaald en leg commissie vast. """
        for report_line in self:
            sol = report_line.order_line_id
            if not sol.x_is_paid_out:
                current_calc = report_line.commission_amount
                sol.write({
                    'x_is_paid_out': True,
                    'x_payout_date': fields.Date.context_today(self),
                    'x_fixed_commission': current_calc
                })

    def action_mark_unpaid(self):
        """ Reset geselecteerde regels naar onbetaald. """
        for report_line in self:
            sol = report_line.order_line_id
            sol.write({
                'x_is_paid_out': False,
                'x_payout_date': False,
                'x_fixed_commission': 0.0
            })