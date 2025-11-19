from odoo import models, fields, api
# GEEN foute imports

class Outfit(models.Model):
    _name = 'website.outfit'
    _description = 'Website Outfit'
    _inherit = ['website.published.mixin', 'website.multi.mixin']

    name = fields.Char('Name', required=True, translate=True)
    description = fields.Text('Description', translate=True)

    image = fields.Image('Photo', max_width=1920, max_height=1920)

    # --- HIER HET NIEUWE VELD ---
    # Dit is de enige wijziging die je in dit bestand hoeft te maken
    sale_ok = fields.Boolean('Can be Sold', default=True)
    # -----------------------------

    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        domain="[('sale_ok', '=', True)]"
    )

    slug = fields.Char(
        'Slug',
        compute='_compute_slug',
        store=True,
        help="De URL-vriendelijke versie van de naam."
    )

    website_url = fields.Char(
        compute='_compute_website_url',
        help='De volledige URL naar de outfit.'
    )

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
