# Card Tracker - Pokemon & One Piece (NL)

Gratis tool die voor jou bijhoudt of er bij Nederlandse webshops **nieuwe voorraad of
nieuwe sets** zijn. Doel: betere inkoopbeslissingen voor card packs.

## Hoe het werkt

- **Set-releases**: trekt de officiele Pokemon TCG API en de
  One Piece TCG API (`apitcg.com`) en markeert nieuwe sets sinds vorige run.
- **Webshop monitoring**: per pagina maakt het script een fingerprint
  (genormaliseerde tekst-hash, set unieke prijzen, item-count). Bij
  verschil met vorige snapshot zie je in het rapport "inhoud gewijzigd",
  "nieuwe prijzen", of "aantal items: X -> Y". Werkt op elke shop -
  geen brittle CSS-selectors per site.
- **Geschiedenis**: alles gaat naar `data/history.jsonl` (per run, per URL).
- **Rapport**: `docs/index.html`. Te bekijken via GitHub Pages.

## Setup

### 1. GitHub Pages aanzetten

Repo settings -> Pages -> Source: *Deploy from a branch*, branch
`main` (of de branch waar de workflow naar pusht), folder `/docs`.
Daarna is je dashboard te vinden op
`https://<jouw-user>.github.io/Overview_CollectionCards/`.

### 2. Workflow checken

`.github/workflows/update.yml` draait elk uur en bij elke push naar
`main`/`claude/**`. Triggeren kan ook handmatig via tab Actions ->
*update-card-tracker* -> *Run workflow*.

De workflow heeft `permissions: contents: write` nodig (staat al in
het bestand) zodat hij de gegenereerde data en het rapport kan
committen.

### 3. Bronnen aanpassen

Bewerk `config/sources.yaml`. Voeg URLs toe of haal ze weg.
Voorbeeld:

```yaml
shops:
  - name: "Mijn nieuwe shop"
    region: nl-online       # of: maastricht
    games: [pokemon]
    urls:
      - "https://shop.nl/categorie/pokemon"
```

## Lokaal draaien (optioneel)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.tracker
open docs/index.html
```

Eerste run: alle pagina's zijn "nieuw toegevoegd". Vanaf de tweede
run zie je echte wijzigingen.

## Beperkingen


- Sites achter Cloudflare-bescherming (bv. soms MediaMarkt of
  Bol.com) kunnen 403 geven. In het rapport zie je dat als rode rij;
  dan helpt het om je eigen lokale runner te gebruiken of een andere
  URL te kiezen (bv. een specifieke productpagina).
- De One Piece API endpoint kan veranderen; `onepiece_api.py`
  probeert meerdere URL-vormen en log't anders een nette fout.

## Bestandsstructuur

```
config/sources.yaml         shops + URLs
src/tracker.py              orchestrator
src/scrapers/webshop.py     universele HTML snapshot
src/scrapers/pokemon_api.py Pokemon TCG sets
src/scrapers/onepiece_api.py One Piece TCG sets
src/report.py               HTML dashboard
data/history.jsonl          run-geschiedenis (gecommit)
data/state.json             laatste snapshot per URL
docs/index.html             dashboard (GitHub Pages)
.github/workflows/update.yml  hourly job
```
