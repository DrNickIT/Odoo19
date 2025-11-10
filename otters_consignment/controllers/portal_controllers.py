# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.osv import expression

# --- FIX 1: Imports toegevoegd voor AccessError en MissingError ---
from odoo.exceptions import AccessError, MissingError

import logging
_logger = logging.getLogger(__name__)

class ConsignmentPortal(CustomerPortal):

    # Dit voegt de teller toe aan *alle* portal paginas (voor o.a. broodkruimels)
    def _prepare_portal_layout_values(self):
        values = super(ConsignmentPortal, self)._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        submission_count = request.env['otters.consignment.submission'].sudo().search_count([
            ('supplier_id.email', '=ilike', partner.email)
        ])
        values['consignment_count'] = submission_count
        return values

    # --- FIX 3: Functienaam gewijzigd naar _list ---
    # Dit is de LIJST-pagina (/my/consignments)
    @http.route(['/my/consignments', '/my/consignments/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_consignments_list(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        Submission = request.env['otters.consignment.submission']

        domain = [('supplier_id.email', '=ilike', partner.email)]

        searchbar_sortings = {'date': {'label': 'Datum', 'order': 'submission_date desc'}}
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']

        pager_values = request.website.pager(
            url="/my/consignments",
            total=Submission.sudo().search_count(domain),
            page=page,
            step=self._items_per_page
        )
        submissions = Submission.sudo().search(domain, order=order, limit=self._items_per_page, offset=pager_values['offset'])

        values.update({
            'submissions': submissions,
            'page_name': 'consignment_list',
            'pager': pager_values,
            'default_url': '/my/consignments',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        return request.render("otters_consignment.portal_my_consignments", values)

    # --- FIX 3: Functienaam gewijzigd naar _detail ---
    # Dit is de DETAIL-pagina (/my/consignments/<id>)
    @http.route(['/my/consignments/<int:submission_id>'], type='http', auth="user", website=True)
    def portal_my_consignments_detail(self, submission_id, access_token=None, **kw):
        try:
            # --- FIX 2: 'access_token' verwijderd uit de aanroep ---
            submission_sudo = self._get_submission_check_access(submission_id)
        except (AccessError, MissingError): # Werkt nu dankzij Fix 1
            return request.redirect('/my')

        report_model = request.env['otters.consignment.report']

        all_sold_products = submission_sudo._get_sold_products()
        stock_products = request.env['product.template'].sudo().search([
            ('submission_id', '=', submission_id),
            ('id', 'not in', all_sold_products.ids),
            ('active', '=', True)
        ])

        all_report_lines = report_model.sudo().search([('submission_id', '=', submission_id)])

        def aggregate_report_lines(lines):
            aggregated_data = {}
            for line in lines:
                product = line.product_id
                if product not in aggregated_data:
                    aggregated_data[product] = {'name': product.name, 'price_sold': 0, 'payout': 0, 'qty': 0}

                aggregated_data[product]['price_sold'] += line.price_subtotal
                aggregated_data[product]['payout'] += line.commission_amount
                aggregated_data[product]['qty'] += line.qty_sold
            return aggregated_data.values()

        unpaid_lines = all_report_lines.filtered(lambda r: not r.x_is_paid_out)
        paid_lines = all_report_lines.filtered(lambda r: r.x_is_paid_out)

        aggregated_unpaid = aggregate_report_lines(unpaid_lines)
        aggregated_paid = aggregate_report_lines(paid_lines)

        total_payout_unpaid = sum(l.commission_amount for l in unpaid_lines)
        # (Ik heb je typo hier ook gecorrigeerd: pMayout -> payout)
        total_payout_paid = sum(l.commission_amount for l in paid_lines)

        values = {
            'submission': submission_sudo,
            'stock_products': stock_products,
            'aggregated_unpaid': aggregated_unpaid,
            'aggregated_paid': aggregated_paid,
            'total_payout_unpaid': total_payout_unpaid,
            'total_payout_paid': total_payout_paid,
            'page_name': 'consignment_submission',
            'access_token': access_token,
        }

        return request.render("otters_consignment.portal_consignment_submission", values)

    # Dit is de helper-functie voor toegangscontrole
    def _get_submission_check_access(self, submission_id):
        submission = request.env['otters.consignment.submission'].browse([submission_id])
        if not submission.exists():
            raise MissingError("Deze inzending bestaat niet.")

        partner = request.env.user.partner_id
        if submission.sudo().supplier_id.email != partner.email:
            raise AccessError("Je hebt geen toegang tot deze inzending.")

        return submission.sudo()
