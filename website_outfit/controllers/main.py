import logging # Importeer de logger
from odoo import http
from odoo.http import request

class WebsiteOutfit(http.Controller):
    # --- NIEUWE ROUTE VOOR OVERZICHT ---
    @http.route(['/outfits', '/outfits/page/<int:page>'], type='http', auth="public", website=True)
    def outfit_list(self, page=1, **kw):
        """Toont een lijst van alle outfits met paginering."""

        # Instellingen
        items_per_page = 12  # Hoeveel outfits per pagina?
        Outfit = request.env['website.outfit']

        # Alleen gepubliceerde outfits tonen
        domain = [('is_published', '=', True)]

        # Totaal aantal tellen voor de pager
        total = Outfit.search_count(domain)

        # De pager berekenen (standaard Odoo functie)
        pager = request.website.pager(
            url='/outfits',
            total=total,
            page=page,
            step=items_per_page,
            scope=7,
            url_args=kw
        )

        # De records ophalen
        # limit = hoeveelheid per pagina
        # offset = waar te beginnen (berekend door pager)
        # order = 'create_date desc' zorgt voor NIEUWSTE bovenaan
        outfits = Outfit.search(
            domain,
            limit=items_per_page,
            offset=pager['offset'],
            order='create_date desc'
        )

        return request.render('website_outfit.outfit_list_page', {
            'outfits': outfits,
            'pager': pager, # Geef pager door aan template
        })

    # Deze route is voor de detailpagina - CORRECT
    @http.route(['/outfit/<string:slug>'], type='http', auth="public", website=True)
    def outfit_detail(self, slug, **kw):
        """Render de detailpagina voor een specifieke outfit."""
        outfit = request.env['website.outfit'].search([('slug', '=', slug)], limit=1)

        if not outfit or not outfit.can_access_from_current_website():
            return request.render('website.404')

        return request.render('website_outfit.outfit_detail_page', {
            'outfit': outfit,
        })

    # Deze route is voor "Hele Outfit Toevoegen" - AANGEPAST
    @http.route(['/outfit/add_all_to_cart'], type='http', auth="public", website=True, methods=['POST'])
    def add_all_to_cart(self, outfit_id, **kw):
        """Voeg alle producten van een outfit toe aan de winkelwagen."""
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

    # Deze route is voor "Eén Product Toevoegen" - AANGEPAST
    @http.route(['/outfit/add_one_to_cart'], type='http', auth="public", website=True, methods=['POST'])
    def add_one_to_cart(self, product_id, redirect, **kw):
        """Voeg één product toe en ga terug naar de outfitpagina."""

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
