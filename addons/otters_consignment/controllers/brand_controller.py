# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class OttersBrandController(http.Controller):
    # Aantal merken per pagina
    _brands_per_page = 24

    @http.route(['/merken', '/merken/page/<int:page>'], type='http', auth='public', website=True)
    def brands_overview(self, page=1, **kw):
        # 1. Haal alle gepubliceerde merken op
        all_brands = request.env['otters.brand'].search([
            ('is_published', '=', True)
        ], order='name asc')

        # 2. Filter: Alleen merken met voorraad
        # (Dit gebeurt in Python, dus we hebben de volledige lijst nodig om te kunnen tellen)
        visible_brands = all_brands.filtered(lambda b: b.product_ids.filtered(
            lambda p: p.is_published and p.qty_available > 0
        ))

        # 3. Paginering instellen
        total = len(visible_brands)
        pager = request.website.pager(
            url='/merken',
            total=total,
            page=page,
            step=self._brands_per_page,
            scope=7,
            url_args=kw
        )

        # 4. De juiste "hap" uit de lijst nemen voor deze pagina
        offset = pager['offset']
        brands_to_show = visible_brands[offset : offset + self._brands_per_page]

        return request.render('otters_consignment.brands_overview_page', {
            'brands': brands_to_show, # We sturen alleen de merken voor deze pagina
            'pager': pager,           # We sturen de pager data mee
        })

    # ... (Detail route blijft ongewijzigd) ...
    @http.route('/brand/<model("otters.brand"):brand>', type='http', auth='public', website=True)
    def brand_detail(self, brand, **kw):
        products = brand.product_ids.filtered(
            lambda p: p.is_published and p.qty_available > 0
        )
        return request.render('otters_consignment.brand_detail_page', {
            'brand': brand,
            'products': products,
        })