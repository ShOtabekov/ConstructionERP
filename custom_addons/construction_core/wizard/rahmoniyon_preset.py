"""Preset: ЖК Rahmoniyon (5 blocks, 20 floors, shops on the 1st floor).

Unit areas and rooms are taken from the typical floor plan
(«План типового этажа», total 2530 m2). Each unit tuple is
(rooms, total area m2, marker X %, marker Y %) in sales order.
"""

RAHMONIYON_BLOCKS = {
    "A": {
        "name": "Блок А",
        "code": "A",
        "image": "construction_core/static/src/img/rahmoniyon/block_A.jpg",
        "units": [
            (1, 46.6, 37.14, 81.97),
            (1, 58.9, 13.82, 72.96),
            (1, 63.6, 14.21, 20.0),
            (1, 50.2, 27.26, 12.11),
            (2, 67.3, 59.28, 26.99),
            (1, 50.2, 81.42, 12.11),
            (2, 101.6, 94.86, 20.56),
            (1, 46.6, 71.14, 81.97),
        ],
    },
    "B": {
        "name": "Блок Б",
        "code": "B",
        "image": "construction_core/static/src/img/rahmoniyon/block_B.jpg",
        "units": [
            (2, 93.7, 18.95, 88.31),
            (2, 79.5, 8.92, 69.19),
            (2, 101.9, 14.47, 16.51),
            (1, 61.1, 50.6, 24.56),
            (1, 61.1, 60.64, 24.56),
            (2, 75.8, 94.37, 17.98),
            (2, 74.5, 94.37, 67.72),
        ],
    },
    "V": {
        "name": "Блок В",
        "code": "V",
        "image": "construction_core/static/src/img/rahmoniyon/block_V.jpg",
        "units": [
            (3, 96.0, 7.49, 72.68),
            (2, 75.8, 7.49, 19.38),
            (1, 61.1, 46.69, 26.48),
            (1, 61.1, 57.87, 26.48),
            (2, 75.8, 95.58, 19.38),
            (3, 96.0, 95.58, 72.68),
        ],
    },
    "G": {
        "name": "Блок Г",
        "code": "G",
        "image": "construction_core/static/src/img/rahmoniyon/block_G.jpg",
        "units": [
            (2, 74.5, 8.93, 67.72),
            (2, 75.8, 9.16, 17.98),
            (1, 61.1, 42.36, 24.56),
            (1, 61.1, 52.28, 24.56),
            (2, 101.9, 87.92, 16.51),
            (2, 79.5, 93.34, 69.19),
            (2, 93.7, 83.57, 88.31),
        ],
    },
    "D": {
        # По списку квартир застройщика (17.11.2026): 8 квартир на этаже,
        # как в блоке А, в обратном порядке (Д-05-07 = 58,9 м²).
        # План и планировки взяты из блока А.
        "name": "Блок Д",
        "code": "D",
        "image": "construction_core/static/src/img/rahmoniyon/block_D.jpg",
        "units": [
            (1, 46.6, 71.14, 81.97),
            (2, 101.6, 94.86, 20.56),
            (1, 50.2, 81.42, 12.11),
            (2, 67.3, 59.28, 26.99),
            (1, 50.2, 27.26, 12.11),
            (1, 63.6, 14.21, 20.0),
            (1, 58.9, 13.82, 72.96),
            (1, 46.6, 37.14, 81.97),
        ],
    },
}


def unit_image_path(block_key, position):
    return (
        "construction_core/static/src/img/rahmoniyon/unit_%s_%d.jpg"
        % (block_key, position)
    )


RAHMONIYON_DEFAULTS = {
    "floors_total": 20,
    "residential_from": 2,
    "shop_count": 5,
    "shop_area": 100.0,
}
