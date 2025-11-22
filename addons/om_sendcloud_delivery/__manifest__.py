{
    'name': 'My Sendcloud Connector',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Sendcloud integratie voor Odoo Community',
    'depends': ['delivery', 'website_sale', 'stock_delivery'],
    'data': [
        'views/delivery_carrier_views.xml',
        'views/website_sale_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'om_sendcloud_delivery/static/src/js/sendcloud_widget.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
    'author': 'Tom Hoornaert',
}
