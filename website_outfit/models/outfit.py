from odoo import models, fields, api

class OutfitCategory(models.Model):
    _name = 'website.outfit.category'
    _description = 'Outfit Categorie'
    _order = 'sequence, name'

    name = fields.Char('Naam', required=True, translate=True)
    sequence = fields.Integer('Volgorde', default=10)
    outfit_ids = fields.One2many('website.outfit', 'category_id', string='Outfits')

class Outfit(models.Model):
    _name = 'website.outfit'
    _description = 'Website Outfit'
    _inherit = ['website.published.mixin', 'website.multi.mixin']
    _order = 'sequence, id'  # ### Zorgt dat de volgorde werkt ###

    name = fields.Char('Naam', required=True, translate=True)

    # ### DIT VELD MISTE JE: ###
    sequence = fields.Integer('Volgorde', default=10)
    # ##########################

    description = fields.Text('Beschrijving', translate=True)
    image = fields.Image('Foto', max_width=1920, max_height=1920)
    sale_ok = fields.Boolean('Kan verkocht worden', default=True)

    category_id = fields.Many2one(
        'website.outfit.category',
        string='Categorie',
        help="Bijv. Baby, Kleuter, Teen..."
    )

    product_ids = fields.Many2many(
        'product.product',
        string='Producten',
        domain="[('sale_ok', '=', True)]"
    )

    slug = fields.Char('Slug', compute='_compute_slug', store=True, help="De URL-vriendelijke versie van de naam.")
    website_url = fields.Char(compute='_compute_website_url', help='De volledige URL naar de outfit.')

    @api.depends('name')
    def _compute_slug(self):
        for outfit in self:
            if outfit.id and outfit.name:
                outfit.slug = f"{self.env['ir.http']._slug(outfit)}"
            else:
                outfit.slug = False

    @api.depends('slug')
    def _compute_website_url(self):
        for outfit in self:
            if outfit.slug:
                outfit.website_url = f'/outfit/{outfit.slug}'
            else:
                outfit.website_url = False