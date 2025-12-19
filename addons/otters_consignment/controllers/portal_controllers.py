# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, MissingError
import logging

_logger = logging.getLogger(__name__)

class ConsignmentPortal(CustomerPortal):
    _items_per_page = 20

    def _prepare_portal_layout_values(self):
        values = super(ConsignmentPortal, self)._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        submission_count = request.env['otters.consignment.submission'].sudo().search_count([
            ('supplier_id.email', '=ilike', partner.email)
        ])
        values['consignment_count'] = submission_count
        return values

    @http.route(['/my/consignments', '/my/consignments/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_consignments_list(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        Submission = request.env['otters.consignment.submission']

        domain = [('supplier_id.email', '=ilike', partner.email)]

        searchbar_sortings = {'date': {'label': 'Datum', 'order': 'submission_date desc, id desc'}}
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

    @http.route(['/my/consignments/<int:submission_id>'], type='http', auth="user", website=True)
    def portal_my_consignments_detail(self, submission_id, access_token=None, **kw):
        try:
            submission_sudo = self._get_submission_check_access(submission_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # 1. HAAL ALLE VERKOOP DATA OP (Live uit sales)
        all_sales_data = submission_sudo._get_portal_sold_data()

        # Splitsen in Betaald en Nog Niet Betaald
        aggregated_paid = [line for line in all_sales_data if line['is_paid']]
        aggregated_unpaid = [line for line in all_sales_data if not line['is_paid']]

        # 2. IN VOORRAAD
        # De makkelijkste manier: Alles met stock > 0 en zonder 'reden van verwijdering'
        stock_products = request.env['product.template'].sudo().search([
            ('submission_id', '=', submission_id),
            ('qty_available', '>', 0),       # Dit is de gouden standaard voor "In Stock"
            ('x_unsold_reason', '=', False), # Niet verwijderd/afgekeurd
            ('active', '=', True)
        ])

        # 3. UIT COLLECTIE (Verwijderd/Geretourneerd/Geschonken)
        removed_products = request.env['product.template'].sudo().search([
            ('submission_id', '=', submission_id),
            ('x_unsold_reason', '!=', False), # Wel een reden
            ('active', '=', True)
        ])

        # Bereken totalen voor de samenvatting bovenaan de pagina
        total_payout_paid = sum(item['payout'] for item in aggregated_paid)
        total_payout_unpaid = sum(item['payout'] for item in aggregated_unpaid)
        total_payout_stock = sum(p.list_price * submission_sudo.payout_percentage for p in stock_products)

        values = {
            'submission': submission_sudo,
            'page_name': 'consignment_submission',
            'access_token': access_token,

            # De 4 lijsten:
            'aggregated_paid': aggregated_paid,     # Historie
            'aggregated_unpaid': aggregated_unpaid, # Nog tegoed
            'stock_products': stock_products,       # Nog te koop
            'removed_products': removed_products,   # Weg

            # De totalen:
            'total_payout_paid': total_payout_paid,
            'total_payout_unpaid': total_payout_unpaid,
            'total_payout_stock': total_payout_stock,
        }

        return request.render("otters_consignment.portal_consignment_submission", values)

    def _get_submission_check_access(self, submission_id):
        submission = request.env['otters.consignment.submission'].browse(submission_id)
        if not submission.exists():
            raise MissingError("Deze inzending bestaat niet.")

        partner = request.env.user.partner_id
        if submission.sudo().supplier_id.email != partner.email:
            raise AccessError("Je hebt geen toegang tot deze inzending.")

        return submission.sudo()