{
    "name": "Construction Core",
    "version": "19.0.1.2.0",
    "category": "Construction",
    "summary": "Construction projects and real estate management",
    "author": "Construction ERP",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/project_views.xml",
        "views/real_estate_views.xml",
        "views/chessboard_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "construction_core/static/src/js/apartment_chessboard.js",
            "construction_core/static/src/xml/apartment_chessboard.xml",
            "construction_core/static/src/scss/apartment_chessboard.scss",
        ],
    },
    "application": True,
    "installable": True
}

