"""Pictures of the wares.

Each entry pairs a photo in ``static/productdle/wares/`` with the ways a product
in the shop can be named ("Tuborg Grøn", "Tuborg Grøn Pilsner", ...). A product
gets a picture when its name, with markup, casing and punctuation ignored,
equals one of those names or starts with one of them. When several names fit,
the longest one wins, so "Faxe Kondi Booster Melon Boost" is not given the plain
"Faxe Kondi" photo.

The product names live in the stregsystem database, so add an alias here
whenever a ware is renamed. ``manage.py wares`` lists the products it could not
match.
"""

import re

import unicodedata

from django.templatetags.static import static

WARES = [
    ("coca-cola.png", ["coca cola", "coca cola original"]),
    ("faxe-kondi.png", ["faxe kondi", "faxe kondi pro", "faxe kondi cotm"]),
    ("faxe-kondi-booster-energi.png", ["faxe kondi booster energi", "booster energi"]),
    ("faxe-kondi-booster-pink-dragon-fruit.png", ["faxe kondi booster pink dragon fruit", "pink dragon fruit"]),
    ("faxe-kondi-booster-lucky-boost.png", ["faxe kondi booster lucky boost", "lucky boost"]),
    ("faxe-kondi-booster-melon-boost.png", ["faxe kondi booster melon boost", "melon boost"]),
    ("faxe-kondi-booster-original.png", ["faxe kondi booster original"]),
    ("faxe-kondi-booster-original-zero.png", ["faxe kondi booster original zero"]),
    ("faxe-kondi-booster-sort-energi.png", ["faxe kondi booster sort energi", "booster sort"]),
    ("faxe-kondi-booster-sort-energi-zero.png", ["faxe kondi booster sort energi zero"]),
    ("faxe-kondi-booster-twisted-ice-zero.png", ["faxe kondi booster twisted ice zero", "twisted ice zero"]),
    ("faxe-kondi-booster-lemon.png", ["faxe kondi booster lemon"]),
    ("faxe-kondi-booster-frosty-blue-zero.png", ["faxe kondi booster frosty blue zero", "frosty blue zero"]),
    ("faxe-kondi-booster-aztro.png", ["faxe kondi booster aztro", "aztro"]),
    ("sport-cola.png", ["sport cola"]),
    ("sport-cola-light.png", ["sport cola light"]),
    ("pepsi-max.png", ["pepsi max"]),
    ("kinley.png", ["kinley", "kinley tonic"]),
    ("kilde-vaeld.png", ["kilde væld", "kildevæld"]),
    ("cocio.png", ["cocio"]),
    ("frem-aeblemost.png", ["frem æblemost", "æblemost"]),
    ("hancock-appelsinjuice.png", ["hancock appelsinjuice", "hancock appelsin", "appelsinjuice"]),
    ("fuze-tea-fersken.png", ["fuze tea fersken", "fuzetea fersken"]),
    ("fuze-tea-fersken-hibiscus.png", ["fuze tea fersken hibiscus", "fersken hibiscus"]),
    ("tuborg-groen.png", ["tuborg grøn", "tuborg groen"]),
    ("tuborg-classic.png", ["tuborg classic"]),
    ("tuborg-guld.png", ["tuborg guld"]),
    ("carlsberg-nordic.png", ["carlsberg nordic", "nordic pilsner"]),
    ("grimbergen-double-ambree.png", ["grimbergen double ambree", "grimbergen"]),
    ("refsvindinge-ale.png", ["refsvindinge ægte fynsk ale", "refsvindinge ale", "ægte fynsk ale", "ale no 16"]),
    ("limfjords-porter.png", ["limfjords porter", "limfjord porter", "limfjordsporter"]),
    ("thy-classic.png", ["thy classic"]),
    ("somersby-apple.png", ["somersby apple", "somersby"]),
]

TAG_RE = re.compile(r"<[^>]+>")
SEPARATOR_RE = re.compile(r"[^0-9a-zæøå]+")

# Products whose name contains one of these words must not borrow the photo of a
# more general ware. "Faxe Kondi Booster" is not the plain "Faxe Kondi" can.
DISQUALIFIERS = {
    "faxe-kondi.png": ["booster"],
    "somersby-apple.png": ["fyttetur"],
    "cocio.png": ["kaffe"],
}


def normalize(name: str) -> str:
    """Product name reduced to lowercase words, without markup, accents or punctuation."""
    text = TAG_RE.sub("", name).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return SEPARATOR_RE.sub(" ", text).strip()


_ALIASES = [(normalize(alias), image) for image, aliases in WARES for alias in aliases]


def _contains(words: list, phrase: list) -> bool:
    """True when the phrase appears in the words, in order and uninterrupted."""
    span = len(phrase)
    return any(words[i : i + span] == phrase for i in range(len(words) - span + 1))


def image_for(name: str) -> str:
    """Static URL of the ware's photo, or "" when it has none.

    The product's name may carry the ware's name anywhere inside it - the shop
    names things like "Vand (Kildevæld uden brus) (excl. pant)" or
    "Øl(Tuborg Grøn/-Classic & Guld)" - so an alias matches when its words
    appear in order inside the product's words. The longest alias wins, so a
    specific ware never inherits the photo of the general product it is named
    after.
    """
    words = normalize(name).split()
    if not words:
        return ""
    best = None
    for alias, image in _ALIASES:
        phrase = alias.split()
        if not _contains(words, phrase):
            continue
        if any(word in words for word in DISQUALIFIERS.get(image, ())):
            continue
        if best is None or len(phrase) > best[0]:
            best = (len(phrase), image)
    return static(f"productdle/wares/{best[1]}") if best else ""
