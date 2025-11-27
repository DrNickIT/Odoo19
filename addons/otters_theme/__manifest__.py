{
    'name': 'Otters & Flamingos Theme',
    'version': '19.0.1.0.0',  # Odoo 19 versie
    'category': 'Website/Theme',
    'summary': 'Custom product cards with random frames',
    'description': """
        Deze module voegt een custom design toe aan de product cards
        op de shop pagina.
        - Random kaders (5 variaties)
        - Gekleurde randen rondom product info
        - Vierkante foto-weergave
    """,
    'author': 'Tom Hoornaert',
    'license': 'LGPL-3',

    # Dit zorgt dat jouw module pas werkt als de webshop module er is
    'depends': ['website_sale'],

    # Hier laden we de XML (voor de variant_x logica)
    'data': [
        'views/templates.xml',
    ],

    # Hier laden we de SCSS (Styling)
    'assets': {
        'web.assets_frontend': [
            # Verwijst naar jouw SCSS bestand
            'otters_theme/static/src/scss/product_card.scss',
        ],
    },

    'installable': True,
    'application': False,
    'auto_install': False,
}
