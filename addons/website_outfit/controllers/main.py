import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class WebsiteOutfit(http.Controller):

    # --- 1. OVERZICHT PAGINA MET FILTER ---
    @http.route([
        '/outfits',
        '/outfits/page/<int:page>',
        '/outfits/category/<int:category_id>',
        '/outfits/category/<int:category_id>/page/<int:page>'
    ], type='http', auth="public", website=True)
    def outfit_list(self, page=1, category_id=None, **kw):
        items_per_page = 12
        Outfit = request.env['website.outfit']
        Category = request.env['website.outfit.category']

        # Basis domein: alleen gepubliceerde outfits
        domain = [('is_published', '=', True)]

        # Filter logica
        active_category = False
        if category_id:
            domain.append(('category_id', '=', int(category_id)))
            active_category = Category.browse(int(category_id))

        # Haal alle categorieën op voor de filter-knoppen
        categories = Category.search([], order='sequence')

        # Pager en zoeken
        total = Outfit.search_count(domain)

        # URL bouwen voor pager (zodat filter behouden blijft bij volgende pagina)
        url = '/outfits'
        if category_id:
            url = f"/outfits/category/{category_id}"

        pager = request.website.pager(
            url=url,
            total=total,
            page=page,
            step=items_per_page,
            scope=7
        )

        outfits = Outfit.search(
            domain,
            limit=items_per_page,
            offset=pager['offset'],
            order='create_date desc'
        )

        return request.render('website_outfit.outfit_list_page', {
            'outfits': outfits,
            'pager': pager,
            'categories': categories,        # NIEUW
            'active_category': active_category, # NIEUW
        })

    # --- 2. DETAIL PAGINA ---
    @http.route(['/outfit/<string:slug>'], type='http', auth="public", website=True)
    def outfit_detail(self, slug, **kw):
        outfit = request.env['website.outfit'].search([('slug', '=', slug)], limit=1)

        if not outfit or not outfit.can_access_from_current_website():
            return request.render('website.404')

        return request.render('website_outfit.outfit_detail_page', {
            'outfit': outfit,
        })

    @http.route(['/outfit/add_all_to_cart'], type='http', auth="public", website=True, methods=['POST'])
    def add_all_to_cart(self, outfit_id, **kw):
        outfit = request.env['website.outfit'].browse(int(outfit_id))
        if not outfit:
            return request.render('website.404')

        # Haal de huidige winkelwagen op of maak een nieuwe
        sale_order = request.cart or request.website._create_cart()

        for product in outfit.product_ids:
            # --- HIER IS DE CORRECTIE ---
            # Gebruik _cart_add en 'quantity'
            sale_order._cart_add(
                product_id=product.id,
                quantity=1
            )

        return request.redirect("/shop/cart")

    # --- 4. EEN PRODUCT TOEVOEGEN ---
    @http.route(['/outfit/add_one_to_cart'], type='http', auth="public", website=True, methods=['POST'])
    def add_one_to_cart(self, product_id, redirect, **kw):
        if not product_id:
            return request.render('website.404')

        # Haal de huidige winkelwagen op of maak een nieuwe
        sale_order = request.cart or request.website._create_cart()

        # --- HIER IS DE CORRECTIE ---
        # Gebruik _cart_add en 'quantity'
        sale_order._cart_add(
            product_id=int(product_id),
            quantity=1
        )
        return request.redirect(redirect)

    # --- 5. SNIPPET ROUTE ---
    @http.route(['/website_outfit/snippet_content'], type='jsonrpc', auth="public", website=True)
    def snippet_content(self):
        outfits = request.env['website.outfit'].search(
            [('is_published', '=', True)],
            limit=4,
            order='create_date desc'
        )
        return request.env['ir.ui.view']._render_template(
            'website_outfit.snippet_latest_outfits_content',
            {'outfits': outfits, 'outfit_title': 'Nieuwste Looks'}
        )