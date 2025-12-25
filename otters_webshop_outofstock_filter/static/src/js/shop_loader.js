/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.OttersShopLoader = publicWidget.Widget.extend({
    selector: '.o_wsale_products_page', // Alleen actief op de shoppagina
    events: {
        // 1. Product klikken (Afbeelding & Titel)
        'click .oe_product_image a': '_showLoader',
        'click .o_wsale_product_information a': '_showLoader',

        // 2. Navigatie & Sortering
        'click .pagination a': '_showLoader',                   // Volgende pagina
        'click .dropdown-menu a[href*="/shop"]': '_showLoader', // Sorteer menu
        'click .o_wsale_apply_layout': '_showLoader',           // Grid/Lijst switch

        // 3. Filters (Zijbalk)
        'change .js_attributes input': '_showLoader',           // Checkboxen
        'click .js_attributes label': '_showLoader',            // Labels

        // 4. Categorieën (Overal: Zijbalk, Bovenbalk, Breadcrumbs)
        'click .breadcrumb a': '_showLoader',                   // Kruimelpad bovenaan
        'click a[href*="/shop/category/"]': '_showLoader',      // ELKE link naar een categorie
        'click a[href="/shop"]': '_showLoader',                 // Link terug naar "Alle producten"
    },

    /**
     * @override
     */
    start: function () {
        // HTML toevoegen (als die er nog niet is)
        if ($('#otters_page_loader').length === 0) {
            $('body').append(`
                <div id="otters_page_loader">
                    <div class="otters_spinner_container">
                        <i class="fa fa-circle-o-notch fa-spin otters_spinner"></i>
                    </div>
                    <span class="otters_text">Momentje...</span>
                </div>
            `);
        }

        // Luister naar browser 'terug' knop -> Loader verbergen
        window.addEventListener('pageshow', () => {
            $('#otters_page_loader').removeClass('active');
        });

        return this._super.apply(this, arguments);
    },

    _showLoader: function (ev) {
        // 1. Check op CTRL/CMD click (nieuw tabblad = geen loader)
        if (ev.ctrlKey || ev.metaKey) {
            return;
        }

        // 2. Check of het een "uitklap" knopje is (geen loader)
        const $target = $(ev.currentTarget);
        if ($target.data('toggle') === 'collapse' || $target.data('bs-toggle') === 'collapse') {
            return;
        }

        // 3. Check of de link wel echt ergens heen gaat (geen '#' of lege links)
        const href = $target.attr('href');
        if (!href || href === '#' || href.startsWith('javascript')) {
            return;
        }

        // Alles OK? Toon loader!
        $('#otters_page_loader').addClass('active');
    },
});