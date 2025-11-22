{
    'name': 'Otters Webshop Consignment',
    'version': '19.0.1.0.0',  # Odoo 19 versie
    'category': 'Website',
    'summary': 'A portal for consignments. People who send clothes to your shop to sell.',
    'license': 'LGPL-3',
    'author': 'Tom Hoornaert',
    'depends': [
        'website_sale',
        'website',
        'stock',
        'sale_management',
        'otters_webshop_outofstock_filter',
        'portal',
        'om_sendcloud_delivery',
    ],
    'data': [
        # 1. SECURITY & CONFIG (Moet EERST geladen worden)
        'security/ir_rule.xml',           # Access Rules (Record-niveau beveiliging)
        'security/ir.model.access.csv',   # ACL's (Model-niveau beveiliging)
        'data/config_data.xml',           # Systeemparameters (Payout percentages, Sendcloud)
        'data/product_attribute_data.xml',# Product Attributen
        'data/whitelist_data.xml',        # whitlist voor forms Attributen

        # 2. BACKEND MODIFICATIES & WIZARDS (DE KRITISCHE SECTIE)
        'views/res_partner_views.xml',
        'views/product_views_inherit.xml',

        # 2.1 EERST: Definieer de actie die door views.xml wordt gebruikt
        'views/import_products_wizard_views.xml', # Bevat: action_import_products_wizard

        # 2.2 TWEEDE: Definieer de Root Menu en gebruik de import actie
        'views/views.xml',                # Bevat: menu_consignment_root EN gebruikt action_import_products_wizard
        'views/sendcloud_extension.xml',

        # 2.3 LAATST: Gebruik de Root Menu voor de Submenu's
        'views/image_upload_wizard_views.xml',    # Gebruikt: menu_consignment_root (parent)
        'reports/consignment_report_views.xml', # Gebruikt: menu_consignment_root (parent)

        # 3. PRINT ACTIES & WEBLAYOUTS (Moet hier komen zodat alle modellen bestaan)
        'reports/product_labels.xml',

        # 4. PORTAAL & WEBSITE
        'views/templates.xml',            # Publieke Consignment formulier
        'views/portal_templates.xml',     # Portal Views (Mijn Inzendingen)
    ],
    'installable': True,
    'auto_install': False,
}
