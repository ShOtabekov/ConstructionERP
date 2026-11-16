{
    "name": "Construction Sales",
    "version": "19.0.1.0.0",
    "category": "Construction",
    "summary": "Real estate reservations and sales contracts",
    "description": """
        Construction Sales Management
        =============================
        - Apartment reservations
        - Customer management using Odoo Contacts
        - Real estate sales contracts
        - USD and TJS price fixation
        - Reservation expiration
        - Sales history
    """,
    "author": "Construction ERP",
    "license": "LGPL-3",
    "depends": [
        "base",
        "contacts",
        "mail",
        "construction_core",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequences.xml",
        "data/cron.xml",
        "views/reservation_views.xml",
        "views/contract_views.xml",
        "views/sales_menus.xml",
    ],
    "application": True,
    "installable": True,
}
