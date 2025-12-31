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

        # --- NIEUW: Haal systeem percentages op voor de weergave in de edit-modal ---
        ICP = request.env['ir.config_parameter'].sudo()
        cash_perc = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3')) * 100
        coupon_perc = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5')) * 100

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
            # Nieuwe waardes doorgeven:
            'system_cash_perc': int(cash_perc),
            'system_coupon_perc': int(coupon_perc),
        }

        return request.render("otters_consignment.portal_consignment_submission", values)

    # 2. OPSLAAN VAN INDIVIDUELE INZENDING (MODAL)
    @http.route(['/my/consignments/update'], type='http', auth="user", methods=['POST'], website=True)
    def portal_consignment_update_settings(self, submission_id, payout_method, x_iban=None, **kw):
        """ Update één specifieke inzending (enkel financieel) """
        try:
            submission = self._get_submission_check_access(int(submission_id))
        except (AccessError, MissingError):
            return request.redirect('/my')

        # Mag niet geannuleerd zijn
        if submission.state == 'cancel':
            return request.redirect('/my/consignments/%s' % submission_id)

        ICP = request.env['ir.config_parameter'].sudo()

        # We updaten ENKEL de financiële luiken
        vals = {
            'payout_method': payout_method
        }

        if payout_method == 'cash':
            vals['payout_percentage'] = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        else:
            vals['payout_percentage'] = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

        # De acties (action_unaccepted / action_unsold) worden hier NIET meer aangeraakt.
        # Ze blijven zoals ze waren bij aanmaak.

        if x_iban:
            vals['x_iban'] = x_iban

        submission.write(vals)

        return request.redirect('/my/consignments/%s' % submission_id)

    def _get_submission_check_access(self, submission_id):
        submission = request.env['otters.consignment.submission'].browse(submission_id)
        if not submission.exists():
            raise MissingError("Deze inzending bestaat niet.")

        partner = request.env.user.partner_id
        if submission.sudo().supplier_id.email != partner.email:
            raise AccessError("Je hebt geen toegang tot deze inzending.")

        return submission.sudo()

    @http.route(['/my/consignments/settings'], type='http', auth="user", website=True)
    def portal_my_consignment_settings(self, **kw):
        partner = request.env.user.partner_id
        ICP = request.env['ir.config_parameter'].sudo()

        cash_perc = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3')) * 100
        coupon_perc = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5')) * 100
        current_iban = partner.bank_ids.sorted('id', reverse=True)[:1].acc_number if partner.bank_ids else ''

        values = {
            'partner': partner,
            'current_iban': current_iban,
            'system_cash_perc': int(cash_perc),
            'system_coupon_perc': int(coupon_perc),
            'page_name': 'consignment_settings',
        }
        return request.render("otters_consignment.portal_consignment_settings", values)

    @http.route(['/my/consignments/settings/save'], type='http', auth="user", methods=['POST'], website=True)
    def portal_my_consignment_settings_save(self, payout_method, action_unaccepted, action_unsold, x_iban=None, update_existing=False, **kw):
        partner = request.env.user.partner_id
        ICP = request.env['ir.config_parameter'].sudo()

        cash_perc_val = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        coupon_perc_val = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

        # 1. Update Partner (Voor TOEKOMSTIGE aanvragen)
        vals = {
            'x_payout_method': payout_method,
            'x_cash_payout_percentage': cash_perc_val if payout_method == 'cash' else 0.0,
            'x_coupon_payout_percentage': coupon_perc_val if payout_method == 'coupon' else 0.0,
            # We slaan de acties hier op als standaardvoorkeur
            'x_action_unaccepted': action_unaccepted,
            'x_action_unsold': action_unsold,
        }
        partner.sudo().write(vals)

        # 2. Update IBAN
        if x_iban:
            clean_iban = x_iban.replace(' ', '').upper().strip()
            existing_bank = request.env['res.partner.bank'].sudo().search([
                ('acc_number', '=', clean_iban), ('partner_id', '=', partner.id)
            ], limit=1)
            if not existing_bank:
                request.env['res.partner.bank'].sudo().create({'acc_number': clean_iban, 'partner_id': partner.id})

        # 3. Update Lopende Inzendingen
        # LET OP: Hier updaten we ENKEL de uitbetalingsmethode, NIET de acties!
        if update_existing:
            active_submissions = request.env['otters.consignment.submission'].sudo().search([
                ('supplier_id', '=', partner.id),
                ('state', 'not in', ['done', 'cancel']) # Sla Afgerond en Geannuleerd over
            ])

            sub_vals = {
                'payout_method': payout_method,
                'payout_percentage': cash_perc_val if payout_method == 'cash' else coupon_perc_val,
            }
            active_submissions.write(sub_vals)

        return request.redirect('/my/consignments')