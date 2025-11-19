import logging # Importeer de logger
from odoo import http
from odoo.http import request

# --- DIT MOET ALTIJD IN DE LOG VERSCHIJNEN BIJ EEN HERSTART ---
_logger = logging.getLogger(__name__)
_logger.info("!!!!!!!!!! [website_outfit] controllers/main.py BESTAND IS GELEZEN DOOR PYTHON !!!!!!!!!!")
# --- EINDE LOG ---

class WebsiteOutfit(http.Controller):

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

    @http.route('/website_outfit/snippet_content', type='http', auth="public", website=True, sitemap=False)
    def latest_outfits_snippet(self, limit=4, **kw):

        # !! DEBUG STAP 1: Wordt de controller aangeroopen?
        _logger.info("!!!!!!!! OUTFIT SNIPPET CONTROLLER: Route /snippet_content is AANGEROEPEN. !!!!!!!!")

        Outfit = request.env['website.outfit'].sudo()
        outfits = Outfit.search(
            [('website_published', '=', True)],
            order='create_date desc',
            limit=int(limit)
        )

        # !! DEBUG STAP 2: Heeft het outfits gevonden?
        _logger.info(f"!!!!!!!! OUTFIT SNIPPET CONTROLLER: {len(outfits)} outfits gevonden. !!!!!!!!")

        return request.render('website_outfit.snippet_latest_outfits_content', {
            'outfits': outfits,
            'outfit_title': kw.get('outfit_title', 'Nieuwste Outfits'),
        })
