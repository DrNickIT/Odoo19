# -*- coding: utf-8 -*-
{
    'name': "Website Outfits",
    'summary': "Beheer en toon outfits op je website.",
    'description': """
        Staat toe om outfits te maken (bestaande uit meerdere producten) 
        en deze te tonen op de website via een snippet en detailpagina's.
    """,
    'author': "Jouw Naam",
    'website': "https_jouw_website.nl",
    'category': 'Website/eCommerce',
    'version': '19.0.1.0.0',

    # Essentiële afhankelijkheden
    'depends': [
        'base',
        'website',
        'website_sale', # Nodig voor /shop/cart functionaliteit
        'product',        # Nodig voor de M2M relatie
    ],

    # Laad al onze nieuwe bestanden
    'data': [
        'security/ir.model.access.csv',
        'views/outfit_views.xml',
        'views/outfit_templates.xml',
        'data/outfit_data.xml',
    ],

    # Voeg een icoon toe (optioneel, maar netjes)
    # Maak hiervoor een bestand: /addons/website_outfit/static/description/icon.png
    'images': ['static/description/icon.png'],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
