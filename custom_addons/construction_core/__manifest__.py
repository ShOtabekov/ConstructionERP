{
    "name": "Construction Core",
    "version": "19.0.1.12.1",
    "category": "Construction",
    "summary": "Construction projects and real estate management",
    "author": "Construction ERP",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/project_views.xml",
        "views/real_estate_views.xml",
        "views/block_wizard_views.xml",
        "views/price_wizard_views.xml",
        "views/chessboard_views.xml",
        "views/project_image_views.xml",
        "data/recompute_names.xml",
        "data/rahmoniyon_sync.xml",
        "data/rahmoniyon_unit_plans.xml",
        "data/rahmoniyon_renders.xml",
        "views/license_views.xml",
        "views/update_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "construction_core/static/src/js/apartment_chessboard.js",
            "construction_core/static/src/xml/apartment_chessboard.xml",
            "construction_core/static/src/scss/apartment_chessboard.scss",
            "construction_core/static/src/license/license_systray.js",
            "construction_core/static/src/license/license_systray.xml",
        ],
    },
    "application": True,
    "installable": True
}

