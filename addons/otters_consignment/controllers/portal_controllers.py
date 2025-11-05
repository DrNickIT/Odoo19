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
    def portal_consignment_submission(self, submission_id, **kw):
        """ Toont de details van één inzending en de bijbehorende producten. """

        try:
            submission = self._get_submission_check_access(submission_id)
        except request.exceptions.AccessError:
            return request.render("website.403") # Geen toegang

        # --- LOGICA VOOR VERKOCHTE VS. IN VOORRAAD ---
        # Roept de methode uit submission.py aan om betrouwbaar verkochte producten te bepalen
        products_sold = submission._get_sold_products()
        # Alles in de inzending MINUS de verkochte producten
        products_in_stock = submission.product_ids - products_sold

        # Berekening van de totale uitbetaling (via de SQL-view otters.consignment.report)
        report_lines = request.env['otters.consignment.report'].sudo().search([
            ('supplier_id.email', '=ilike', submission.supplier_id.email)
        ])

        # Filter de rapportlijnen specifiek op producten van deze inzending
        submission_product_ids = submission.product_ids.ids
        total_payout = sum(line.commission_amount for line in report_lines if line.product_id.id in submission_product_ids)

        values = self._prepare_portal_layout_values()
        values.update({
            'submission': submission,
            'products_in_stock': products_in_stock,
            'products_sold': products_sold,
            'total_payout_for_submission': total_payout,
            'page_name': 'consignment_detail',
        })
        return request.render("otters_consignment.portal_consignment_submission", values)
