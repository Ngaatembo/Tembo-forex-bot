"""
Explicit, documented relevance mapping — instrument relevance is NEVER
inferred from vague text by an AI. It's a transparent, testable
keyword search over headline+summary text against a fixed currency
keyword table, plus a fixed currency->instrument table. Anyone can
read this file and know exactly why an article was tagged relevant to
an instrument.
"""

COUNTRY_TO_CURRENCY = {
    "US": "USD", "USA": "USD", "UNITED STATES": "USD",
    "EU": "EUR", "EUROZONE": "EUR", "EURO AREA": "EUR", "GERMANY": "EUR", "FRANCE": "EUR",
    "GB": "GBP", "UK": "GBP", "UNITED KINGDOM": "GBP",
    "JP": "JPY", "JAPAN": "JPY",
}

CURRENCY_TO_INSTRUMENTS = {
    "USD": ("EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"),
    "EUR": ("EUR/USD",),
    "GBP": ("GBP/USD",),
    "JPY": ("USD/JPY",),
}

CURRENCY_KEYWORDS = {
    "USD": ("usd", "dollar", "federal reserve", "fed ", "fomc", "us economy", "u.s. economy", "nonfarm payroll", "nfp"),
    "EUR": ("eur", "euro", "ecb", "european central bank", "eurozone"),
    "GBP": ("gbp", "pound sterling", "boe", "bank of england", " uk ", "britain", "british"),
    "JPY": ("jpy", "yen", "boj", "bank of japan"),
    "XAU": ("gold", "xau", "bullion", "precious metal"),
}


def instruments_relevant_to_text(headline: str, summary):
    text = f"{headline} {summary or ''}".lower()
    instruments = set()

    for currency, keywords in CURRENCY_KEYWORDS.items():
        if currency == "XAU":
            if any(kw in text for kw in keywords):
                instruments.add("XAU/USD")
            continue
        if any(kw in text for kw in keywords):
            instruments.update(CURRENCY_TO_INSTRUMENTS.get(currency, ()))

    return tuple(sorted(instruments))


def currency_for_country(country):
    if country is None:
        return None
    return COUNTRY_TO_CURRENCY.get(country.strip().upper())


def instruments_relevant_to_currency(currency):
    if currency is None:
        return ()
    return CURRENCY_TO_INSTRUMENTS.get(currency.upper(), ())
