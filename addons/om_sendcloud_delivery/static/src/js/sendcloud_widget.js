/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.SendcloudWidget = publicWidget.Widget.extend({
    selector: '#o_delivery_form',
    events: {
        'change input[type="radio"]': '_onCarrierChange',
        'click .open-sendcloud-map': '_openMap',
    },

    start: function () {
        this._super.apply(this, arguments);
        this._onCarrierChange();
    },

    _onCarrierChange: function () {
        var checkedRadio = this.$el.find('input[type="radio"]:checked');
        this.$('.sendcloud-pickup-container').hide();

        var container = checkedRadio.closest('li').find('.sendcloud-pickup-container');
        if (container.length > 0) {
            container.show();
        }
    },

    _openMap: function (ev) {
        ev.preventDefault();
        var self = this;
        var container = $(ev.currentTarget).closest('.sendcloud-pickup-container');

        // 1. Ophalen van waarden (met fallbacks)
        var publicKey = container.find('.sendcloud_public_key').val();

        // Als land leeg is -> Val terug op 'BE'
        var country = container.find('.sendcloud_country_code').val() || 'BE';

        // Als postcode/stad/straat leeg zijn -> Gebruik lege string ''
        var postalCode = container.find('.sendcloud_zip').val() || '';

        if (!window.sendcloud) {
            console.error("Sendcloud script not loaded");
            return;
        }

        // 2. Data opschonen
        // Postcode spaties weghalen (bijv "3000 " -> "3000")
        if (postalCode) {
            postalCode = postalCode.replace(/\s+/g, '');
        }

        // 3. Configureren
        var config = {
            apiKey: publicKey,
            country: country,
            postalCode: postalCode,
            language: 'nl-be'
        };

        console.log("Sendcloud Map Config (Guest Safe):", config);

        // 4. Kaart openen
        window.sendcloud.servicePoints.open(
            config,
            function(point) {
                console.log("Punt gekozen:", point);
                self._savePoint(point, container);
            },
            function(errors) {
                console.log("Fouten:", errors);
                // Optioneel: Toon een alert aan de gebruiker als de API key mist
                if (String(errors).includes("Missing API key")) {
                    alert("Configuratie fout: API Key ontbreekt. Neem contact op met de webshop.");
                }
            }
        );
    },

    _savePoint: function (point, container) {
        fetch('/shop/sendcloud/save_service_point', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    service_point_id: String(point.id),
                    service_point_name: point.name + ' (' + point.city + ')'
                },
                id: Math.floor(Math.random() * 1000000000)
            })
        })
            .then(function (response) { return response.json(); })
            .then(function (result) {
                if (result.result && result.result.success) {
                    container.find('.sendcloud-selected-point').text("Gekozen: " + point.name + ", " + point.city);
                    container.find('.open-sendcloud-map').text("Wijzig punt");
                    container.find('.open-sendcloud-map').removeClass('btn-primary').addClass('btn-success');
                }
            })
            .catch(function (error) { console.error("Netwerkfout:", error); });
    }
});
