# -*- coding: utf-8 -*-
import logging
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo import http
from odoo.http import request

# Maak een logger aan
_logger = logging.getLogger(__name__)
class OttersWebsiteSale(WebsiteSale):

    @http.route([
        '/shop',
        '/shop/page/<int:page>',
        '/shop/category/<model("product.public.category"):category>',
        '/shop/category/<model("product.public.category"):category>/page/<int:page>'
    ], type='http', auth="public", website=True, sitemap=WebsiteSale.sitemap_shop)
    def shop(self, page=0, category=None, search='', ppg=False, **post):

        # --- FIX 1: Behoud ALLE filters (meervoudige selecties) ---
        # Jouw URL gebruikt 'attribute_values', dus we moeten die specifiek ophalen als lijst.
        # Anders bevat 'post' alleen de laatste filter (bv. alleen Type en niet Maat).
        if request.httprequest.args.getlist('attribute_values'):
            post['attribute_values'] = request.httprequest.args.getlist('attribute_values')

        # Voor de zekerheid ook de standaard 'attrib' meenemen (voor andere filters)
        if request.httprequest.args.getlist('attrib'):
            post['attrib'] = request.httprequest.args.getlist('attrib')

        # --- FIX 2: Sortering ---
        current_sorting = post.get('order') or ''
        if current_sorting == 'create_date desc' or not current_sorting:
            post['order'] = 'type asc, create_date desc'

        # Uitvoeren
        return super(OttersWebsiteSale, self).shop(page, category, search, ppg, **post)

    def _get_mandatory_billing_address_fields(self, country_sudo):
        mandatory_fields = super(OttersWebsiteSale, self)._get_mandatory_billing_address_fields(country_sudo)

        if 'phone' in mandatory_fields:
            mandatory_fields.remove('phone')

        return mandatory_fields

    def _get_mandatory_delivery_address_fields(self, country_sudo):
        mandatory_fields = super(OttersWebsiteSale, self)._get_mandatory_delivery_address_fields(country_sudo)

        if 'phone' in mandatory_fields:
            mandatory_fields.remove('phone')

        return mandatory_fields

    def _get_default_country(self, **kwargs):
        country = request.env.user.country_id

        if country:
            return country

        return request.env['res.country'].sudo().search([('code', '=', 'BE')], limit=1)