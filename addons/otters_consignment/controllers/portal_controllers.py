# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
import logging

_logger = logging.getLogger(__name__)

class ConsignmentPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        """ Voegt een teller toe voor het aantal inzendingen op de /my/home pagina. """
        values = super(ConsignmentPortal, self)._prepare_portal_layout_values()

        partner = request.env.user.partner_id
        # Zoek submissions op basis van het e-mailadres voor consistente filtering
        submission_count = request.env['otters.consignment.submission'].sudo().search_count([
            ('supplier_id.email', '=ilike', partner.email)
        ])
        values['consignment_count'] = submission_count

        return values

    @http.route(['/my/consignments', '/my/consignments/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_consignments(self, page=1, **kw):
        """ Toont de lijst van alle inzendingen. """

        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        # Zoek met sudo om te garanderen dat de ACL's van de Portal-gebruiker de telling niet blokkeren
        Submission = request.env['otters.consignment.submission'].sudo()

        domain = [('supplier_id.email', '=ilike', partner.email)]

        pager_values = portal_pager(
            url="/my/consignments",
            total=values['consignment_count'],
            page=page,
            step=self._items_per_page
        )

        submissions = Submission.search(domain, limit=self._items_per_page, offset=pager_values['offset'])

        values.update({
            'submissions': submissions,
            'page_name': 'consignment',
            'default_url': '/my/consignments',
            'pager': pager_values,
        })
        return request.render("otters_consignment.portal_my_consignments", values)


    def _get_submission_check_access(self, submission_id):
        """ Controleert of de ingelogde gebruiker toegang heeft tot dit record op basis van e-mail. """
        # Gebruik .browse(id).sudo() om het record op te halen buiten ACL-beperkingen
        submission = request.env['otters.consignment.submission'].browse(submission_id).sudo()
        partner = request.env.user.partner_id

        # Verbeterde toegangscontrole via e-mailadres
        if not submission or submission.supplier_id.email.lower() != partner.email.lower():
            raise request.exceptions.AccessError('U hebt geen toegang tot deze inzending.')

        return submission

    @http.route(['/my/consignments/<int:submission_id>'], type='http', auth="user", website=True)
    def portal_submission_page(self, submission_id, **kw):
        """ Toont de details van één specifieke inzending. """
        try:
            submission = self._get_submission_check_access(submission_id)
        except request.exceptions.AccessError:
            return request.render("website.403") # Geen toegang

        # --- LOGICA VOOR VERKOCHTE VS. IN VOORRAAD ---
        products_sold = submission._get_sold_products()
        products_in_stock = submission.product_ids - products_sold

        # --- NIEUWE LOGICA VOOR VERKOOPGEGEVENS (PRIJS & COMMISSIE) ---
        # 1. Haal de rapportlijnen op voor de verkochte producten in deze inzending
        report_lines = request.env['otters.consignment.report'].sudo().search([
            ('supplier_id', '=', submission.supplier_id.id),
            ('product_id', 'in', products_sold.ids),
        ])

        # 2. Aggregeer de verkoopgegevens per product (nodig als een product meerdere keren verkocht is)
        product_report_map = {}
        for line in report_lines:
            product_id = line.product_id.id
            if product_id not in product_report_map:
                product_report_map[product_id] = {
                    'total_sold_price': 0.0,
                    'total_commission': 0.0,
                    'qty_sold': 0,
                }
            # De rapportlijn bevat de subtotalen van de SO line, deze tellen we op
            product_report_map[product_id]['total_sold_price'] += line.price_subtotal
            product_report_map[product_id]['total_commission'] += line.commission_amount
            product_report_map[product_id]['qty_sold'] += line.qty_sold


        products_sold_data = []
        total_payout = 0.0

        # 3. Koppel de data aan de verkochte producten
        for product in products_sold:
            report_data = product_report_map.get(product.id, {})

            sold_price_total = report_data.get('total_sold_price', 0.0)
            commission_total = report_data.get('total_commission', 0.0)
            qty_sold = report_data.get('qty_sold', 0)

            products_sold_data.append({
                'product': product,
                'qty_sold': qty_sold,
                'total_sold_price': sold_price_total,
                'total_commission': commission_total,
            })
            total_payout += commission_total # Bereken de totale uitbetaling

        values = self._prepare_portal_layout_values()
        values.update({
            'submission': submission,
            'products_in_stock': products_in_stock,
            'products_sold_data': products_sold_data, # NIEUW: Bevat prijs en commissie
            'total_payout_for_submission': total_payout,
            'page_name': 'submission',
            'pager': False,
            'currency': request.env.company.currency_id, # Valuta van het bedrijf
        })
        return request.render("otters_consignment.portal_consignment_submission", values)
