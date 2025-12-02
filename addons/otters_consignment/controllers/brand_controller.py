# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class OttersBrandController(http.Controller):

    # 1. De Overzichtspagina (/merken)
    @http.route('/merken', type='http', auth='public', website=True)
    def brands_overview(self, **kw):
        # Stap 1: Haal alle merken op die op 'Gepubliceerd' staan
        all_brands = request.env['otters.brand'].search([
            ('is_published', '=', True)
        ], order='name asc')

        # Stap 2: Filter: Toon enkel merken met minstens 1 beschikbaar product
        # We kijken of er in 'product_ids' minstens één product zit dat:
        # a) Gepubliceerd is (is_published=True)
        # b) Voorraad heeft (qty_available > 0)

        visible_brands = all_brands.filtered(lambda b: b.product_ids.filtered(
            lambda p: p.is_published and p.qty_available > 0
        ))

        return request.render('otters_consignment.brands_overview_page', {
            'brands': visible_brands,
        })

    # 2. De Detailpagina (/brand/woody)
    @http.route('/brand/<model("otters.brand"):brand>', type='http', auth='public', website=True)
    def brand_detail(self, brand, **kw):
        # Ook hier tonen we enkel de beschikbare producten
        products = brand.product_ids.filtered(
            lambda p: p.is_published and p.qty_available > 0
        )

        values = {
            'brand': brand,
            'products': products,
        }
        return request.render('otters_consignment.brand_detail_page', values)