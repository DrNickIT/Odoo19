from odoo import http
from odoo.http import request

class SendcloudController(http.Controller):

    @http.route('/shop/sendcloud/save_service_point', type='jsonrpc', auth="public", website=True)
    def save_service_point(self, service_point_id, service_point_name, **kw):
        # Haal order ID uit de sessie (Odoo 19 proof)
        sale_order_id = request.session.get('sale_order_id')

        if sale_order_id:
            # Sudo is nodig omdat gasten anders niet mogen schrijven
            order = request.env['sale.order'].sudo().browse(sale_order_id)
            if order.exists():
                order.write({
                    'sendcloud_service_point_id': service_point_id,
                    'sendcloud_service_point_name': service_point_name
                })
                return {'success': True}

        return {'success': False}
