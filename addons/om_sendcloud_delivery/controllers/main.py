from odoo import http
from odoo.http import request

class SendcloudController(http.Controller):

    # AANPASSING: type='json' is nu type='jsonrpc'
    @http.route('/shop/sendcloud/save_service_point', type='jsonrpc', auth="public", website=True)
    def save_service_point(self, service_point_id, service_point_name, **kw):
        print(f"--- SENDCLOUD CONTROLLER: Punt opslaan {service_point_id} ---")

        # We halen de order direct uit de sessie (Odoo 19 proof)
        sale_order_id = request.session.get('sale_order_id')

        if sale_order_id:
            # Sudo() gebruiken voor schrijfrechten
            order = request.env['sale.order'].sudo().browse(sale_order_id)

            if order.exists():
                order.write({
                    'sendcloud_service_point_id': service_point_id,
                    'sendcloud_service_point_name': service_point_name
                })
                return {'success': True}

        print("--- GEEN ORDER GEVONDEN IN SESSIE ---")
        return {'success': False}
