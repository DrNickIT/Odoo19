# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class OttersBrandController(http.Controller):

    _brands_per_page = 24
    _products_per_page = 24

    @http.route(['/merken', '/merken/page/<int:page>'], type='http', auth='public', website=True)
    def brands_overview(self, page=1, **kw):
        all_brands = request.env['otters.brand'].search([
            ('is_published', '=', True)
        ], order='name asc')

        visible_brands = all_brands.filtered(lambda b: b.product_ids.filtered(
            lambda p: p.is_published and p.virtual_available > 0
        ))

        total = len(visible_brands)
        pager = request.website.pager(
            url='/merken',
            total=total,
            page=page,
            step=self._brands_per_page,
            scope=7,
            url_args=kw
        )

        offset = pager['offset']
        brands_to_show = visible_brands[offset : offset + self._brands_per_page]

        return request.render('otters_consignment.brands_overview_page', {
            'brands': brands_to_show,
            'pager': pager,
        })

    # 2. Detail (AANGEPAST)
    @http.route([
        '/brand/<model("otters.brand"):brand>',
        '/brand/<model("otters.brand"):brand>/page/<int:page>'
    ], type='http', auth='public', website=True)
    def brand_detail(self, brand, page=1, **kw):
        all_products = brand.product_ids.filtered(
            lambda p: p.is_published and p.virtual_available > 0
        )

        total = len(all_products)

        # AANPASSING HIERONDER:
        # We gebruiken request.env['ir.http']._slug(brand) in plaats van slug(brand)
        pager = request.website.pager(
            url='/brand/%s' % request.env['ir.http']._slug(brand),
            total=total,
            page=page,
            step=self._products_per_page,
            scope=7,
            url_args=kw
        )

        offset = pager['offset']
        products_to_show = all_products[offset : offset + self._products_per_page]

        values = {
            'brand': brand,
            'products': products_to_show,
            'pager': pager,
        }
        return request.render('otters_consignment.brand_detail_page', values)