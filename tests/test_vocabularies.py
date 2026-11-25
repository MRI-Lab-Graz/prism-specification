"""mappings/vocabularies.json: every vocabulary has a real example URL its pattern accepts and no other pattern does.

A pattern checks the shape of a URL, never that the entry exists (specs/mappings.md). The examples below are real
entries, looked up when the vocabulary was added: OBO ontologies and EFO through the EBI Ontology Lookup Service,
MeSH, UMLS, Wikidata, the NIH CDE repository, PubChem, UniProt, the ATC index, Orphanet, Cognitive Atlas and WHO ICD-10
by opening the URL. Neurobagel's names are the ones listed in its own configuration (neurobagel/communities,
configs/Neurobagel/config.json). Six sources refuse automated lookups (LOINC, ICD-11, OMIM, HMDB, DrugBank, RxNorm on BioPortal):
their shape is the one their own documentation gives, so adding an entry there needs a manual look-up too
(UNVERIFIED below; the mappings page must say the same).
The OBO digit widths were checked against the ontologies' contents (MFOEM, MFOMD, CMO: every class; OBA: a sample).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_mappings  # noqa: E402

# the patterns exactly as the check compiles them, and matched the way it matches (fullmatch)
PATTERNS, _problems = check_mappings.load_vocabularies(ROOT / "mappings/vocabularies.json")
VOCABS = json.loads((ROOT / "mappings/vocabularies.json").read_text(encoding="utf-8"))
UNVERIFIED = {"loinc", "icd11", "omim", "hmdb", "drugbank", "rxnorm"}
OBO = "http://purl.obolibrary.org/obo/"
EXAMPLES = {
    "snomed": "https://snomed.info/id/416954004",
    "loinc": "https://loinc.org/44249-1",
    "chebi": OBO + "CHEBI_17650",
    "ncit": OBO + "NCIT_C117162",
    "hpo": OBO + "HP_0000716",
    "mondo": OBO + "MONDO_0002009",
    "doid": OBO + "DOID_1470",
    "mfoem": OBO + "MFOEM_000026",
    "mfomd": OBO + "MFOMD_0000013",
    "uberon": OBO + "UBERON_0003881",
    "pato": OBO + "PATO_0102003",
    "cmo": OBO + "CMO_0003287",
    "oba": OBO + "OBA_VT1000670",
    "efo": "http://www.ebi.ac.uk/efo/EFO_0007006",
    "icd11": "http://id.who.int/icd/entity/334423054",
    "icd10": "https://icd.who.int/browse10/2019/en#/F32",
    "mesh": "https://id.nlm.nih.gov/mesh/D003866",
    "umls": "https://uts.nlm.nih.gov/uts/umls/concept/C0011581",
    "wikidata": "https://www.wikidata.org/entity/Q42844",
    "cogatlas": "https://www.cognitiveatlas.org/concept/id/trm_5022ef7599294",
    "cde": "https://cde.nlm.nih.gov/deView?tinyId=Qy9ZGtZ4kuH",
    "pubchem": "https://pubchem.ncbi.nlm.nih.gov/compound/5754",
    "uniprot": "https://www.uniprot.org/uniprotkb/P04150",
    "atc": "https://atcddd.fhi.no/atc_ddd_index/?code=N06AB",
    "orphanet": "http://www.orpha.net/ORDO/Orphanet_558",
    "omim": "https://omim.org/entry/608516",
    "hmdb": "https://hmdb.ca/metabolites/HMDB0000063",
    "drugbank": "https://go.drugbank.com/drugs/DB00741",
    "rxnorm": "http://purl.bioontology.org/ontology/RXNORM/5640",
    "neurobagel": "http://neurobagel.org/vocab/Sex",
}


def test_every_vocabulary_has_an_example_and_every_example_a_vocabulary():
    assert set(VOCABS) == set(EXAMPLES)


def test_an_example_matches_its_own_pattern_and_no_other():
    for name, url in EXAMPLES.items():
        matching = [n for n, p in PATTERNS.items() if p.fullmatch(url)]
        assert matching == [name], (name, matching)


def test_a_malformed_url_is_refused():
    for name, url in EXAMPLES.items():
        for bad in (url + "x/y", url.replace("://", "://evil.example/"), url.rsplit("/", 1)[0], url + " ", url + "\n"):
            assert not PATTERNS[name].fullmatch(bad), (name, bad)


def test_other_loinc_kinds_are_accepted():
    codes = ("LP31370-9", "LA6568-5", "LL1000-0", "LG100-4", "44249-1")
    assert all(PATTERNS["loinc"].fullmatch(f"https://loinc.org/{code}") for code in codes)


def test_icd_forms_people_copy_are_accepted():
    assert PATTERNS["icd11"].fullmatch("http://id.who.int/icd/release/11/2019-04/mms/1563440793")
    assert PATTERNS["icd10"].fullmatch("https://icd.who.int/browse10/2019/en#/F30-F39")
    assert PATTERNS["icd10"].fullmatch("https://icd.who.int/browse10/2019/en#/F32.1")


def test_the_mappings_page_lists_every_vocabulary():
    page = (ROOT / "specs/mappings.md").read_text(encoding="utf-8")
    missing = [n for n, v in VOCABS.items() if f"| `{n}` | {v['label']} |" not in page]
    assert missing == []


def test_the_mappings_page_names_the_sources_whose_shape_could_not_be_looked_up():
    page = (ROOT / "specs/mappings.md").read_text(encoding="utf-8")
    sentence = page[page.index("except for"):].split("\n\n")[0]
    assert {n for n in VOCABS if f"`{n}`" in sentence} == UNVERIFIED
