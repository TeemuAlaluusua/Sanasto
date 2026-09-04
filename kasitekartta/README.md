# Sanaston käsitekartta

Interaktiivinen selainsovellus, joka visualisoi koko `concepts/`-kansion
käsitteet verkkokaaviona: kaksi eri näkymää, joko sanaston omat SKOS-relaatiot
(ylä-/alakäsite, liittyvä käsite) tai käsitteiden määritelmien semanttiseen
samankaltaisuuteen perustuva sijoittelu.

## Käyttö

Julkaistu sivu on `../docs/kasitekartta/index.html` — se on osa samaa
GitHub Pages -julkaisua kuin pääsanasto (`docs/index.html`), josta sinne on
myös linkki ("Käsitekartta" -painike yläpalkissa). Sivu on täysin itsenäinen
(data on upotettu tiedostoon), joten mitään palvelinta ei tarvita —
ainoastaan D3.js ladataan CDN:stä (cdnjs.cloudflare.com).

Voit myös avata `../docs/kasitekartta/index.html`-tiedoston suoraan
selaimessa lokaalisti.

Visuaalinen teema (fontit, värit, painikkeet, header) on yhdenmukaistettu
pääsanaston (`docs/index.html`) kanssa: system-ui-fontti, sininen
#2563eb-korostusväri, vaalea harmaa tausta. Sivulla ei ole erillistä tummaa
teemaa, koska pääsanastollakaan ei ole.

Ominaisuudet:
- **Kielivalitsin (FI/SV/EN)** yläpalkissa, sama malli kuin pääsanastossa
  (`docs/index.html`): vaihtaa käsitteiden solmuetiketit, haun ja koko
  käyttöliittymän tekstit (painikkeet, suodattimet, otsikot, tyhjät tilat,
  menetelmäkuvaus) valitulle kielelle. Haku toimii kaikilla kolmella
  kielellä yhtä aikaa riippumatta valitusta käyttöliittymäkielestä.
- **Relaatiot / Semantiikka** -kytkin: vaihtaa graafin asettelun eksplisiittisen
  relaatioverkoston (voimasuuntautunut layout) ja semanttisen
  samankaltaisuuden välillä.
  - **Semantiikka**-näkymässä käsitteet **kelluvat**: kevyt fysiikkasimulaatio
    vetää niitä kohti niiden 2D-projisoitua sijaintia (UMAP), mutta ne
    väistävät toisiaan (collision) ja niitä voi raahata vapaasti — ne eivät
    ole enää jäissä kiinteissä pikselikoordinaateissa kuten aiemmassa
    versiossa.
- Relaatiotyyppisuodattimet: ylä-/alakäsitteet, liittyvät käsitteet, sekä
  "ehdotetut (semanttiset)" — algoritmin laskemat, **vahvistamattomat**
  relaatioehdokkaat.
- "Vain relaatiottomat" -suodatin nostaa esiin käsitteet joilla ei ole vielä
  yhtään relaatiota — hyödyllinen sanastotyön QA-työkalu.
- Haku, ja käsitepaneeli jossa fi/sv/en-määritelmät, synonyymit, lähteet ja
  klikattavat relaatiot/ehdotukset.
- "← Sanasto" -painike yläpalkin vasemmassa reunassa vie takaisin pääsanaston
  etusivulle (teksti seuraa valittua kieltä).

## Datan päivittäminen

Sivun sisältämä data (käsitteet, relaatiot, semanttiset ehdotukset ja
2D-sijainnit) on kiinteä snapshot `concepts/`-kansiosta sillä hetkellä kun
`build_data.py` ajettiin viimeksi. Kun `concepts/`-kansioon tehdään muutoksia
(uusia käsitteitä, korjattuja relaatioita), sivu pitää regeneroida:

```bash
cd kasitekartta
pip install -r requirements.txt
python3 build_data.py
```

Tämä lukee `../concepts/*.yml`, laskee relaatiograafin ja semanttiset
ehdotukset, ja kirjoittaa tuloksen sekä `graph_data.json`:iin (data sellaisenaan,
tähän kansioon, ei tarvitse versioida gitiin) että
`../docs/kasitekartta/index.html`:ään (data upotettuna `template.html`-pohjaan
— tämä on se tiedosto joka pitää committata, koska GitHub Pages julkaisee
vain `docs/`-kansion sisällön).

`template.html` on sivun HTML/CSS/JS-lähdekoodi (ei sisällä dataa itsessään,
vaan `__GRAPH_DATA__`-paikkamerkin, jonka `build_data.py` korvaa). Jos haluat
muokata sivun ulkoasua tai toiminnallisuutta, muokkaa `template.html`:ää ja
aja `build_data.py` uudelleen — älä muokkaa `../docs/kasitekartta/index.html`:ää
suoraan, koska se ylikirjoitetaan seuraavalla ajolla.

## Menetelmä ja rajoitukset

Eksplisiittiset relaatiot (broader/narrower/related) tulevat suoraan
sanaston SKOS-datasta.

"Ehdotetut (semanttiset)" relaatiot on laskettu suomenkielisten
määritelmien TF-IDF-samankaltaisuudesta (sana 1-2-grammit + merkki
3-5-grammit, kosinisamankaltaisuus, kynnysarvo 0.35, enintään 3
ehdotusta/käsite). Tämä on kevyt lexical-menetelmä, ei transformer-pohjainen
sentence-embedding-malli.

**Jos haluat tarkempia semanttisia ehdotuksia**, voit vaihtaa
`build_data.py`:n embeddings-osion käyttämään esim. `sentence-transformers`-
kirjastoa (`paraphrase-multilingual-MiniLM-L12-v2` tai vastaava monikielinen
malli toimii hyvin suomelle) millä tahansa koneella jolla on internetyhteys:

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
embeddings = model.encode(texts, normalize_embeddings=True)
```

ja korvata nykyisen TF-IDF-laskennan tällä — loppuosa skriptistä (kosinisamankaltaisuus,
UMAP-sijoittelu, kandidaattien suodatus, HTML-injektio) toimii sellaisenaan.

**Nämä ehdotukset eivät ole vahvistettua dataa** — ne on tarkoitettu
sanastotyön apuvälineeksi (mahdollisten puuttuvien relaatioiden löytämiseen),
ei sellaisenaan viralliseen SKOS-dataan lisättäväksi.
